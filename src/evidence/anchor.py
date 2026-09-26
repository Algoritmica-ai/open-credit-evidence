# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Anchoring: proof, outside anyone's control, that a test's files existed unchanged.

A test is sealed by ``checksums.sha256``, a SHA-256 for every file in it; the SHA-256 of
that file is the test's *seal*. Anyone who controls the files could re-seal them after a
change. Anchoring puts the seal where nobody can change it afterwards: the Bitcoin
blockchain, through OpenTimestamps (opentimestamps.org).

How it works:

1. The seal (32 bytes; no data leaves the machine) is mixed with a random nonce and sent
   to public OpenTimestamps calendars. Each answers at once with a *pending* proof.
2. A calendar gathers every hash it receives into a Merkle tree and writes the tree's
   root into one Bitcoin transaction, paying its fee. It costs us nothing.
3. Once the transaction is in a block, usually within a few hours, ``upgrade`` fetches
   the complete proof: the hash steps from the seal to that block's Merkle root.
4. ``verify`` recomputes those steps and compares the result with the block, as two
   public block explorers (or the bank's own node) report it. The proof then depends on
   nothing but Bitcoin: it proves the files existed, unchanged, no later than the block.

A test keeps changing after it is sealed (reviews, rulings, the feedback pack), and each
change re-seals it. So we anchor milestones: the test when it finishes, the feedback
pack when it is built. Each anchor keeps a copy of the file list it anchored, so later
anyone can check which files are unchanged since, and that none of the assistant's memos
or check results ever changed. The records form a chain, each naming the one before.

Everything lives in ``anchors/`` inside the test, outside its seal (a seal cannot hold
its own proof). The module is standalone: ``EVIDENCE_ANCHOR=off`` turns it off, and
without the ``opentimestamps`` package it does nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ANCHORS = "anchors"  # inside the test folder, outside its seal
CHECKSUMS = "checksums.sha256"
EXPLORERS = ("https://blockstream.info/api", "https://mempool.space/api")
# Files that never change once a test has run: the assistant's memos and what the checks
# found. Reviews, rulings and the feedback pack are added later, and are expected to.
PROTECTED = ("transcripts/", "results.jsonl", "manifest.json")
TIMEOUT = 15

Submit = Callable[[str, bytes], Any]  # (calendar url, digest) -> Timestamp
Fetch = Callable[[str, bytes], Any]  # (calendar url, commitment) -> Timestamp
Lookup = Callable[[int], dict[str, Any]]  # block height -> {hash, merkle_root, time, sources}


def enabled() -> bool:
    """Anchoring is on unless EVIDENCE_ANCHOR says off, and the library is installed."""
    if os.environ.get("EVIDENCE_ANCHOR", "on").strip().lower() in ("off", "0", "false", "no"):
        return False
    try:
        import opentimestamps  # noqa: F401
    except ImportError:
        return False
    return True


def calendars() -> list[str]:
    """Where seals are sent: EVIDENCE_ANCHOR_CALENDARS (comma-separated), else the public
    OpenTimestamps aggregators."""
    own = [u.strip() for u in os.environ.get("EVIDENCE_ANCHOR_CALENDARS", "").split(",")
           if u.strip()]
    if own:
        return own
    from opentimestamps.calendar import DEFAULT_AGGREGATORS

    return list(DEFAULT_AGGREGATORS)


def explorers() -> list[str]:
    own = [u.strip().rstrip("/") for u in
           os.environ.get("EVIDENCE_ANCHOR_EXPLORERS", "").split(",") if u.strip()]
    return own or list(EXPLORERS)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _link(rec: dict[str, Any]) -> str:
    """A record's fixed part, hashed: what the next record names as its predecessor."""
    fixed = {k: rec[k] for k in ("n", "what", "at", "seal", "previous")}
    return _sha256(json.dumps(fixed, sort_keys=True).encode())


def records(run: Path) -> list[dict[str, Any]]:
    """The test's anchor records, oldest first."""
    d = run / ANCHORS
    if not d.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(d.glob("[0-9][0-9][0-9].json"))]


def _write(run: Path, rec: dict[str, Any]) -> None:
    (run / ANCHORS / f"{rec['n']:03d}.json").write_text(
        json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ proofs


def _submit(url: str, digest: bytes) -> Any:
    from opentimestamps.calendar import RemoteCalendar

    return RemoteCalendar(url).submit(digest, timeout=TIMEOUT)


def _fetch(url: str, commitment: bytes) -> Any:
    from opentimestamps.calendar import RemoteCalendar

    return RemoteCalendar(url).get_timestamp(commitment, timeout=TIMEOUT)


def _nodes(ts: Any) -> Iterator[Any]:
    yield ts
    for child in ts.ops.values():
        yield from _nodes(child)


def _save_proof(path: Path, proof: Any) -> None:
    from opentimestamps.core.serialize import StreamSerializationContext

    with path.open("wb") as fh:
        proof.serialize(StreamSerializationContext(fh))


def _load_proof(path: Path) -> Any:
    from opentimestamps.core.serialize import StreamDeserializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile

    with path.open("rb") as fh:
        return DetachedTimestampFile.deserialize(StreamDeserializationContext(fh))


def _stamp(run: Path, rec: dict[str, Any], submit: Submit) -> None:
    """Send the seal to the calendars and keep the (pending) proof."""
    from opentimestamps.core.op import OpAppend, OpSHA256
    from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

    proof = DetachedTimestampFile(OpSHA256(), Timestamp(bytes.fromhex(rec["seal"])))
    # a random nonce first, so a calendar cannot tell which seal it was sent
    tip = proof.timestamp.ops.add(OpAppend(os.urandom(16))).ops.add(OpSHA256())
    ok, errors = [], {}
    for url in rec["calendars_asked"]:
        try:
            tip.merge(submit(url, tip.msg))
            ok.append(url)
        except Exception as exc:  # noqa: BLE001 — a calendar down is recorded, not fatal
            errors[url] = f"{type(exc).__name__}: {exc}"[:200]
    rec.update(calendars=ok, errors=errors)
    if ok:
        _save_proof(run / ANCHORS / f"{rec['n']:03d}.ots", proof)
        rec["status"] = "pending"
    else:
        rec["status"] = "failed"


def anchor(run: Path, what: str, *, submit: Submit | None = None,
           urls: list[str] | None = None) -> dict[str, Any] | None:
    """Anchor the test's current seal, labelled ``what`` ("test", "feedback-pack", ...).
    Returns the new record, the latest one if the seal has not changed since, or None when
    anchoring is off or the test is not sealed. Never raises for a network failure: the
    record says it failed, and ``upgrade`` tries again."""
    if submit is None and not enabled():
        return None
    sums = run / CHECKSUMS
    if not sums.is_file():
        return None
    data = sums.read_bytes()
    seal = _sha256(data)
    past = records(run)
    if past and past[-1]["seal"] == seal:
        return past[-1]  # nothing changed since the last anchor
    (run / ANCHORS).mkdir(exist_ok=True)
    n = (past[-1]["n"] + 1) if past else 1
    (run / ANCHORS / f"{n:03d}-{CHECKSUMS}").write_bytes(data)
    rec: dict[str, Any] = {
        "n": n, "what": what, "at": _now(), "seal": seal,
        "previous": _link(past[-1]) if past else None,
        "files": len(data.decode("utf-8").splitlines()),
        "calendars_asked": list(urls or calendars()),
        "status": "failed", "bitcoin": None,
    }
    _stamp(run, rec, submit or _submit)
    _write(run, rec)
    return rec


def _bitcoin(proof: Any) -> tuple[int, bytes] | None:
    from opentimestamps.core.notary import BitcoinBlockHeaderAttestation

    found = [(att.height, msg) for msg, att in proof.timestamp.all_attestations()
             if isinstance(att, BitcoinBlockHeaderAttestation)]
    return min(found) if found else None  # the earliest block is the strongest claim


def upgrade(run: Path, *, fetch: Fetch | None = None, submit: Submit | None = None,
            lookup: Lookup | None = None) -> list[dict[str, Any]]:
    """Fetch the complete proof for every pending anchor, and send again any that failed.
    Returns the records that changed."""
    from opentimestamps.calendar import DEFAULT_CALENDAR_WHITELIST
    from opentimestamps.core.notary import PendingAttestation

    changed = []
    trusted = set(calendars())
    for rec in records(run):
        if rec["status"] == "failed":
            _stamp(run, rec, submit or _submit)
            if rec["status"] != "failed":
                _write(run, rec)
                changed.append(rec)
            continue
        if rec["status"] != "pending":
            continue
        path = run / ANCHORS / f"{rec['n']:03d}.ots"
        proof = _load_proof(path)
        for node in list(_nodes(proof.timestamp)):
            for att in list(node.attestations):
                # only calendars we know: a proof file must not make us call anywhere else
                if not isinstance(att, PendingAttestation) or not (
                        att.uri in DEFAULT_CALENDAR_WHITELIST or att.uri in trusted):
                    continue
                try:
                    node.merge((fetch or _fetch)(att.uri, node.msg))
                except Exception:  # noqa: BLE001 — not in a block yet, or the calendar is down
                    continue
        block = _bitcoin(proof)
        if block:
            _save_proof(path, proof)
            height, msg = block
            rec["status"] = "confirmed"
            rec["bitcoin"] = {"height": height, "merkle_root": msg[::-1].hex()}
            try:
                b = (lookup or _lookup)(height)
                rec["bitcoin"].update(block=b["hash"], time=b["time"])
            except Exception:  # noqa: BLE001 — the block's time is filled in by verify
                pass
            rec["confirmed_at"] = _now()
            _write(run, rec)
            changed.append(rec)
    return changed


# ------------------------------------------------------------------ checking


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "credit-evidence-engine"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — fixed https hosts
        return r.read()


def _lookup(height: int) -> dict[str, Any]:
    """The block at ``height`` as every reachable explorer reports it; they must agree."""
    seen = []
    for api in explorers():
        try:
            h = _get(f"{api}/block-height/{height}").decode().strip()
            b = json.loads(_get(f"{api}/block/{h}"))
            seen.append({"hash": h, "merkle_root": b["merkle_root"],
                         "time": datetime.fromtimestamp(b["timestamp"], UTC)
                         .isoformat(timespec="seconds"), "source": api})
        except Exception:  # noqa: BLE001 — try the next explorer
            continue
    if not seen:
        raise OSError("no block explorer reachable")
    if len({(s["hash"], s["merkle_root"]) for s in seen}) > 1:
        raise ValueError(f"block explorers disagree about block {height}")
    return seen[0] | {"sources": [s["source"] for s in seen]}


def _sums(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            out[name] = digest
    return out


def verify(run: Path, *, lookup: Lookup | None = None) -> dict[str, Any]:
    """Check every anchor: its copy of the file list is the seal it anchored, the chain is
    unbroken, the proof reaches the Bitcoin block it names, and no memo or check result
    has changed since. ``ok`` is False only when something is wrong; an anchor still
    waiting for Bitcoin, or an explorer out of reach, is reported but not a failure."""
    recs = records(run)
    current = _sums((run / CHECKSUMS).read_text(encoding="utf-8")) if (
        run / CHECKSUMS).is_file() else {}
    out, ok = [], True
    for i, rec in enumerate(recs):
        n = f"{rec['n']:03d}"
        problems: list[str] = []
        copy = run / ANCHORS / f"{n}-{CHECKSUMS}"
        if not copy.is_file() or _sha256(copy.read_bytes()) != rec["seal"]:
            problems.append("its copy of the file list is missing or does not match the seal")
        if rec["previous"] != (_link(recs[i - 1]) if i else None):
            problems.append("the chain of anchors is broken before it")
        block = None
        if rec["status"] in ("pending", "confirmed"):
            path = run / ANCHORS / f"{n}.ots"
            try:
                proof = _load_proof(path)
                if proof.file_digest.hex() != rec["seal"]:
                    problems.append("its proof is for a different seal")
                found = _bitcoin(proof)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"its proof cannot be read ({type(exc).__name__})")
                found = None
            if found:
                height, msg = found
                try:
                    b = (lookup or _lookup)(height)
                    if b["merkle_root"] != msg[::-1].hex():
                        problems.append(f"its proof does not match Bitcoin block {height}")
                    else:
                        block = {"height": height, "hash": b["hash"], "time": b["time"],
                                 "sources": b.get("sources", [])}
                except Exception as exc:  # noqa: BLE001
                    block = {"height": height, "unchecked": str(exc)[:120]}
        then = _sums(copy.read_text(encoding="utf-8")) if copy.is_file() else {}
        unchanged = sorted(k for k in then if current.get(k) == then[k])
        changed = sorted(k for k in then if k in current and current[k] != then[k])
        removed = sorted(k for k in then if k not in current)
        added = sorted(k for k in current if k not in then)
        broken = [k for k in changed + removed if k.startswith(PROTECTED)]
        if broken:
            problems.append(f"{len(broken)} memo or check-result file(s) changed since: "
                            + ", ".join(broken[:5]))
        state = ("broken" if problems else
                 "confirmed" if block and "unchecked" not in block else
                 "confirmed-unchecked" if block else rec["status"])
        ok = ok and not problems
        out.append({"n": rec["n"], "what": rec["what"], "at": rec["at"], "seal": rec["seal"],
                    "state": state, "block": block, "problems": problems,
                    "unchanged": len(unchanged), "changed": changed, "added": added,
                    "removed": removed})
    return {"ok": ok, "anchors": out, "message": _message(out)}


def _message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Not anchored."
    bad = [r for r in rows if r["state"] == "broken"]
    if bad:
        return f"Anchor {bad[0]['n']} fails: {bad[0]['problems'][0]}."
    done = [r for r in rows if r["block"] and "time" in r["block"]]
    waiting = [r for r in rows if r["state"] == "pending"]
    parts = []
    if done:
        b = done[-1]["block"]
        parts.append(f"anchored in Bitcoin block {b['height']:,} ({b['time']})")
    if waiting:
        parts.append(f"{len(waiting)} waiting for Bitcoin")
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + "." if parts else "Anchors not yet checked."


def status(run: Path) -> list[dict[str, Any]]:
    """The anchors as recorded, without any network: for the UI."""
    return [{k: r.get(k) for k in ("n", "what", "at", "seal", "status", "bitcoin",
                                   "calendars", "confirmed_at")} for r in records(run)]
