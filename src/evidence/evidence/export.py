# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Export a run's reports as print-ready HTML and PDF.

The Markdown under ``evidence/`` is the evidence: sealed, and re-derived by
``evidence verify --recompute``. A PDF is a rendering of it for people who read
on paper or attach it to a committee pack. A renderer stamps its output, so a
PDF cannot be reproduced byte for byte and is never sealed into the run.

Instead, every PDF carries what ties it to the run it came from: the run's
*seal* — the SHA-256 of ``checksums.sha256``, which fixes every file in the run
— on every page, the SHA-256 of the Markdown it renders, the timestamps of the
model calls, the scoring and the export, and an integrity section that says how
to check all of it. The auditor's PDF lists the checksum of every file.

PDFs are printed by a local Chrome or Chromium (``EVIDENCE_CHROME`` names one
explicitly). Without one, the HTML is written and can be printed from a browser.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence.evidence.readers import READERS

# Every document an export can produce: the six readers and the full report.
DOCUMENTS: dict[str, dict[str, str]] = {
    "business": {"title": "Business summary", "source": "evidence/readers/business.md"},
    "credit-risk": {"title": "Model risk report", "source": "evidence/readers/credit-risk.md"},
    "compliance": {"title": "Compliance report", "source": "evidence/readers/compliance.md"},
    "operations": {"title": "Underwriting operations briefing",
                   "source": "evidence/readers/operations.md"},
    "vendor": {"title": "Vendor report", "source": "evidence/readers/vendor.md"},
    "auditor": {"title": "Audit and integrity report", "source": "evidence/readers/auditor.md"},
    "full": {"title": "Full evidence report", "source": "evidence/report.md"},
}
for _name, _meta in DOCUMENTS.items():
    _r = READERS.get(_name, {"for": "Every reader", "question": "Everything, by obligation."})
    _meta |= {"for": _r["for"], "question": _r["question"]}

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge",
]

STATUS = {"GO": "go", "GO WITH CONDITIONS": "cond", "CONDITIONAL": "cond", "NO-GO": "nogo",
          "INCONCLUSIVE": "cond", "INSUFFICIENT": "cond", "NOT-RUN": "cond"}


# --------------------------------------------------------------------------
# Markdown -> HTML, for the subset the reports use
# --------------------------------------------------------------------------

_NUMERIC = re.compile(r"^[\d.,%/×x\s–-]+$|^\d+ of \d+$|^at most \d+%$")


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(^|[^*])\*([^*\n]+)\*", r"\1<em>\2</em>", s)
    return s


def _cell(text: str, header: bool, numeric: bool) -> str:
    tag = "th" if header else "td"
    raw = text.strip()
    if not header and raw.upper() in STATUS:
        return f'<td><span class="chip {STATUS[raw.upper()]}">{html.escape(raw)}</span></td>'
    cls = ' class="num"' if numeric else ""
    return f"<{tag}{cls}>{_inline(raw)}</{tag}>"


def _table(block: list[str]) -> str:
    head, *rows = [r.split("\x00") for r in block]
    # a column is numeric when every body cell in it is: header and cells align right
    numeric = [bool(rows) and all(i < len(r) and _NUMERIC.match(r[i].strip()) for r in rows)
               for i in range(len(head))]
    return ("<table><thead><tr>"
            + "".join(_cell(c, True, numeric[i]) for i, c in enumerate(head))
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(_cell(c, False, i < len(numeric) and numeric[i])
                                       for i, c in enumerate(r)) + "</tr>" for r in rows)
            + "</tbody></table>")


def md_to_html(src: str) -> str:
    """Headings, tables, lists, block quotes, code blocks, bold, italic and code."""
    out: list[str] = []
    block: list[str] = []
    kind = ""

    def flush() -> None:
        nonlocal block, kind
        if not block:
            return
        if kind == "table":
            out.append(_table(block))
        elif kind in ("ul", "ol"):
            out.append(f"<{kind}>" + "".join(f"<li>{_inline(x)}</li>" for x in block)
                       + f"</{kind}>")
        elif kind == "quote":
            out.append(f"<blockquote>{_inline(' '.join(block))}</blockquote>")
        elif kind == "code":
            out.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
        block, kind = [], ""

    code = False
    for raw in src.split("\n"):
        line = raw.rstrip()
        if line.startswith("```"):
            if code:
                flush()
                code = False
            else:
                flush()
                code, kind = True, "code"
            continue
        if code:
            block.append(raw)
            continue
        if line.startswith("|"):
            if re.match(r"^\|[\s:|-]+\|?$", line):
                continue
            cells = line.strip().strip("|").split("|")
            if kind != "table":
                flush()
                kind = "table"
            block.append("\x00".join(c.strip() for c in cells))
            continue
        m = re.match(r"^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$", line)
        if m:
            want = "ol" if m.group(1) else "ul"
            if kind != want:
                flush()
                kind = want
            block.append(m.group(2))
            continue
        if line.startswith(">"):
            if kind != "quote":
                flush()
                kind = "quote"
            block.append(line.lstrip("> ").strip())
            continue
        flush()
        if line.startswith("### "):
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif re.match(r"^-{3,}$", line):
            out.append("<hr>")
        elif line:
            out.append(f"<p>{_inline(line)}</p>")
    flush()
    return "\n".join(out)


# --------------------------------------------------------------------------
# the document
# --------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal_digest(run: Path) -> str:
    """The run's seal: SHA-256 of checksums.sha256, which fixes every file in the run."""
    return _sha256(run / "checksums.sha256")


def _checksums(run: Path) -> list[tuple[str, str]]:
    rows = []
    for line in (run / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            rows.append((name, digest))
    return rows


def _duration(a: str | None, b: str | None) -> str:
    try:
        secs = (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(int(secs), 3600)
    return f" ({h} h {rem // 60} min)" if h else f" ({rem // 60} min {rem % 60} s)"


def _ts(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).astimezone(UTC).strftime("%d %b %Y, %H:%M:%S UTC")
    except ValueError:
        return value


def _strip_lead(md: str, name: str) -> str:
    """The cover carries the title and the run line; drop them from the body."""
    lines = md.split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    if name != "full" and lines and lines[0].startswith("Assistant `"):
        lines = lines[1:]
    # the verdict is on the cover
    lines = [x for x in lines if not x.startswith("## Verdict:")]
    return "\n".join(lines)


def render_html(run: Path, name: str, exported_at: datetime | None = None) -> str:
    """One document of a run as a self-contained, print-ready HTML page."""
    if name not in DOCUMENTS:
        raise KeyError(f"no document {name!r}; documents: {', '.join(DOCUMENTS)}")
    doc = DOCUMENTS[name]
    src = run / doc["source"]
    if not src.is_file():
        raise FileNotFoundError(f"{src} not found — write the run's evidence first "
                                "(evidence report <run> --rewrite)")
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    decision_path = run / "evidence" / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8")) if decision_path.is_file() \
        else None
    exported = (exported_at or datetime.now(UTC)).astimezone(UTC)
    seal = seal_digest(run)
    sums = dict(_checksums(run))
    source_sha = sums.get(doc["source"]) or _sha256(src)
    sut, pack = manifest["sut"], manifest["pack"]
    judge = manifest.get("judge") or {}
    models = manifest.get("models") or {}
    e = html.escape

    meta = [
        ("Run", f"<code>{e(manifest['run_id'])}</code>"),
        ("Pack", f"<code>{e(pack['pack_id'])}</code> v{e(str(pack['version']))} · "
                 f"{pack['items']} cases × {manifest['repeats']} = {manifest['transcripts']} "
                 "briefings"),
        ("Assistant under test", f"<code>{e(sut['model_id'])}</code> · "
                                 f"{'on-prem' if sut.get('on_prem') else 'cloud'}"),
        ("Judge", f"<code>{e(judge.get('model_id', '—'))}</code> · reported, not gated"
         if judge else "none"),
        ("Model calls", f"{_ts(manifest.get('started_at'))} → {_ts(manifest.get('finished_at'))}"
                        f"{_duration(manifest.get('started_at'), manifest.get('finished_at'))}"),
        ("Checks scored", _ts(manifest.get("scored_at")) if manifest.get("scored_at")
         else _ts(manifest.get("finished_at"))),
        ("Exported", exported.strftime("%d %b %Y, %H:%M:%S UTC")),
        ("Model fingerprints", "<br>".join(
            f"{role} <code>{e(str((models.get(role) or {}).get('fingerprint') or 'not recorded'))}"
            f"</code>" + (" <b class='chip nogo'>changed during run</b>"
                          if (models.get(role) or {}).get("changed_during_run") else "")
            for role in ("assistant", "judge", "embed")
            if role in models or role == "assistant" or (role == "judge" and judge))),
        ("Engine", f"{e(manifest['engine']['package'])} {e(manifest['engine']['version'])} · "
                   f"commit <code>{e(manifest['engine'].get('git_commit') or '—')}</code>"),
    ]
    meta_html = "".join(f"<div class='k'>{k}</div><div class='v'>{v}</div>" for k, v in meta)
    verdict = decision["verdict"] if decision else None
    chip = (f"<div class='verdict'><span>Verdict against the bank's thresholds</span>"
            f"<b class='chip big {STATUS.get(verdict, 'cond')}'>{e(verdict)}</b></div>"
            if verdict else "")

    key_files = [f for f in ("manifest.json", "results.jsonl", "evidence/decision.json",
                             doc["source"]) if f in sums]
    integrity = [
        "<section class='integrity'><h2>Integrity</h2>",
        f"<p>This PDF renders <code>{e(doc['source'])}</code> from run "
        f"<code>{e(manifest['run_id'])}</code>. The Markdown is sealed into the run and can be "
        "re-derived from its results; the PDF is a rendering and is not sealed. To check this "
        "document against the run:</p><ol>",
        f"<li>The SHA-256 of the run's <code>checksums.sha256</code> — its <b>seal</b>, printed "
        f"on every page — is <code class='hash'>{seal}</code>.</li>",
        "<li><code>evidence verify runs/&lt;run&gt;</code> confirms every file still matches "
        "<code>checksums.sha256</code>; add <code>--recompute --pack packs/"
        f"{e(pack['pack_id'])}</code> to re-derive every result and every report.</li>",
        f"<li>The source of this document, <code>{e(doc['source'])}</code>, has SHA-256 "
        f"<code class='hash'>{source_sha}</code>, as listed in <code>checksums.sha256</code>."
        "</li></ol>",
        "<table class='sums'><thead><tr><th>file</th><th>SHA-256</th></tr></thead><tbody>",
        *(f"<tr><td><code>{e(f)}</code></td><td><code class='hash'>{sums[f]}</code></td></tr>"
          for f in key_files),
        "</tbody></table>",
        f"<p class='small'>Pack items SHA-256 <code class='hash'>{e(pack['items_sha256'])}</code>"
        + (f" · regulation corpus <code class='hash'>"
           f"{e((judge.get('corpus') or {}).get('corpus_sha256', ''))}</code>"
           if (judge.get("corpus") or {}).get("corpus_sha256") else "")
        + "</p></section>",
    ]
    appendix = ""
    if name == "auditor":
        rows = "".join(f"<tr><td><code>{e(f)}</code></td><td><code class='hash'>{d}</code></td>"
                       "</tr>" for f, d in _checksums(run))
        appendix = (f"<section class='appendix'><h2>Appendix — every file in the run "
                    f"({len(sums)})</h2><p class='small'>The contents of <code>checksums.sha256"
                    "</code>, in order.</p><table class='sums all'><thead><tr><th>file</th>"
                    f"<th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table></section>")

    body = md_to_html(_strip_lead(src.read_text(encoding="utf-8"), name))
    footer_left = f"Run {manifest['run_id']} · seal {seal[:16]}…"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{e(doc['title'])} — {e(manifest['run_id'])}</title>
<style>{_CSS.replace("__PAGE_SANS__", _PAGE_SANS).replace("__PAGE_MONO__", _PAGE_MONO)
           .replace("__FOOT_LEFT__", _css_str(footer_left))
           .replace("__HEAD_LEFT__", _css_str("Credit Evidence Engine · " + doc['title']))
           .replace("__HEAD_RIGHT__", _css_str(pack['pack_id'] + " v" + str(pack['version'])))}
</style></head><body>
<header class="cover">
  <div class="brand">Credit Evidence Engine <span>·</span> Evidence pack</div>
  <h1>{e(doc['title'])}</h1>
  <p class="for"><b>For</b> {e(doc['for'])} — {e(doc['question'])}</p>
  {chip}
  <div class="meta">{meta_html}</div>
  <div class="seal"><span>Run seal · SHA-256 of checksums.sha256</span><code>{seal}</code></div>
</header>
<main>{body}</main>
{''.join(integrity)}
{appendix}
</body></html>
"""


def _css_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# Page margin boxes do not see custom properties, so their fonts are spelled out.
_PAGE_SANS = '-apple-system, "Helvetica Neue", Arial, sans-serif'
_PAGE_MONO = "Menlo, Consolas, monospace"

_CSS = """
@page { size: A4; margin: 20mm 17mm 18mm;
  @top-left { content: __HEAD_LEFT__; font: 7.5pt __PAGE_SANS__; color: #6b7280; }
  @top-right { content: __HEAD_RIGHT__; font: 7.5pt __PAGE_SANS__; color: #6b7280; }
  @bottom-left { content: __FOOT_LEFT__; font: 7pt __PAGE_MONO__; color: #6b7280; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages);
                  font: 7.5pt __PAGE_SANS__; color: #6b7280; } }
@page :first { @top-left { content: none; } @top-right { content: none; } }
:root { --sans: "Inter", -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  --mono: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  --ink: #14171f; --ink2: #4b5563; --ink3: #6b7280; --line: #e3e6eb; --tint: #f4f6f8;
  --accent: #1f5f4a; --go: #1e7b3c; --go-bg: #e7f4ea; --cond: #9a6400; --cond-bg: #fdf3dc;
  --nogo: #b42318; --nogo-bg: #fdecea; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font: 9.6pt/1.5 var(--sans); color: var(--ink); margin: 0; }
code { font: 8.2pt var(--mono); background: var(--tint); padding: 0 3px; border-radius: 3px; }
code.hash { font-size: 7.4pt; word-break: break-all; background: none; padding: 0; }
.cover { border-bottom: 2px solid var(--accent); padding-bottom: 10pt; margin-bottom: 14pt; }
.brand { font-size: 7.5pt; letter-spacing: .14em; text-transform: uppercase; color: var(--accent);
  font-weight: 650; }
.brand span { color: var(--ink3); }
.cover h1 { font-size: 20pt; letter-spacing: -.01em; margin: 6pt 0 2pt; font-weight: 700; }
.cover .for { margin: 0 0 10pt; color: var(--ink2); }
.verdict { display: flex; align-items: center; gap: 10pt; margin: 4pt 0 10pt;
  padding: 8pt 10pt; background: var(--tint); border-radius: 6pt; }
.verdict span { color: var(--ink2); font-size: 8.5pt; }
.meta { display: grid; grid-template-columns: 38mm 1fr; gap: 3pt 10pt; font-size: 8.4pt; }
.meta .k { color: var(--ink3); text-transform: uppercase; letter-spacing: .05em; font-size: 7pt;
  padding-top: 1.5pt; }
.seal { margin-top: 8pt; padding: 6pt 9pt; border: 1px solid var(--line); border-radius: 5pt; }
.seal span { display: block; font-size: 7pt; text-transform: uppercase; letter-spacing: .06em;
  color: var(--ink3); margin-bottom: 1pt; }
.seal code { background: none; padding: 0; font-size: 7.8pt; word-break: break-all; }
.chip { display: inline-block; font: 700 7.4pt var(--sans); letter-spacing: .04em;
  padding: 1.5pt 6pt; border-radius: 99px; }
.chip.big { font-size: 10pt; padding: 3pt 11pt; }
.chip.go { color: var(--go); background: var(--go-bg); }
.chip.cond { color: var(--cond); background: var(--cond-bg); }
.chip.nogo { color: var(--nogo); background: var(--nogo-bg); }
h1 { font-size: 14pt; } h2 { font-size: 11.5pt; margin: 16pt 0 5pt; padding-top: 7pt;
  border-top: 1px solid var(--line); color: var(--ink); break-after: avoid; }
h3 { font-size: 10pt; margin: 10pt 0 3pt; break-after: avoid; }
main > h2:first-child { border-top: 0; padding-top: 0; margin-top: 0; }
p { margin: 3.5pt 0; } ul, ol { margin: 3pt 0 5pt; padding-left: 15pt; } li { margin: 1.5pt 0; }
strong { font-weight: 650; }
table { width: 100%; border-collapse: collapse; margin: 5pt 0 9pt; font-size: 8.2pt; }
thead { display: table-header-group; }
th { text-align: left; font-size: 6.9pt; text-transform: uppercase; letter-spacing: .05em;
  color: var(--ink2); background: var(--tint); padding: 4pt 5pt; border-bottom: 1px solid #cfd4db; }
td { padding: 3.5pt 5pt; border-bottom: 1px solid var(--line); vertical-align: top; }
tbody tr:nth-child(even) td { background: #fafbfc; }
th.num { text-align: right; }
td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tr, blockquote, pre, .seal, .verdict { break-inside: avoid; }
blockquote { margin: 6pt 0; padding: 6pt 10pt; border-left: 3px solid var(--accent);
  background: #f3f7f5; font-style: italic; color: #1f2937; }
pre { font: 7.8pt/1.45 var(--mono); background: var(--tint); padding: 7pt 9pt; border-radius: 5pt;
  white-space: pre-wrap; }
.integrity { margin-top: 16pt; padding: 10pt 12pt; border: 1px solid var(--line);
  border-radius: 6pt; background: #fcfcfd; break-inside: avoid; }
.integrity h2 { border: 0; padding: 0; margin: 0 0 4pt; }
.sums td:first-child { width: 42%; } .sums code { background: none; padding: 0; }
@page wide { size: A4 landscape; }
.appendix { page: wide; break-before: page; }
.sums.all { font-size: 6.8pt; table-layout: fixed; }
.sums.all td { padding: 1.4pt 5pt; white-space: nowrap; overflow: hidden; }
.sums.all td:first-child { width: 57%; }
.sums.all code.hash { word-break: normal; font-size: 6.8pt; }
.small { font-size: 7.6pt; color: var(--ink3); }
"""


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

def find_chrome() -> str | None:
    """A Chrome, Chromium or Edge to print with: EVIDENCE_CHROME, then the usual places."""
    explicit = os.environ.get("EVIDENCE_CHROME")
    if explicit:
        return explicit if Path(explicit).exists() or shutil.which(explicit) else None
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def html_to_pdf(html_path: Path, pdf_path: Path, chrome: str) -> None:
    args = [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw", f"--print-to-pdf={pdf_path}"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")  # a container running as root
    subprocess.run([*args, html_path.resolve().as_uri()], check=True, timeout=180,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"{chrome} did not write {pdf_path}")


def export_run(run: Path, out: Path, names: list[str] | None = None, *, pdf: bool = True,
               exported_at: datetime | None = None) -> dict[str, Any]:
    """Write each document as HTML and, when a browser is available, PDF. Never inside the run:
    a file there would not be in checksums.sha256 and the run would fail verification."""
    run, out = run.resolve(), out.resolve()
    if out == run or run in out.parents:
        raise ValueError("export outside the run directory: files inside it break its seal")
    out.mkdir(parents=True, exist_ok=True)
    when = exported_at or datetime.now(UTC)
    chrome = find_chrome() if pdf else None
    written: list[str] = []
    for name in names or list(DOCUMENTS):
        html_path = out / f"{run.name}-{name}.html"
        html_path.write_text(render_html(run, name, when), encoding="utf-8")
        if chrome:
            pdf_path = html_path.with_suffix(".pdf")
            html_to_pdf(html_path, pdf_path, chrome)
            html_path.unlink()
            written.append(str(pdf_path))
        else:
            written.append(str(html_path))
    return {"written": written, "pdf": bool(chrome), "chrome": chrome, "seal": seal_digest(run),
            "exported_at": when.isoformat(timespec="seconds")}
