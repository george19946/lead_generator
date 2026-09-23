"""SQLite store (stdlib sqlite3): latest entity state, versioned snapshots, sync cursors and runs.

Every write commits straight away, so an interrupted backfill keeps what it has fetched and can resume.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from signals.core.clock import from_iso, to_iso, utcnow
from signals.core.feed import Lead
from signals.core.source import RawRecord
from signals.db.schema import MIGRATIONS, SCHEMA, SCHEMA_VERSION


class SaveResult(Enum):
    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    SUPPRESSED = "suppressed"  # on the opt-out list: not stored


@dataclass(frozen=True)
class StoredEntity:
    source: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    payload_hash: str
    first_seen_at: datetime
    last_fetched_at: datetime
    last_changed_at: datetime
    gone_at: datetime | None


@dataclass(frozen=True)
class Snapshot:
    fetched_at: datetime
    payload_hash: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class LeadRow:
    vertical: str
    feed: str
    entity_key: str
    trigger_key: str
    event_date: date | None
    week_ending: date
    created_at: datetime
    regions: tuple[str, ...]
    data: dict[str, Any]


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class SchemaVersionError(RuntimeError):
    pass


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._suppressed: set[str] | None = None

    @classmethod
    def open(cls, path: Path | str) -> Store:
        """Open (creating if needed) the database and apply the schema. `:memory:` works for tests."""
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit; see transaction()
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        store = cls(conn)
        store._migrate()
        return store

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise SchemaVersionError(f"database schema v{version} is newer than this code (v{SCHEMA_VERSION})")
        # Both the schema and the migrations are idempotent (IF NOT EXISTS), so a crash before the version
        # is written is harmless.
        if version == 0:
            self.conn.executescript(SCHEMA)
        else:
            for step in range(version + 1, SCHEMA_VERSION + 1):
                self.conn.executescript(MIGRATIONS[step])
        if version < SCHEMA_VERSION:
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    class _Tx:
        def __init__(self, conn: sqlite3.Connection):
            self.conn = conn

        def __enter__(self) -> None:
            self.conn.execute("BEGIN")

        def __exit__(self, exc_type: object, *_: object) -> None:
            self.conn.execute("ROLLBACK" if exc_type else "COMMIT")

    def transaction(self) -> Store._Tx:
        return Store._Tx(self.conn)

    # --- entities and snapshots -----------------------------------------------------

    def save_record(self, record: RawRecord) -> SaveResult:
        """Store a fetched record. A new snapshot is written only when the payload has changed.

        Records on the opt-out list (by their own ID, or a location's provider ID) are not stored.
        """
        if self.is_suppressed(record.entity_id) or self.is_suppressed(record.payload.get("providerId")):
            return SaveResult.SUPPRESSED
        text = canonical_json(record.payload)
        digest = hashlib.sha256(text.encode()).hexdigest()
        at = to_iso(record.fetched_at)
        key = (record.source, record.entity_type, record.entity_id)
        with self.transaction():
            row = self.conn.execute(
                "SELECT payload_hash FROM entities WHERE source=? AND entity_type=? AND entity_id=?", key
            ).fetchone()
            if row is not None and row["payload_hash"] == digest:
                self.conn.execute(
                    "UPDATE entities SET last_fetched_at=?, gone_at=NULL"
                    " WHERE source=? AND entity_type=? AND entity_id=?",
                    (at, *key),
                )
                return SaveResult.UNCHANGED
            if row is None:
                self.conn.execute(
                    "INSERT INTO entities (source, entity_type, entity_id, payload, payload_hash,"
                    " first_seen_at, last_fetched_at, last_changed_at) VALUES (?,?,?,?,?,?,?,?)",
                    (*key, text, digest, at, at, at),
                )
            else:
                self.conn.execute(
                    "UPDATE entities SET payload=?, payload_hash=?, last_fetched_at=?, last_changed_at=?,"
                    " gone_at=NULL WHERE source=? AND entity_type=? AND entity_id=?",
                    (text, digest, at, at, *key),
                )
            self.conn.execute(
                "INSERT INTO snapshots (source, entity_type, entity_id, fetched_at, payload_hash, payload)"
                " VALUES (?,?,?,?,?,?)",
                (*key, at, digest, text),
            )
        return SaveResult.NEW if row is None else SaveResult.CHANGED

    def mark_gone(self, source: str, entity_type: str, entity_id: str, at: datetime) -> bool:
        """Record that the source no longer returns this entity. Returns False if it was never stored."""
        cur = self.conn.execute(
            "UPDATE entities SET gone_at=COALESCE(gone_at, ?), last_fetched_at=?"
            " WHERE source=? AND entity_type=? AND entity_id=?",
            (to_iso(at), to_iso(at), source, entity_type, entity_id),
        )
        return cur.rowcount > 0

    def get(self, source: str, entity_type: str, entity_id: str) -> StoredEntity | None:
        row = self.conn.execute(
            "SELECT * FROM entities WHERE source=? AND entity_type=? AND entity_id=?",
            (source, entity_type, entity_id),
        ).fetchone()
        return _entity(row) if row else None

    def has(self, source: str, entity_type: str, entity_id: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM entities WHERE source=? AND entity_type=? AND entity_id=?",
                (source, entity_type, entity_id),
            ).fetchone()
            is not None
        )

    def iter_entities(self, source: str, entity_type: str, *, include_gone: bool = False) -> Iterator[StoredEntity]:
        sql = "SELECT * FROM entities WHERE source=? AND entity_type=?"
        if not include_gone:
            sql += " AND gone_at IS NULL"
        for row in self.conn.execute(sql + " ORDER BY entity_id", (source, entity_type)).fetchall():
            yield _entity(row)

    def fetched_since(self, source: str, entity_type: str, since: datetime) -> set[str]:
        rows = self.conn.execute(
            "SELECT entity_id FROM entities WHERE source=? AND entity_type=? AND last_fetched_at>=?",
            (source, entity_type, to_iso(since)),
        )
        return {r[0] for r in rows}

    def ids_with_history(self, source: str, entity_type: str) -> set[str]:
        """IDs of entities with more than one stored version (i.e. that have changed)."""
        rows = self.conn.execute(
            "SELECT entity_id FROM snapshots WHERE source=? AND entity_type=? GROUP BY entity_id HAVING COUNT(*)>1",
            (source, entity_type),
        )
        return {r[0] for r in rows}

    def history(self, source: str, entity_type: str, entity_id: str) -> list[Snapshot]:
        """All stored versions, oldest first."""
        rows = self.conn.execute(
            "SELECT fetched_at, payload_hash, payload FROM snapshots"
            " WHERE source=? AND entity_type=? AND entity_id=? ORDER BY fetched_at, id",
            (source, entity_type, entity_id),
        )
        return [_snapshot(r) for r in rows]

    def snapshot_as_of(self, source: str, entity_type: str, entity_id: str, at: datetime) -> Snapshot | None:
        """The version that was current at `at` (the latest fetched at or before it)."""
        row = self.conn.execute(
            "SELECT fetched_at, payload_hash, payload FROM snapshots"
            " WHERE source=? AND entity_type=? AND entity_id=? AND fetched_at<=?"
            " ORDER BY fetched_at DESC, id DESC LIMIT 1",
            (source, entity_type, entity_id, to_iso(at)),
        ).fetchone()
        return _snapshot(row) if row else None

    def counts(self) -> dict[str, int]:
        """Entity counts per `source/entity_type`, plus table totals."""
        out = {
            f"{r[0]}/{r[1]}": r[2]
            for r in self.conn.execute(
                "SELECT source, entity_type, COUNT(*) FROM entities GROUP BY 1, 2 ORDER BY 1, 2"
            )
        }
        for table in ("snapshots", "lead_events", "runs"):
            out[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return out

    # --- lead events ------------------------------------------------------------------

    def record_lead(self, vertical: str, lead: Lead, week_ending: date, at: datetime) -> int:
        """Record a lead for the week unless its trigger was recorded before. Returns 1 if new, else 0."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO lead_events"
            " (vertical, feed, entity_key, trigger_key, event_date, week_ending, created_at, data)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                vertical,
                lead.feed,
                lead.entity_key,
                lead.trigger_key,
                lead.event_date.isoformat() if lead.event_date else None,
                week_ending.isoformat(),
                to_iso(at),
                canonical_json({"regions": list(lead.regions), "data": lead.data}),
            ),
        )
        return cur.rowcount

    def leads_for_week(self, vertical: str, week_ending: date, feed: str | None = None) -> list[LeadRow]:
        """Leads first reported in the given week, in a stable order."""
        sql = "SELECT * FROM lead_events WHERE vertical=? AND week_ending=?"
        params: list[Any] = [vertical, week_ending.isoformat()]
        if feed:
            sql += " AND feed=?"
            params.append(feed)
        rows = self.conn.execute(sql + " ORDER BY feed, event_date DESC, entity_key, trigger_key", params)
        return [_lead(r) for r in rows]

    # --- opt-outs ----------------------------------------------------------------------

    def is_suppressed(self, entity_id: str | None) -> bool:
        if not entity_id:
            return False
        if self._suppressed is None:
            self._suppressed = {r[0] for r in self.conn.execute("SELECT entity_id FROM suppressed")}
        return str(entity_id) in self._suppressed

    def suppressed(self) -> list[tuple[str, datetime, str | None]]:
        rows = self.conn.execute("SELECT entity_id, added_at, note FROM suppressed ORDER BY added_at, entity_id")
        return [(r[0], from_iso(r[1]), r[2]) for r in rows]

    def suppress(self, entity_id: str, note: str | None, at: datetime) -> dict[str, int]:
        """Add an ID to the opt-out list and erase everything stored about it. Returns rows deleted per table."""
        self.conn.execute(
            "INSERT OR REPLACE INTO suppressed (entity_id, added_at, note) VALUES (?,?,?)", (entity_id, to_iso(at), note)
        )
        self._suppressed = None
        return self.forget(entity_id)

    def unsuppress(self, entity_id: str) -> bool:
        removed = self.conn.execute("DELETE FROM suppressed WHERE entity_id=?", (entity_id,)).rowcount > 0
        self._suppressed = None
        return removed

    def forget(self, entity_id: str) -> dict[str, int]:
        """Delete an entity, its versions and its leads. For a provider, also its locations and their leads."""
        with self.transaction():
            ids = [entity_id] + [
                r[0]
                for r in self.conn.execute(
                    "SELECT entity_id FROM entities WHERE entity_type='location'"
                    " AND json_extract(payload, '$.providerId')=?",
                    (entity_id,),
                )
            ]
            counts = {"entities": 0, "snapshots": 0, "lead_events": 0}
            for one in ids:
                counts["entities"] += self.conn.execute("DELETE FROM entities WHERE entity_id=?", (one,)).rowcount
                counts["snapshots"] += self.conn.execute("DELETE FROM snapshots WHERE entity_id=?", (one,)).rowcount
                counts["lead_events"] += self.conn.execute(
                    "DELETE FROM lead_events WHERE entity_key LIKE '%:' || ?"
                    " OR json_extract(data, '$.data.provider_id')=?",
                    (one, one),
                ).rowcount
        return counts

    # --- sync state -----------------------------------------------------------------

    def get_cursor(self, source: str, stream: str) -> str | None:
        row = self.conn.execute(
            "SELECT cursor FROM sync_state WHERE source=? AND stream=?", (source, stream)
        ).fetchone()
        return row[0] if row else None

    def set_cursor(self, source: str, stream: str, cursor: str) -> None:
        self.conn.execute(
            "INSERT INTO sync_state (source, stream, cursor, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT (source, stream) DO UPDATE SET cursor=excluded.cursor, updated_at=excluded.updated_at",
            (source, stream, cursor, to_iso(utcnow())),
        )

    # --- runs -----------------------------------------------------------------------

    def start_run(self, command: str, params: dict[str, Any], at: datetime | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (command, params, started_at, status) VALUES (?,?,?,'running')",
            (command, canonical_json(params), to_iso(at or utcnow())),
        )
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, stats: dict[str, Any], at: datetime | None = None) -> None:
        self.conn.execute(
            "UPDATE runs SET status=?, stats=?, finished_at=? WHERE id=?",
            (status, canonical_json(stats), to_iso(at or utcnow()), run_id),
        )

    # --- retention ------------------------------------------------------------------

    def purge(self, before: datetime) -> dict[str, int]:
        """Delete data older than `before`, keeping each live entity's current snapshot.

        Removes superseded snapshots, entities that disappeared from their source before the cutoff
        (with their snapshots), lead events and finished runs.
        """
        cutoff = to_iso(before)
        with self.transaction():
            gone = self.conn.execute(
                "SELECT source, entity_type, entity_id FROM entities WHERE gone_at IS NOT NULL AND gone_at<?",
                (cutoff,),
            ).fetchall()
            for row in gone:
                self.conn.execute(
                    "DELETE FROM snapshots WHERE source=? AND entity_type=? AND entity_id=?", tuple(row)
                )
            entities = self.conn.execute(
                "DELETE FROM entities WHERE gone_at IS NOT NULL AND gone_at<?", (cutoff,)
            ).rowcount
            # A snapshot is superseded when a newer one of the same entity exists.
            snapshots = self.conn.execute(
                "DELETE FROM snapshots WHERE fetched_at<? AND EXISTS ("
                " SELECT 1 FROM snapshots newer WHERE newer.source=snapshots.source"
                " AND newer.entity_type=snapshots.entity_type AND newer.entity_id=snapshots.entity_id"
                " AND (newer.fetched_at>snapshots.fetched_at"
                "      OR (newer.fetched_at=snapshots.fetched_at AND newer.id>snapshots.id)))",
                (cutoff,),
            ).rowcount
            leads = self.conn.execute("DELETE FROM lead_events WHERE created_at<?", (cutoff,)).rowcount
            runs = self.conn.execute(
                "DELETE FROM runs WHERE started_at<? AND status!='running'", (cutoff,)
            ).rowcount
        return {"entities": entities, "snapshots": snapshots, "lead_events": leads, "runs": runs}


def _entity(row: sqlite3.Row) -> StoredEntity:
    return StoredEntity(
        source=row["source"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        payload=json.loads(row["payload"]),
        payload_hash=row["payload_hash"],
        first_seen_at=from_iso(row["first_seen_at"]),
        last_fetched_at=from_iso(row["last_fetched_at"]),
        last_changed_at=from_iso(row["last_changed_at"]),
        gone_at=from_iso(row["gone_at"]) if row["gone_at"] else None,
    )


def _lead(row: sqlite3.Row) -> LeadRow:
    body = json.loads(row["data"])
    return LeadRow(
        vertical=row["vertical"],
        feed=row["feed"],
        entity_key=row["entity_key"],
        trigger_key=row["trigger_key"],
        event_date=date.fromisoformat(row["event_date"]) if row["event_date"] else None,
        week_ending=date.fromisoformat(row["week_ending"]),
        created_at=from_iso(row["created_at"]),
        regions=tuple(body.get("regions", [])),
        data=body.get("data", {}),
    )


def _snapshot(row: sqlite3.Row) -> Snapshot:
    return Snapshot(from_iso(row["fetched_at"]), row["payload_hash"], json.loads(row["payload"]))
