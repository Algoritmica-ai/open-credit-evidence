# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""PDF export: each page carries the run's seal; each document its timestamps and checksums."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evidence.evidence.export import (
    DOCUMENTS,
    export_run,
    find_chrome,
    md_to_html,
    render_html,
    seal_digest,
)

RUN = Path(__file__).resolve().parents[1] / "runs" / "2026-09-24-onprem-nano"
committed = pytest.mark.skipif(not RUN.is_dir(), reason="no committed run")
WHEN = datetime(2026, 9, 30, 9, 0, 0, tzinfo=UTC)


def test_markdown_subset():
    h = md_to_html("## Results\n\n| check | pass | status |\n|---|---|---|\n"
                   "| `a` | 55/60 | NO-GO |\n\n> a quoted sentence\n\n1. one\n2. two\n\n"
                   "```\nevidence verify\n```")
    assert '<th class="num">pass</th>' in h and '<td class="num">55/60</td>' in h
    assert '<span class="chip nogo">NO-GO</span>' in h
    assert "<blockquote>a quoted sentence</blockquote>" in h
    assert "<ol><li>one</li><li>two</li></ol>" in h and "<pre>evidence verify</pre>" in h


@committed
def test_every_document_carries_the_seal_the_source_digest_and_the_times():
    seal = seal_digest(RUN)
    assert seal == hashlib.sha256((RUN / "checksums.sha256").read_bytes()).hexdigest()
    sums = dict(reversed(line.split("  ", 1))
                for line in (RUN / "checksums.sha256").read_text().splitlines())
    for name, doc in DOCUMENTS.items():
        page = render_html(RUN, name, WHEN)
        assert seal in page and f"seal {seal[:16]}" in page  # cover and every page's footer
        assert sums[doc["source"]] in page
        assert "24 Sep 2026, 01:16:16 UTC → 24 Sep 2026, 01:25:08 UTC" in page
        assert "30 Sep 2026, 09:00:00 UTC" in page  # exported


@committed
def test_the_auditor_lists_every_file_and_the_verdict_is_on_the_cover():
    auditor = render_html(RUN, "auditor", WHEN)
    for line in (RUN / "checksums.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert digest in auditor and name in auditor
    business = render_html(RUN, "business", WHEN)
    assert "chip big nogo" in business and "<h2>Verdict:" not in business


@committed
def test_export_never_writes_inside_the_run(tmp_path):
    with pytest.raises(ValueError):
        export_run(RUN, RUN / "exports", ["business"], pdf=False)
    res = export_run(RUN, tmp_path, pdf=False, exported_at=WHEN)
    assert len(res["written"]) == len(DOCUMENTS)
    assert all(Path(p).suffix == ".html" for p in res["written"])


@committed
@pytest.mark.skipif(find_chrome() is None, reason="no Chrome or Chromium to print with")
def test_pdf_is_printed(tmp_path):
    res = export_run(RUN, tmp_path, ["business"], exported_at=WHEN)
    pdf = Path(res["written"][0])
    assert pdf.suffix == ".pdf" and pdf.read_bytes()[:5] == b"%PDF-"
