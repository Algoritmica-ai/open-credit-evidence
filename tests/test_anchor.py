# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Anchoring a run's seal in Bitcoin, with a fake calendar and a fake block explorer."""

import json
import shutil

import pytest

pytest.importorskip("opentimestamps")

from opentimestamps.core.notary import (  # noqa: E402
    BitcoinBlockHeaderAttestation,
    PendingAttestation,
)
from opentimestamps.core.op import OpAppend, OpSHA256  # noqa: E402
from opentimestamps.core.timestamp import Timestamp  # noqa: E402

from evidence import anchor  # noqa: E402
from evidence.evidence.verify import verify_run  # noqa: E402
from evidence.evidence.writer import seal  # noqa: E402

HEIGHT = 915_000


def _submit(url, digest):
    """A calendar: commits to the digest and promises a Bitcoin attestation later."""
    ts = Timestamp(digest)
    tip = ts.ops.add(OpAppend(b"calendar")).ops.add(OpSHA256())
    tip.attestations.add(PendingAttestation("https://alice.btc.calendar.opentimestamps.org"))
    return ts


def _fetch(url, commitment):
    """The same calendar, hours later: the commitment is now in block HEIGHT."""
    ts = Timestamp(commitment)
    ts.ops.add(OpAppend(b"block")).ops.add(OpSHA256()).attestations.add(
        BitcoinBlockHeaderAttestation(HEIGHT))
    return ts


def _down(url, digest):
    raise OSError("calendar unreachable")


def _offline(height):
    raise OSError("no block explorer reachable")


def _explorer(run):
    """A block explorer that reports block HEIGHT with the Merkle root the proof reaches."""
    def lookup(height):
        rec = next(r for r in anchor.records(run) if r["bitcoin"])
        return {"hash": "00" * 32, "merkle_root": rec["bitcoin"]["merkle_root"],
                "time": "2026-09-26T14:02:00+00:00", "sources": ["fake"]}
    return lookup


@pytest.fixture
def run(tmp_path):
    r = tmp_path / "run"
    (r / "transcripts").mkdir(parents=True)
    (r / "transcripts" / "a-r0.json").write_text('{"output": "memo"}')
    (r / "results.jsonl").write_text('{"passed": true}\n')
    (r / "manifest.json").write_text("{}")
    seal(r)
    return r


def test_a_seal_is_anchored_then_confirmed_in_a_bitcoin_block(run):
    two = ["https://a.example", "https://b.example"]
    rec = anchor.anchor(run, "test", submit=_submit, urls=two)
    assert rec["status"] == "pending" and rec["calendars"] == two
    assert (run / "anchors" / "001.ots").is_file()
    assert (run / "anchors" / "001-checksums.sha256").is_file()
    assert verify_run(run).ok  # the anchors sit outside the seal
    assert anchor.verify(run)["anchors"][0]["state"] == "pending"
    # nothing changed since: the same anchor, not a new one
    assert anchor.anchor(run, "test", submit=_submit, urls=["https://a.example"])["n"] == 1

    changed = anchor.upgrade(run, fetch=_fetch, lookup=_offline)
    assert [r["status"] for r in changed] == ["confirmed"]
    assert changed[0]["bitcoin"]["height"] == HEIGHT
    res = anchor.verify(run, lookup=_explorer(run))
    row = res["anchors"][0]
    assert res["ok"] and row["state"] == "confirmed" and row["block"]["height"] == HEIGHT
    assert row["unchanged"] == 3 and "915,000" in res["message"]


def test_later_milestones_chain_and_expected_changes_are_not_failures(run):
    anchor.anchor(run, "test", submit=_submit, urls=["https://a.example"])
    (run / "review").mkdir()
    (run / "review" / "records.jsonl").write_text('{"memo": "a"}\n')
    seal(run)
    second = anchor.anchor(run, "feedback-pack", submit=_submit, urls=["https://a.example"])
    first = anchor.records(run)[0]
    assert second["n"] == 2 and second["previous"] == anchor._link(first)
    res = anchor.verify(run)
    assert res["ok"] and res["anchors"][0]["added"] == ["review/records.jsonl"]


def test_a_changed_memo_or_a_broken_chain_fails(run):
    anchor.anchor(run, "test", submit=_submit, urls=["https://a.example"])
    (run / "transcripts" / "a-r0.json").write_text('{"output": "a different memo"}')
    seal(run)  # re-sealed after the change: the seal alone would not show it
    res = anchor.verify(run)
    assert not res["ok"] and "transcripts/a-r0.json" in res["anchors"][0]["problems"][0]

    rec = json.loads((run / "anchors" / "001.json").read_text())
    rec["seal"] = "0" * 64
    (run / "anchors" / "001.json").write_text(json.dumps(rec))
    assert "does not match the seal" in anchor.verify(run)["anchors"][0]["problems"][0]


def test_calendars_down_is_recorded_and_retried_never_raised(run):
    rec = anchor.anchor(run, "test", submit=_down, urls=["https://a.example"])
    assert rec["status"] == "failed" and "unreachable" in rec["errors"]["https://a.example"]
    assert anchor.verify(run)["ok"]  # not yet anchored is not a failure
    again = anchor.upgrade(run, submit=_submit)
    assert [r["status"] for r in again] == ["pending"]


def test_a_proof_that_does_not_reach_the_block_fails(run):
    anchor.anchor(run, "test", submit=_submit, urls=["https://a.example"])
    anchor.upgrade(run, fetch=_fetch, lookup=_offline)
    wrong = lambda h: {"hash": "00", "merkle_root": "ff" * 32, "time": "t"}  # noqa: E731
    res = anchor.verify(run, lookup=wrong)
    assert not res["ok"] and "does not match Bitcoin block" in res["anchors"][0]["problems"][0]


def test_off_means_off(run, monkeypatch):
    monkeypatch.setenv("EVIDENCE_ANCHOR", "off")
    assert not anchor.enabled() and anchor.anchor(run, "test") is None
    assert not (run / "anchors").exists()


def test_a_copy_of_a_run_verifies_with_its_anchors(run, tmp_path):
    anchor.anchor(run, "test", submit=_submit, urls=["https://a.example"])
    copy = tmp_path / "copy"
    shutil.copytree(run, copy)
    assert verify_run(copy).ok and anchor.verify(copy)["ok"]
    assert (copy / "anchors" / "001.ots").read_bytes() == (run / "anchors" / "001.ots").read_bytes()


def test_an_explorer_that_stalls_does_not_hold_up_the_check(monkeypatch):
    import threading
    import time as _time

    stalled = threading.Event()

    def block(api, height):
        if "slow" in api:
            stalled.wait(30)  # accepts the connection, then never answers
        return {"hash": "00", "merkle_root": "ab", "time": "t", "source": api}

    monkeypatch.setattr(anchor, "_block", block)
    monkeypatch.setenv("EVIDENCE_ANCHOR_EXPLORERS", "https://slow.example,https://fast.example")
    t0 = _time.monotonic()
    b = anchor._lookup(1, deadline=1.0)
    assert _time.monotonic() - t0 < 5 and b["sources"] == ["https://fast.example"]
    stalled.set()
