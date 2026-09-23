"""Hints for new-company leads: SIC code labels, and names that suggest the business isn't CQC-regulated.

Care SIC codes also cover children's services (regulated by Ofsted, not CQC), recruitment agencies and
training firms. Such companies are flagged, not dropped: the flag is a hint for a person to check.
"""

from __future__ import annotations

import re

SIC_LABELS = {
    "87100": "nursing care (residential)",
    "87200": "learning disability / mental health (residential)",
    "87300": "elderly and disabled (residential)",
    "87900": "other residential care",
    "88100": "domiciliary / social work without accommodation",
    # Codes often listed alongside the care codes.
    "78100": "employment agency",
    "78200": "temporary staffing agency",
    "78300": "other human resources provision",
    "85590": "other education",
    "85600": "educational support",
    "86101": "hospital",
    "86102": "medical nursing home",
    "86210": "GP practice",
    "86900": "other human health",
    "88910": "child day-care",
    "88990": "other social work without accommodation",
}

# (flag, words). A word matches whole words in the normalised name ("childrens" covers "children's").
NAME_FLAGS = (
    ("children's services (Ofsted, not CQC)",
     ("child", "children", "childrens", "kids", "youth", "young people", "foster", "fostering", "adolescent")),
    ("recruitment / staffing", ("recruitment", "recruiting", "staffing", "personnel", "locum", "locums")),
    ("training / consultancy", ("training", "academy", "consultancy", "consultants", "consulting")),
)


def _normalise(name: str) -> str:
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower().replace("'", "")).split()) + " "


def name_flag(name: str | None) -> str | None:
    """The first flag whose words appear in the company name, or None."""
    text = _normalise(name or "")
    for flag, words in NAME_FLAGS:
        if any(f" {w} " in text for w in words):
            return flag
    return None


def sic_labels(codes: str | list[str] | None) -> str:
    """"87300; 88100" -> "elderly and disabled (residential); domiciliary / ..." ("SIC n" if unknown)."""
    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(";")]
    return "; ".join(SIC_LABELS.get(c, f"SIC {c}") for c in codes or [] if c)
