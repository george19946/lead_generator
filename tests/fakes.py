"""A fake CQC API for collection tests: list, detail and changes endpoints over in-memory records."""

from datetime import datetime, timezone

import httpx

from signals.settings import RegionConfig
from signals.verticals.care.collect import ASC_DIRECTORATE

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
REGIONS = {
    "london": RegionConfig(cqc_region="London"),
    "east-london": RegionConfig(postcode_areas=["E", "IG", "RM"]),
}


def loc(location_id, region, postcode, provider="P1", status="Registered", directorate=ASC_DIRECTORATE, **extra):
    return {
        "locationId": location_id, "name": f"Home {location_id}", "providerId": provider,
        "registrationStatus": status, "region": region, "postalCode": postcode,
        "inspectionDirectorate": directorate, "localAuthority": "Somewhere",
        "regulatedActivities": [{"name": "Personal care", "contacts": [{"personGivenName": "Jane"}]}],
        **extra,
    }


class FakeCqc:
    """Just enough of the CQC API: list, detail and changes endpoints."""

    def __init__(self):
        self.locations = {
            "L1": loc("L1", "London", "SE1 7PB"),
            "L2": loc("L2", "London", "N16 0AA", provider="P2", status="Deregistered"),
            "L3": loc("L3", "East", "IG10 1AA"),  # Essex, but in the east-london postcode region
            "L4": loc("L4", "North West", "FY4 2RF", provider="P4"),
        }
        self.listed = {"London": ["L1", "L2", "L5"], None: ["L1", "L2", "L3", "L4", "L5"]}  # L5 is gone
        self.providers = {p: {"providerId": p, "name": f"Provider {p}", "locationIds": []} for p in ("P1", "P2", "P3", "P4", "P9")}
        self.changes = {"location": [], "provider": []}
        self.fail = set()
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        parts = request.url.path.split("/")[3:]  # after /public/v1
        params = request.url.params
        if parts == ["locations"]:
            assert params["inspectionDirectorate"] == ASC_DIRECTORATE
            ids = self.listed[params.get("region")]
            postcodes = {i: self.locations[i]["postalCode"] if i in self.locations else "E1 1AA" for i in ids}
            items = [{"locationId": i, "locationName": i, "postalCode": postcodes[i]} for i in ids]
            return httpx.Response(200, json={"locations": items, "total": len(items), "totalPages": 1, "page": 1})
        if parts[0] == "changes":
            return httpx.Response(200, json={"changes": self.changes[parts[1]], "totalPages": 1, "page": 1})
        kind, entity_id = parts
        if entity_id in self.fail:
            return httpx.Response(400, json={"message": "bad"})
        table = self.locations if kind == "locations" else self.providers
        return httpx.Response(200, json=table[entity_id]) if entity_id in table else httpx.Response(404)

    def detail_calls(self, kind):
        return sorted(r.url.path.rsplit("/", 1)[1] for r in self.requests if f"/{kind}/" in r.url.path)
