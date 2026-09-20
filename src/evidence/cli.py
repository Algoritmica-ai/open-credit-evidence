# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""``evidence`` — run a pack, write the evidence pack, verify it.

evidence run packs/underwriter-sample --repeats 3 --out runs/2026-10-07
evidence report runs/2026-10-07
evidence verify runs/2026-10-07 [--recompute --pack packs/underwriter-sample]
evidence rules packs/underwriter-sample
evidence checks
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from evidence.checks import available_checks
from evidence.evidence import verify_run, write_evidence
from evidence.pack import load_pack
from evidence.regulations import assess
from evidence.runner import run_pack


def _cmd_run(a: argparse.Namespace) -> int:
    pack = load_pack(a.pack)
    for w in pack.warnings:
        print(f"warning: {w}", file=sys.stderr)
    out = Path(a.out) if a.out else Path("runs") / datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    checks = a.checks.split(",") if a.checks else None
    print(f"pack     {pack.pack_id} v{pack.version}  {len(pack.items)} items")
    print(f"checks   {', '.join(checks or pack.checks_declared())}")
    print(f"repeats  {a.repeats}   judge {'on' if not a.no_judge else 'off'}   out {out}")
    manifest = run_pack(
        pack, out, repeats=a.repeats, checks=checks, judge=not a.no_judge, limit=a.limit
    )
    print(f"sut      {manifest['sut']['model_id']}  {manifest['sut']['endpoint']}")
    res = write_evidence(out, pack.obligations)
    print(f"sealed   {res['files_sealed']} files -> {out / 'checksums.sha256'}")
    _print_summary(res["summary"], manifest["repeats"])
    print(f"report   {out / 'evidence' / 'report.md'}")
    return 0


def _print_summary(summary: dict, repeats: int) -> None:
    print()
    print(
        f"{'check':20} {'pass':>7} {'fail':>6} {'audit':>6}  {'agreement' if repeats > 1 else ''}"
    )
    for name, c in summary["checks"].items():
        if c["gated"]:
            agree = summary["repeat_agreement"].get(name, {})
            ag = f"{agree.get('stable', '')}/{agree.get('items', '')}" if repeats > 1 else ""
            print(f"{name:20} {c['passed']:>7} {c['failed']:>6} {c['needs_audit']:>6}  {ag}")
        else:
            print(f"{name:20} {'mean ' + str(c['mean_value']):>14}  (reported, not gated)")
    print()


def _cmd_report(a: argparse.Namespace) -> int:
    path = Path(a.run) / "evidence" / "report.md"
    if not path.is_file():
        print(f"{path} not found", file=sys.stderr)
        return 1
    sys.stdout.write(path.read_text(encoding="utf-8"))
    return 0


def _cmd_verify(a: argparse.Namespace) -> int:
    pack = load_pack(a.pack) if a.pack else None
    if a.recompute and pack is None:
        print("--recompute needs --pack", file=sys.stderr)
        return 2
    v = verify_run(Path(a.run), pack, recompute=a.recompute)
    print(v.message + ("   OK" if v.ok else "   FAIL"))
    for d in v.disagreements[:20]:
        print(f"  {d}")
    return 0 if v.ok else 1


def _cmd_rules(a: argparse.Namespace) -> int:
    pack = load_pack(a.pack)
    r = assess(pack.regulatory_context)
    print(
        f"{r.status}  {r.ruleset_id or '-'} v{r.ruleset_version or '-'}  "
        f"jurisdiction {r.jurisdiction or '-'}"
    )
    for f in r.findings:
        extra = f"  missing: {', '.join(f.missing_evidence)}" if f.missing_evidence else ""
        print(f"  {f.status:15} {f.rule_id:34} {f.title}{extra}")
    print(r.note)
    return 0 if r.status in ("pass", "unscoped") else 1


def _cmd_checks(_: argparse.Namespace) -> int:
    for name in available_checks():
        print(name)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evidence", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a pack against the assistant and write the evidence pack")
    r.add_argument("pack")
    r.add_argument("--out", help="run directory (default runs/<timestamp>)")
    r.add_argument("--repeats", type=int, default=1)
    r.add_argument("--checks", help="comma-separated; default: what each item declares")
    r.add_argument("--no-judge", action="store_true", help="skip the readability judge")
    r.add_argument("--limit", type=int, help="only the first N items")
    r.set_defaults(fn=_cmd_run)

    p = sub.add_parser("report", help="print evidence/report.md for a run")
    p.add_argument("run")
    p.set_defaults(fn=_cmd_report)

    v = sub.add_parser("verify", help="re-check a run's checksums, optionally re-derive results")
    v.add_argument("run")
    v.add_argument("--recompute", action="store_true")
    v.add_argument("--pack")
    v.set_defaults(fn=_cmd_verify)

    u = sub.add_parser("rules", help="evaluate the jurisdiction rule pack for a pack's context")
    u.add_argument("pack")
    u.set_defaults(fn=_cmd_rules)

    c = sub.add_parser("checks", help="list registered deterministic checks")
    c.set_defaults(fn=_cmd_checks)

    a = ap.parse_args(argv)
    return int(a.fn(a))


if __name__ == "__main__":
    sys.exit(main())
