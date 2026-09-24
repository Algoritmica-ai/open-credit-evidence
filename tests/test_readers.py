# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""One evidence pack, a report per reader — built from the run, and each answering its question."""

from pathlib import Path

import pytest

from evidence.evidence.readers import READERS, case_interval
from evidence.evidence.writer import build_evidence

RUN = Path(__file__).resolve().parents[1] / "runs" / "2026-09-24-onprem-nano"
committed = pytest.mark.skipif(not RUN.is_dir(), reason="no committed run")


def res(item: str, passed: bool, repeat: int = 0) -> dict:
    return {"item_id": f"p:case_review:{item}:complete", "repeat": repeat,
            "check": "c", "judge": "check:c", "passed": passed}


def test_interval_is_over_cases_not_briefings():
    # two cases, three repeats each: one always passes, one never does
    r = [res("A", True, i) for i in range(3)] + [res("B", False, i) for i in range(3)]
    mean, lo, hi = case_interval(r, "c")
    assert mean == 0.5
    # n = 2 cases, not 6 briefings: the interval spans everything
    assert (lo, hi) == (0.0, 1.0)


@committed
def test_every_reader_is_built_and_sealed_with_the_run():
    files = build_evidence(RUN)
    for name in READERS:
        rel = f"evidence/readers/{name}.md"
        assert rel in files
        assert (RUN / rel).read_text(encoding="utf-8") == files[rel]


@committed
def test_business_is_one_page_and_leads_with_the_verdict():
    text = build_evidence(RUN)["evidence/readers/business.md"]
    lines = text.splitlines()
    assert lines[4].startswith("## Verdict: **NO-GO**")
    assert len([x for x in lines if x.strip()]) < 45
    assert "stated a figure that is not in, or worked out from, the case file" in text


@committed
def test_credit_risk_carries_intervals_stability_and_limitations():
    text = build_evidence(RUN)["evidence/readers/credit-risk.md"]
    for heading in ("## 2. Test design", "## 3. Results", "## 4. Stability",
                    "## 5. Root causes and remediation", "## 6. Limitations", "## 7. Reproduce"):
        assert heading in text
    assert "95% interval" in text and "–" in text


@committed
def test_operations_quotes_what_the_assistant_wrote():
    text = build_evidence(RUN)["evidence/readers/operations.md"]
    assert "> Specifically, the applicant’s total monthly debt service" in text
    assert "**What to do:**" in text and "loan purpose" in text


@committed
def test_compliance_is_the_obligation_sections():
    text = build_evidence(RUN)["evidence/readers/compliance.md"]
    assert "## Human oversight (eu-ai-act:14) — EVIDENCES" in text
    assert "## Lender's process evidence" in text
    assert "## Decision" not in text  # that is the business and credit risk reports' job
