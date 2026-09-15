"""Structural tests for jurisdiction regulation registries."""

import json
import re
from pathlib import Path
from typing import Any

REGISTRY_ROOT = Path("docs/regulations/jurisdictions")
ID_PATTERN = re.compile(r"^[A-Z]{2}-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
ALLOWED_STATUSES = {"in_force", "transition", "conditional", "deprecated"}
ALLOWED_RELATIONSHIPS = {"direct", "supporting", "context_only"}
ALLOWED_FINOS_CONTROLS = {
    "FINOS-AIGF-MI-1",
    "FINOS-AIGF-MI-4",
    "FINOS-AIGF-MI-5",
    "FINOS-AIGF-MI-11",
}


def load_registries() -> list[tuple[Path, dict[str, Any]]]:
    """Load every country registry from the documentation tree."""
    registry_paths = sorted(REGISTRY_ROOT.glob("*/registry.json"))
    assert registry_paths, "At least one jurisdiction registry is required"
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in registry_paths]


def test_regulatory_ids_are_unique_and_match_country() -> None:
    """IDs are stable, globally unique, and prefixed with their ISO country code."""
    seen: set[str] = set()
    for path, registry in load_registries():
        country = registry["jurisdiction"]["code"]
        assert path.parent.name == country
        assert registry["schema_version"] == "1.0"
        for entry in registry["entries"]:
            regulation_id = entry["id"]
            assert ID_PATTERN.fullmatch(regulation_id)
            assert regulation_id.startswith(f"{country}-")
            assert regulation_id not in seen, f"Duplicate regulation ID: {regulation_id}"
            seen.add(regulation_id)


def test_regulatory_entries_have_linkable_evidence_metadata() -> None:
    """Every entry carries the fields needed by an evidence report and control mapping."""
    required = {
        "id",
        "title",
        "citation",
        "category",
        "status",
        "applicability",
        "obligation",
        "open_credit_relationship",
        "open_credit_evidence",
        "finos_controls",
        "eu_ai_act_refs",
        "official_sources",
    }
    for _, registry in load_registries():
        for entry in registry["entries"]:
            assert required <= entry.keys()
            assert entry["status"] in ALLOWED_STATUSES
            assert entry["open_credit_relationship"] in ALLOWED_RELATIONSHIPS
            assert set(entry["finos_controls"]) <= ALLOWED_FINOS_CONTROLS
            assert entry["official_sources"]
            for source in entry["official_sources"]:
                assert source["url"].startswith("https://")
                assert source["label"]
                assert source["publisher"]
