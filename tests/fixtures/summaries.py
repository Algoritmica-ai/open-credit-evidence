"""Pre-generated summaries for testing omission detection.

Contains both good summaries (complete) and bad summaries (missing critical facts).
"""

CASE_001_GOOD_SUMMARY = """
LOAN APPLICATION SUMMARY - LOAN-2026-09-001

APPLICANT PROFILE:
Rajesh Kumar Sharma, 41 years old, Senior Software Engineer at TechSoft Solutions.
Employment tenure: 4 years 2 months (stable).
Monthly net salary: ₹98,500.

LOAN REQUEST:
Personal loan of ₹5,00,000 for 36 months for home renovation.

CREDIT ASSESSMENT:
The applicant's CIBIL score is 682, which is at the minimum acceptable threshold of 680.
This boundary score warrants careful review.

NEGATIVE INDICATORS:
1. Credit Score at Boundary: The score of 682 is just 2 points above our minimum
   threshold, indicating elevated risk.

2. Recent Delinquency: A 30-day late payment was recorded on the SBI credit card
   in June 2026. While the account is now current, this recent delinquency is
   a concern.

3. Credit Shopping Pattern: A loan enquiry from Kotak Mahindra Bank was made just
   7 days prior to this application. This recent enquiry suggests the applicant
   may have been declined elsewhere or is actively shopping for credit.

4. High Debt-to-Income: Existing monthly obligations total ₹37,200 against net
   income of ₹98,500, resulting in a debt-to-income ratio of 38%. Adding the
   proposed loan EMI would push this higher.

RECOMMENDATION:
This case was correctly referred for manual review. The combination of:
- Boundary credit score (682)
- Recent 30-day delinquency
- Credit shopping behavior
- High existing DTI

...suggests elevated risk. Consider requiring additional documentation or
offering reduced loan amount.
"""

CASE_001_BAD_SUMMARY_OMITS_DELINQUENCY = """
LOAN APPLICATION SUMMARY - LOAN-2026-09-001

APPLICANT PROFILE:
Rajesh Kumar Sharma, 41 years old, Senior Software Engineer at TechSoft Solutions.
Employment tenure: 4 years 2 months (stable).
Monthly net salary: ₹98,500.

LOAN REQUEST:
Personal loan of ₹5,00,000 for 36 months for home renovation.

CREDIT ASSESSMENT:
The applicant's CIBIL score is 682. The applicant has a good credit history
with no significant issues. Payment history shows consistent on-time payments
across all accounts.

DEBT ANALYSIS:
Existing monthly obligations total ₹37,200. The applicant has manageable
debt levels with regular income to support additional borrowing.

POSITIVE FACTORS:
- Stable employment of 4+ years
- Regular salary credits
- Previously closed personal loan with normal closure
- Good credit card payment track record

RECOMMENDATION:
The applicant appears to be a reasonable credit risk. The stable employment
and consistent income support the loan request. Recommend approval with
standard terms.
"""

CASE_001_BAD_SUMMARY_OMITS_ENQUIRY = """
LOAN APPLICATION SUMMARY - LOAN-2026-09-001

APPLICANT PROFILE:
Rajesh Kumar Sharma, 41 years old, Senior Software Engineer at TechSoft Solutions.
Employment tenure: 4 years 2 months (stable).
Monthly net salary: ₹98,500.

LOAN REQUEST:
Personal loan of ₹5,00,000 for 36 months for home renovation.

CREDIT ASSESSMENT:
The applicant's CIBIL score is 682, at the minimum threshold boundary.

PAYMENT HISTORY:
One 30-day late payment on SBI credit card in June 2026. Otherwise good
payment track record across accounts.

DEBT ANALYSIS:
Existing DTI of 38% which is on the higher side but manageable given income.

RECOMMENDATION:
The boundary score and recent late payment warrant caution. However, the
long employment tenure and otherwise clean history are positive factors.
Consider approval with close monitoring.
"""

CASE_002_GOOD_SUMMARY = """
LOAN APPLICATION SUMMARY - LOAN-2026-09-002

APPLICANT PROFILE:
Priya Venkatesh, 36 years old, Data Science Manager at Global Analytics Corp.
Employment tenure: 2 years 8 months.
Monthly net salary: ₹1,65,000.

LOAN REQUEST:
Personal loan of ₹12,00,000 for 48 months for debt consolidation.

CREDIT ASSESSMENT:
CIBIL score of 738 is in the "Good" band, well above minimum thresholds.

CRITICAL CONCERNS:

1. Very High Credit Card Utilization: Combined credit card utilization is
   critically high at over 60% (₹5.12 lakh outstanding against ₹8.5 lakh
   total limit). The Axis Bank card alone shows 81% utilization. This is
   a strong indicator of debt stress despite the good credit score.

2. Aggressive Credit Seeking: Three personal loan enquiries within 45 days
   from different lenders (current application, HDFC Bank, and Tata Capital).
   This pattern indicates the applicant is actively seeking credit from
   multiple sources, possibly being declined.

3. Debt Consolidation Risk: The loan purpose is explicitly debt consolidation,
   which combined with the high revolving debt suggests underlying cash flow
   problems. Such loans often provide temporary relief before debt
   re-accumulation.

4. Minimum Payment Pattern: The applicant appears to be making only minimum
   payments on credit cards despite having high income, indicating possible
   cash flow management issues.

RISK ASSESSMENT:
Despite the healthy credit score of 738, the underlying debt pattern is
concerning. High utilization, multiple recent enquiries, and debt
consolidation purpose together suggest financial stress.

RECOMMENDATION:
If approved, strongly recommend:
1. Credit card closure or limit reduction as condition
2. Lower sanctioned amount than requested
3. Closer monitoring of repayment behavior
"""

CASE_002_BAD_SUMMARY_OMITS_UTILIZATION = """
LOAN APPLICATION SUMMARY - LOAN-2026-09-002

APPLICANT PROFILE:
Priya Venkatesh, 36 years old, Data Science Manager at Global Analytics Corp.
Employment tenure: 2 years 8 months.
Monthly net salary: ₹1,65,000.

LOAN REQUEST:
Personal loan of ₹12,00,000 for 48 months for debt consolidation.

CREDIT ASSESSMENT:
The applicant has a CIBIL score of 738 which is in the "Good" band.
The score reflects positive credit behavior and responsible use of credit.

CREDIT HISTORY:
- Car loan with ICICI Bank, current and well-maintained
- Education loan previously closed with normal closure
- Multiple credit cards with good standing
- Previous personal loan closed normally

POSITIVE FACTORS:
- High income supporting loan serviceability
- Good credit score
- No delinquencies in payment history
- Stable employment at reputed company

RECOMMENDATION:
Strong applicant profile with good income and credit score. The debt
consolidation purpose will help the applicant better manage finances.
Recommend approval.
"""

CASE_002_BAD_SUMMARY_OMITS_ENQUIRIES = """
LOAN APPLICATION SUMMARY - LOAN-2026-09-002

APPLICANT PROFILE:
Priya Venkatesh, 36 years old, Data Science Manager at Global Analytics Corp.
Monthly net salary: ₹1,65,000.

LOAN REQUEST:
Personal loan of ₹12,00,000 for debt consolidation.

CREDIT ASSESSMENT:
CIBIL score of 738 is good. However, credit card utilization is high at
over 60% which needs attention. The Axis Bank card shows 81% utilization.

DEBT PATTERN:
The applicant is seeking debt consolidation to manage existing credit card
balances. High utilization indicates some level of debt stress despite
good income.

RECOMMENDATION:
The high utilization is a concern. If approved, consider requiring
credit card limit reduction. The debt consolidation may help if managed
properly.
"""
