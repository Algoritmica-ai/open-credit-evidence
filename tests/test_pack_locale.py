"""The German case file carries no British details, and localising changes no answer."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRITISH = ("CCJ", "Northgate", "Postcode district", "£", "B15", "M14", "CF24", "Harrow Estates")


def _items(pack: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / "packs" / pack / "items.jsonl").open()]


def test_german_case_files_have_no_british_details():
    for item in _items("underwriter-de"):
        text = "\n".join(c["content"] for c in item["context"])
        found = [w for w in BRITISH if w in text]
        assert not found, f"{item['item_id']}: {found}"
        assert "Rheinland Kreditauskunft" in text and "Debtor register entries" in text


def test_german_and_sample_packs_share_the_marking_key():
    for a, b in zip(_items("underwriter-sample"), _items("underwriter-de"), strict=True):
        ga, gb = a["grading"], b["grading"]
        assert ga["disposition"] == gb["disposition"]
        for key in ("driver_refs", "decoy_refs", "omission_refs", "flip_refs", "driver_labels"):
            assert ga[key] == gb[key], (a["item_id"], key)
