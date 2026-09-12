"""Omission checking for decision-critical facts.

Verifies that AI-generated summaries contain all critical facts
from source documents.
"""

import re
from datetime import UTC, datetime

import structlog

from open_credit_evidence.loader import compute_fingerprint
from open_credit_evidence.schemas import (
    Case,
    CriticalFact,
    MarkingResult,
    OmissionResult,
    Severity,
    Summary,
)

logger = structlog.get_logger()


class OmissionChecker:
    """Checks summaries for omitted critical facts.

    This is a keyword/pattern-based implementation for Week 1.
    Future versions may use embedding similarity or LLM-based verification.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        require_all_critical: bool = True,
    ):
        """Initialize omission checker.

        Args:
            confidence_threshold: Minimum confidence to consider a fact present.
            require_all_critical: If True, fail if any CRITICAL severity fact is omitted.
        """
        self.confidence_threshold = confidence_threshold
        self.require_all_critical = require_all_critical

    def _extract_keywords(self, fact: CriticalFact) -> list[str]:
        """Extract searchable keywords from a critical fact.

        Args:
            fact: The critical fact

        Returns:
            List of keywords to search for
        """
        keywords = []

        text = fact.fact.lower()

        number_patterns = [
            r"\b\d{3}\b",
            r"₹[\d,]+",
            r"\d+%",
            r"\d+\s*days?",
            r"\d+\s*months?",
        ]
        for pattern in number_patterns:
            matches = re.findall(pattern, text)
            keywords.extend(matches)

        category_keywords = {
            "credit_score": ["score", "cibil", "credit score"],
            "delinquency": ["late", "delinquent", "dpd", "overdue", "past due", "delinquency"],
            "enquiry_pattern": ["enquir", "inquiry", "credit seek", "shopping"],
            "debt_to_income": ["dti", "debt-to-income", "debt to income", "existing emi", "obligation"],
            "credit_utilization": ["utilization", "utilisation", "outstanding", "limit"],
            "debt_pattern": ["consolidation", "revolving", "debt stress"],
            "payment_behavior": ["minimum payment", "payment behavior"],
        }

        cat_key = fact.category.value if hasattr(fact.category, "value") else str(fact.category)
        if cat_key in category_keywords:
            keywords.extend(category_keywords[cat_key])

        if "kotak" in text:
            keywords.extend(["kotak", "recent enquiry", "prior decline"])
        if "sbi" in text:
            keywords.extend(["sbi"])
        if "hdfc" in text:
            keywords.extend(["hdfc"])
        if "30-day" in text or "30 day" in text:
            keywords.extend(["30-day", "30 day"])
        if "june" in text:
            keywords.extend(["june"])

        keywords = [k for k in keywords if k]
        return list(set(keywords))

    def _check_fact_presence(
        self,
        fact: CriticalFact,
        summary_text: str,
    ) -> OmissionResult:
        """Check if a single fact is present in the summary.

        Args:
            fact: The critical fact to check
            summary_text: The summary text to search

        Returns:
            OmissionResult indicating presence/absence
        """
        summary_lower = summary_text.lower()
        keywords = self._extract_keywords(fact)

        if not keywords:
            return OmissionResult(
                fact_id=fact.id,
                fact=fact,
                is_present=False,
                confidence=0.0,
                matched_text=None,
                reason="No keywords extracted from fact",
            )

        matched_keywords = []
        matched_texts = []

        for keyword in keywords:
            if keyword.lower() in summary_lower:
                matched_keywords.append(keyword)
                idx = summary_lower.find(keyword.lower())
                start = max(0, idx - 30)
                end = min(len(summary_text), idx + len(keyword) + 30)
                matched_texts.append(summary_text[start:end])

        if not matched_keywords:
            confidence = 0.0
            is_present = False
            reason = f"None of the keywords found: {keywords[:5]}"
            matched_text = None
        else:
            confidence = len(matched_keywords) / len(keywords)
            is_present = confidence >= self.confidence_threshold
            reason = f"Found {len(matched_keywords)}/{len(keywords)} keywords"
            matched_text = " ... ".join(matched_texts[:3])

        return OmissionResult(
            fact_id=fact.id,
            fact=fact,
            is_present=is_present,
            confidence=confidence,
            matched_text=matched_text,
            reason=reason,
        )

    def check_summary(
        self,
        case: Case,
        summary: Summary,
    ) -> MarkingResult:
        """Check a summary for omitted critical facts.

        Args:
            case: The source case with critical facts
            summary: The summary to check

        Returns:
            MarkingResult with omission analysis
        """
        logger.info(
            "checking_omissions",
            case_id=case.metadata.case_id,
            num_facts=len(case.metadata.critical_facts),
        )

        results = []
        facts_present = 0
        facts_omitted = 0
        critical_omitted = False

        for fact in case.metadata.critical_facts:
            result = self._check_fact_presence(fact, summary.text)
            results.append(result)

            if result.is_present:
                facts_present += 1
                logger.debug(
                    "fact_present",
                    fact_id=fact.id,
                    confidence=result.confidence,
                )
            else:
                facts_omitted += 1
                logger.warning(
                    "fact_omitted",
                    fact_id=fact.id,
                    category=fact.category,
                    severity=fact.severity,
                    fact=fact.fact[:100],
                )

                if fact.severity == Severity.CRITICAL:
                    critical_omitted = True

        total_facts = len(case.metadata.critical_facts)
        omission_rate = facts_omitted / total_facts if total_facts > 0 else 0.0

        if self.require_all_critical and critical_omitted:
            passed = False
        else:
            passed = omission_rate == 0.0

        summary_fingerprint = compute_fingerprint(summary.text)

        marking_result = MarkingResult(
            case_id=case.metadata.case_id,
            summary_fingerprint=summary_fingerprint,
            total_facts=total_facts,
            facts_present=facts_present,
            facts_omitted=facts_omitted,
            omission_rate=omission_rate,
            passed=passed,
            results=results,
            checked_at=datetime.now(UTC),
        )

        logger.info(
            "omission_check_complete",
            case_id=case.metadata.case_id,
            total_facts=total_facts,
            facts_present=facts_present,
            facts_omitted=facts_omitted,
            omission_rate=f"{omission_rate:.1%}",
            passed=passed,
        )

        return marking_result


def check_omissions(
    case: Case,
    summary: Summary,
    confidence_threshold: float = 0.5,
) -> MarkingResult:
    """Convenience function to check omissions.

    Args:
        case: The source case
        summary: The summary to check
        confidence_threshold: Minimum confidence threshold

    Returns:
        MarkingResult
    """
    checker = OmissionChecker(confidence_threshold=confidence_threshold)
    return checker.check_summary(case, summary)


def summary_passes_omission_check(
    case: Case,
    summary: Summary,
) -> bool:
    """Quick check if summary passes omission verification.

    Args:
        case: The source case
        summary: The summary to check

    Returns:
        True if no critical facts are omitted
    """
    result = check_omissions(case, summary)
    return result.passed
