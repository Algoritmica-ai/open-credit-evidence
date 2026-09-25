# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""``evidence`` — run a pack, write the evidence pack, verify it.

evidence run packs/underwriter-sample --repeats 3 --out runs/2026-10-07
evidence report runs/2026-10-07 [--rewrite --thresholds bank_thresholds.yaml] [--for business]
evidence verify runs/2026-10-07 [--recompute --pack packs/underwriter-sample]
evidence export runs/2026-10-07 [--doc business] [--out exports/today]
evidence compare runs/before runs/after
evidence rules packs/underwriter-sample
evidence checks
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence.checks import available_checks
from evidence.evidence import verify_run, write_evidence
from evidence.evidence.readers import READERS
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
        pack,
        out,
        repeats=a.repeats,
        checks=checks,
        judge=not a.no_judge,
        limit=a.limit,
        corpus=None if a.corpus == "none" else a.corpus,
    )
    print(f"sut      {manifest['sut']['model_id']}  {manifest['sut']['endpoint']}")
    res = write_evidence(out, pack.obligations)
    print(f"sealed   {res['files_sealed']} files -> {out / 'checksums.sha256'}")
    _print_summary(res["summary"], manifest["repeats"])
    _print_decision(out)
    print(f"report   {out / 'evidence' / 'report.md'}")
    return 0


def _print_decision(run: Path) -> None:
    import json

    ev = run / "evidence"
    d = json.loads((ev / "decision.json").read_text(encoding="utf-8"))
    recs = json.loads((ev / "recommendations.json").read_text(encoding="utf-8"))
    print(f"decision {d['verdict']}")
    for c in d["conditions"][:3]:
        print(f"         - {c}")
    if recs:
        r = recs[0]
        a = r["addresses"]
        print(f"change   {r['title']} ({a['briefings']} briefings, {a['results']} failing "
              f"results, {r['owner']} can act)")


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
    if a.rewrite:
        import yaml

        thresholds = yaml.safe_load(Path(a.thresholds).read_text()) if a.thresholds else None
        res = write_evidence(Path(a.run), thresholds=thresholds)
        print(f"rewrote  evidence/ and re-sealed {res['files_sealed']} files", file=sys.stderr)
    path = Path(a.run) / "evidence" / (f"readers/{a.reader}.md" if a.reader else "report.md")
    if not path.is_file():
        print(f"{path} not found", file=sys.stderr)
        return 1
    sys.stdout.write(path.read_text(encoding="utf-8"))
    return 0


def _cmd_export(a: argparse.Namespace) -> int:
    from evidence.evidence.export import DOCUMENTS, export_run

    run = Path(a.run)
    out = Path(a.out) if a.out else Path("exports") / run.name
    res = export_run(run, out, a.doc or list(DOCUMENTS), pdf=not a.html)
    for path in res["written"]:
        print(path)
    print(f"seal     {res['seal']}  (SHA-256 of {run / 'checksums.sha256'})")
    if not res["pdf"] and not a.html:
        print("no Chrome or Chromium found (set EVIDENCE_CHROME): wrote HTML; print it to PDF "
              "from a browser", file=sys.stderr)
    return 0


def _cmd_verify(a: argparse.Namespace) -> int:
    pack = load_pack(a.pack) if a.pack else None
    if a.recompute and pack is None:
        print("--recompute needs --pack", file=sys.stderr)
        return 2
    v = verify_run(Path(a.run), pack, recompute=a.recompute)
    print(v.message + ("   OK" if v.ok else "   FAIL"))
    for d in (v.disagreements + v.derived)[:20]:
        print(f"  {d}")
    return 0 if v.ok else 1


def _cmd_compare(a: argparse.Namespace) -> int:
    import json

    from evidence.evidence.compare import compare_runs

    c = compare_runs(Path(a.before), Path(a.after))
    if a.json:
        print(json.dumps(c, indent=2))
        return 0
    for w in c["warnings"]:
        print(f"warning  {w}")
    print(f"{c['before']['run_id']} -> {c['after']['run_id']}: {c['verdict']}")
    for ch in c["changed"] or [{"what": "nothing recorded in the manifests", "before": "",
                                "after": ""}]:
        print(f"changed  {ch['what']}: {ch['before']} -> {ch['after']}")
    for r in c["checks"]:
        if r["status"] == "not_comparable":
            continue
        print(f"  {r['check']:20} {r['before']:>6.0%} -> {r['after']:>5.0%}  "
              f"{r['change'] * 100:+4.0f} pts [{r['interval'][0] * 100:+.0f}, "
              f"{r['interval'][1] * 100:+.0f}]  helped {r['helped']:2} hurt {r['hurt']:2}  "
              f"{r['status'].replace('_', ' ')}")
    return 0


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


def _cmd_ui(a: argparse.Namespace) -> int:
    if a.root:
        import os

        os.environ["EVIDENCE_ROOT"] = str(Path(a.root).resolve())
    try:
        from evidence.web.app import serve
    except ImportError:
        print("the web UI needs the [web] extra: pip install -e '.[web]'", file=sys.stderr)
        return 2
    print(f"Credit Evidence Engine UI on http://{a.host}:{a.port}  (Ctrl-C to stop)")
    serve(a.host, a.port)
    return 0


def _html_text(html: str) -> str:
    """The text of a saved web page, words inside inline markup kept together."""
    from html.parser import HTMLParser

    inline = {"a", "b", "i", "em", "strong", "span", "sup", "sub", "u", "abbr"}

    class _Text(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.out: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag: str, attrs: Any) -> None:
            self.skip += tag in ("script", "style")
            if tag not in inline:
                self.out.append(" ")

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style") and self.skip:
                self.skip -= 1
            if tag not in inline:
                self.out.append(" ")

        def handle_data(self, data: str) -> None:
            if not self.skip:
                self.out.append(data)

    p = _Text()
    p.feed(html)
    return "".join(p.out)


def _cmd_corpus(a: argparse.Namespace) -> int:
    from evidence.corpus import build_corpus, list_corpora, verify_sources

    if a.action == "verify-sources":
        if not a.official:
            print("verify-sources needs --official <saved official text>", file=sys.stderr)
            return 2
        import hashlib

        paths = [Path(x) for x in a.official]
        ids, urls = a.official_id or [], a.official_url or []
        texts, docs = [], []
        for i, path in enumerate(paths):
            raw = path.read_text(encoding="utf-8", errors="replace")
            texts.append(_html_text(raw) if path.suffix.lower() in (".html", ".htm") else raw)
            docs.append({"id": ids[i] if i < len(ids) else path.name,
                         "url": urls[i] if i < len(urls) else None, "file": path.name,
                         "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        rec = verify_sources(a.jurisdiction, "\n\n".join(texts), official={
            "id": " + ".join(d["id"] for d in docs), "documents": docs,
            "obtained": a.obtained or "saved copy, read by evidence corpus verify-sources"})
        sha = rec["official"]["text_sha256"][:12]
        print(f"{rec['jurisdiction']}: {rec['found']}/{rec['passages']} passages found verbatim "
              f"in {rec['official']['id']} (text sha256 {sha}…)")
        for r in rec["results"]:
            if not r["found"]:
                print(f"  {r['passage_id']}: matches {r['matches_up_to']}/{r['of']} characters, "
                      f"then differs: …{r['diverges_at']}…")
        return 0 if rec["found"] == rec["passages"] else 1
    if a.action == "build":
        m = build_corpus(a.jurisdiction)
        print(
            f"{m['jurisdiction']}: {m['passages']} passages from {len(m['sources'])} source(s), "
            f"embed {m['embed_model']}, corpus sha256 {m['corpus_sha256'][:12]}…"
        )
        for src in m["sources"]:
            print(f"  {src['id']:24} {src['passages']:3} passages  {src['citation']}")
        return 0
    for c in list_corpora():
        state = (
            f"built: {c['passages']} passages, sha {c['corpus_sha256'][:12]}…"
            if c["built"]
            else "not built"
        )
        print(f"{c['jurisdiction']:4} {c['sources']} source(s)  {state}  — {c['title']}")
        sc = c.get("source_check")
        if sc:
            print(f"     checked against {sc['official']} on {sc['checked_at'][:10]}: "
                  f"{sc['found']}/{sc['passages']} passages as they are now"
                  + (f"; unchecked {', '.join(sc['unchecked'])}" if sc["unchecked"] else ""))
    return 0


def _cmd_panel(a: argparse.Namespace) -> int:
    from evidence import panel_run
    from evidence.corpus import Corpus
    from evidence.evidence import write_evidence

    run = Path(a.run)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    pack = load_pack(a.pack or Path("packs") / manifest["pack"]["pack_id"])
    corpus = None
    if a.corpus != "none":
        corpus = Corpus(a.corpus or ((manifest.get("judge") or {}).get("corpus") or {}).get(
            "jurisdiction") or "EU")
        ec = corpus.check_embedder()
        if not ec["ok"]:
            print(f"the embedder does not reproduce the {corpus.jurisdiction} index (cosine "
                  f"{ec['cosine']}); rebuild it first", file=sys.stderr)
            return 1
    bundles, facts = panel_run.bundles(run, pack, corpus, limit=a.limit)
    done = set() if a.redo else panel_run.done_keys(run)
    todo = [b for b in bundles if (b["item_id"], b["repeat"]) not in done]
    if done:
        print(f"panel: {len(bundles) - len(todo)} of {len(bundles)} briefings already done; "
              f"{len(todo)} to go (--redo to start over)")
    if a.redo and (run / "panel").is_dir():
        shutil.rmtree(run / "panel")
    started = datetime.now(UTC).isoformat(timespec="seconds")
    running = {"kind": a.runtime, "status": "running"}

    def sink(recs: list[dict[str, Any]]) -> None:  # finished briefings, as they arrive
        panel_run.record(run, recs, facts, running, started, complete=False)

    runner = panel_run.run_nemoclaw if a.runtime == "nemoclaw" else panel_run.run_direct
    try:
        records, runtime = runner(todo, workers=a.workers, log=print, sink=sink) if todo \
            else ([], {"kind": a.runtime})
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        m = panel_run.record(run, [], facts, running | {"status": f"stopped: {exc}"}, started,
                             complete=False)
        write_evidence(run)  # the run stays sealed and verifiable with a partial panel
        print(f"panel stopped: {exc}\n{m['briefings']} of {m['planned']} briefings are in "
              f"{run / 'panel'}; run the same command again to finish", file=sys.stderr)
        return 1
    finished = panel_run.done_keys(run) | {(r["item_id"], r["repeat"]) for r in records
                                           if not r.get("error")}
    m = panel_run.record(run, records, facts, runtime, started,
                         complete=len(finished) >= len(bundles))
    out = write_evidence(run)
    print(f"panel: {m['briefings']} briefings recorded ({m['errors']} errors, "
          f"{len(finished)}/{len(bundles)} done) in {run / 'panel'}; evidence rebuilt and "
          f"{out['files_sealed']} files sealed")
    print(f"report {run / 'evidence' / 'panel.md'}")
    return 0


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
    r.add_argument(
        "--corpus",
        default="EU",
        help="regulation corpus the judge retrieves from (jurisdiction code, or 'none')",
    )
    r.set_defaults(fn=_cmd_run)

    p = sub.add_parser("report", help="print evidence/report.md for a run")
    p.add_argument("run")
    p.add_argument("--rewrite", action="store_true",
                   help="rebuild evidence/ from the results first (no model calls) and re-seal")
    p.add_argument("--thresholds", help="with --rewrite: the bank's thresholds.yaml")
    p.add_argument("--for", dest="reader", choices=list(READERS),
                   help="print one reader's report instead of the full report.md")
    p.set_defaults(fn=_cmd_report)

    cp = sub.add_parser("compare", help="did a change help? two runs, case by case")
    cp.add_argument("before")
    cp.add_argument("after")
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(fn=_cmd_compare)

    x = sub.add_parser("export", help="the run's reports as PDF, with timestamps and checksums")
    x.add_argument("run")
    x.add_argument("--out", help="directory (default exports/<run>); never inside the run")
    x.add_argument("--doc", action="append",
                   choices=["business", "credit-risk", "compliance", "operations", "vendor",
                            "auditor", "full"],
                   help="one document; repeat for several (default: all seven)")
    x.add_argument("--html", action="store_true", help="write HTML only, no PDF")
    x.set_defaults(fn=_cmd_export)

    v = sub.add_parser("verify", help="re-check a run's checksums, optionally re-derive results")
    v.add_argument("run")
    v.add_argument("--recompute", action="store_true")
    v.add_argument("--pack")
    v.set_defaults(fn=_cmd_verify)

    u = sub.add_parser("rules", help="evaluate the jurisdiction rule pack for a pack's context")
    u.add_argument("pack")
    u.set_defaults(fn=_cmd_rules)

    k = sub.add_parser("corpus", help="build, list or verify regulation corpora for the judge")
    k.add_argument("action", choices=["build", "list", "verify-sources"])
    k.add_argument("jurisdiction", nargs="?", default="EU")
    k.add_argument("--official", action="append",
                   help="verify-sources: saved official text (.html or .txt); repeat for a "
                   "corpus drawn from several instruments")
    k.add_argument("--official-id", action="append",
                   help="verify-sources: each document's id, e.g. a CELEX number, in order")
    k.add_argument("--official-url", action="append",
                   help="verify-sources: where each was obtained, in order")
    k.add_argument("--obtained", help="verify-sources: how the saved texts were obtained and "
                   "any processing (e.g. PDF text with page numbers removed)")
    k.set_defaults(fn=_cmd_corpus)

    pn = sub.add_parser("panel", help="three-agent judge panel over a finished run "
                        "(reported, never gated)")
    pn.add_argument("run")
    pn.add_argument("--runtime", choices=["direct", "nemoclaw"], default="direct",
                    help="direct: here, on the judge endpoint; nemoclaw: inside the NemoClaw "
                    "sandbox on the node (EVIDENCE_PANEL_SSH='<login host> <node>')")
    pn.add_argument("--pack", help="pack directory (default packs/<pack id of the run>)")
    pn.add_argument("--corpus", help="regulation corpus (default: the run judge's; 'none')")
    pn.add_argument("--limit", type=int, help="only the first N items")
    pn.add_argument("--workers", type=int, default=4, help="briefings reviewed at once")
    pn.add_argument("--redo", action="store_true",
                    help="discard the run's panel records and start over (default: resume)")
    pn.set_defaults(fn=_cmd_panel)

    w = sub.add_parser("ui", help="serve the local web UI")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8765)
    w.add_argument("--root", help="directory holding packs/ and runs/ (default: current)")
    w.set_defaults(fn=_cmd_ui)

    c = sub.add_parser("checks", help="list registered deterministic checks")
    c.set_defaults(fn=_cmd_checks)

    a = ap.parse_args(argv)
    return int(a.fn(a))


if __name__ == "__main__":
    sys.exit(main())
