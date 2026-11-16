# Architecture & Engineering Decision Log

**Capstone Project PS-047: Supermarket POS Billing Engine**  
**Team IDT002: Aditi Anshu (1AT24CD004) & Aditi Chaudhary (1AT24CD005)**  
**Section: CSDS A | Standard Library Only (Python 3.10+) | Command-File Driven (No UI)**

---

## 1. One-Line Decision Register

| Decision ID | Date | Component | One-Line Decision Summary | Impact / Result |
| :---: | :---: | :--- | :--- | :--- |
| **DEC-001** | 2026-11-15 | Core Arithmetic | Mandate `decimal.Decimal` with `ROUND_HALF_UP` for all currency (2dp) and weights (3dp); ban `float` entirely. | Eliminates IEEE-754 rounding drift; ensures zero-loss exact-paisa accounting. |
| **DEC-002** | 2026-11-15 | Dependencies | Implement using Python 3.10+ Standard Library only with zero external pip packages. | Guarantees self-contained, air-gapped terminal execution on any host environment. |
| **DEC-003** | 2026-11-15 | User Interface | Bar all graphical or web interfaces; enforce strict batch command-file and CLI execution only. | Complies strictly with the capstone problem brief requirements for a till backend engine. |
| **DEC-004** | 2026-11-15 | Domain Modeling | Model catalog items, bills, scan events, and reports as `@dataclass` structures in `src/models.py`. | Provides clean, typed, inspectable domain entities with minimal runtime overhead. |
| **DEC-005** | 2026-11-15 | Scale Validation | Reject weighed items with net weight strictly below 0.005 kg (`BR-01`) at scan ingestion time. | Prevents illegal or inaccurate zero-load scale scans from entering the billing queue. |
| **DEC-006** | 2026-11-15 | Legal Pricing | Enforce MRP ceiling via `Product.effective_selling_price` and `effective_member_price` as `min(price, mrp)`. | Eliminates overcharging liabilities under consumer packaging laws across all price tiers. |
| **DEC-007** | 2026-11-15 | Multi-Buy Partitioning | Sort multi-buy units descending by price before grouping triples, awarding the cheapest unit in each triple free. | Maximizes customer fairness and produces deterministic promotional allocations. |
| **DEC-008** | 2026-11-15 | Multi-Buy Capping | Cap multi-buy free items at a maximum of 3 free items per bill per offer group (`BR-03`). | Prevents merchant inventory drainage on bulk promotional purchases. |
| **DEC-009** | 2026-11-15 | Category Clearance | Activate 10% FRESH discount only if scan or bill timestamp is at or after 20:00:00 (`BR-04`). | Perfectly models supermarket evening perishables clearance schedules. |
| **DEC-010** | 2026-11-15 | Offer Precedence | Enforce rigid 5-level precedence: Multi-Buy $\to$ Category $\to$ Member $\to$ Coupon $\to$ Threshold (`BR-05`). | Prevents duplicate stacking of multiple item-level promotions on the same physical unit. |
| **DEC-011** | 2026-11-15 | Coupon Validation | Restrict to max 1 coupon per bill; cap PCT coupons at Rs 200.00; reject FIXED coupons if subtotal $< 3 \times \text{value}$. | Protects store margins from abusive coupon stacking or low-subtotal redemption. |
| **DEC-012** | 2026-11-15 | Pro-Rata Apportionment | Apportion bill-level discounts pro-rata across items, allocating residual rounding paise to the largest line item. | Guarantees that the sum of line-item discounts equals the nominal bill discount to the exact paisa. |
| **DEC-013** | 2026-11-15 | GST Rate Slabs | Group items by GST slab (`0%`, `5%`, `12%`, `18%`) and round tax per slab rather than per line (`BR-09`). | Complies strictly with statutory Indian GST accounting standards. |
| **DEC-014** | 2026-11-15 | Intra-Slab Tax Allocation | Proportionally distribute rounded slab GST back to individual lines within the slab. | Enables deterministic line-level effective prices needed for partial returns. |
| **DEC-015** | 2026-11-15 | Loyalty Accrual Exclusions | Exclude `TOBACCO` and `LIQUOR` categories entirely from loyalty point earn calculations (`BR-10`). | Enforces legal compliance barring promotional rewards on regulated vices. |
| **DEC-016** | 2026-11-15 | Loyalty Point Maturation | Place earned loyalty points into a 7-day `PENDING` state until the customer return window lapses (`BR-10`). | Eliminates point gaming where customers earn points and immediately return merchandise. |
| **DEC-017** | 2026-11-15 | Loyalty Redemption Rules | Enforce 1 pt = Rs 0.25, redeemable in 100-pt multiples, capped at 20% of post-threshold subtotal before GST (`BR-11`). | Standardizes loyalty burns while preventing point redemptions from wiping out tax liabilities. |
| **DEC-018** | 2026-11-15 | Return Eligibility Window | Define the 7-day return window as inclusive up to 23:59:59 on Day +7 from the original bill date (`BR-12`). | Provides clear store closing cutoff rules for customer returns. |
| **DEC-019** | 2026-11-15 | Weighed Item Returns | Strictly bar returns on weighed bulk items (`unit == 'KG'`) (`BR-12`). | Prevents health hazards, food contamination, and perishables fraud. |
| **DEC-020** | 2026-11-15 | Multi-Buy Return Clawback | Deduct the free promotional item's value when a partial return breaks a multi-buy triple (`BR-13`). | Prevents exploitation where customers buy 3 items to get 1 free and return the 2 paid items. |
| **DEC-021** | 2026-11-15 | Free Item Return Refund | Refund strictly Rs 0.00 when a customer returns the free item in a multi-buy deal (EC-7). | Accurately reflects the customer's actual zero outlay on the promotional free unit. |
| **DEC-022** | 2026-11-15 | Till Z-Report Invariance | Formulate Z-report to reconcile gross sales, discounts, slab taxes, refunds, and net cash drawer revenue. | Provides store managers with mathematically provable till balancing and audit verification. |

---

## 2. Technical Rationale & Deep Dive

### 2.1 The Float-Free Financial Guarantee
Binary floating-point arithmetic (IEEE-754) is non-deterministic across hardware platforms and represents decimal fractions as recurring binary expansions. In retail transactions, rounding `0.1 + 0.2` produces `0.30000000000000004`, leading to fractional cent imbalances that violate fiscal statutes. By adopting Python's `decimal.Decimal` with explicit quantization (`Decimal('0.01')` for currency and `Decimal('0.001')` for weight) and `ROUND_HALF_UP`, our engine guarantees that every transaction is audit-proof and repeatable to the exact paisa.

### 2.2 Pro-Rata Apportionment Algorithm
When a coupon discount (e.g., Rs 50.00) or bill threshold (e.g., Rs 100.00) is distributed across multiple line items, naive integer division or per-line rounding inevitably produces rounding residuals ($\pm 1$ or $2$ paise). Rather than dropping the residual or forcing unbalanced line values, our engine uses a two-pass algorithm:
1. Pass 1 calculates the baseline proportional share for each line:
   $$S_i = \text{quantize\_currency}\left( \frac{V_i}{V_{\text{total}}} \times D_{\text{total}} \right)$$
2. Pass 2 computes the residual drift $\Delta = D_{\text{total}} - \sum S_i$ and assigns it to the line with the maximum taxable base value.
This ensures strict adherence to the invariant $\sum S_i \equiv D_{\text{total}}$.

### 2.3 Statutory GST Rate-Slab Rounding
Indian GST regulations mandate that GST must not be rounded at the individual SKU line level; rather, lines sharing the same statutory tax rate (`0%`, `5%`, `12%`, `18%`) must be aggregated into a slab taxable total, upon which the percentage is applied and rounded to two decimal places. However, to support partial item returns, the engine also computes an exact line-level GST allocation so that returning one line refunds the exact post-tax amount paid by the customer.

---

## 3. Explicit Edge-Case Resolution Log

### Edge Case 1: Net Weight Minimum Threshold Boundary (0.005 kg vs 0.004 kg)
- **Problem Statement:** Verify that weighed items respect the tare deduction and reject transactions below the minimum legal scale sensitivity of 5 grams.
- **Resolution:**
  - Net weight is computed as `gross_weight - tare_weight`.
  - If `net_weight == Decimal('0.005')`, the scan is accepted.
  - If `net_weight == Decimal('0.004')`, the scan is rejected with a `ValueError`.
- **Test Reference:** `TestPOSBillingEngine.test_edge_case_1_net_weight_boundary`.

### Edge Case 2: Member Price Configured Above MRP
- **Problem Statement:** A data entry error in the product master or a regional price surcharge may cause `member_price > mrp` or `selling_price > mrp`.
- **Resolution:**
  - BR-02 strictly caps both `effective_selling_price` and `effective_member_price` at `mrp`.
  - If MRP is Rs 100.00 and member price is Rs 120.00, the effective unit price charged is capped at Rs 100.00.
- **Test Reference:** `TestPOSBillingEngine.test_edge_case_2_member_price_above_mrp`.

### Edge Case 3: Four Items of Different Prices in One Multi-Buy Group
- **Problem Statement:** How should multi-buy behave when 4 items (e.g., Rs 100, Rs 80, Rs 60, Rs 40) belong to the same offer group?
- **Resolution:**
  - Units are sorted descending: `[100, 80, 60, 40]`.
  - The first triple `(100, 80, 60)` is formed. The cheapest unit in the triple (Rs 60.00) is awarded 100% free.
  - The 4th item (Rs 40.00) cannot form a complete group of 3. It remains outside the group, is paid at full price, and remains eligible for subsequent offers.
- **Test Reference:** `TestPOSBillingEngine.test_edge_case_3_four_items_different_prices_multibuy`.

### Edge Case 4: Evening Clearance Scan at Exactly 20:00:00
- **Problem Statement:** Verify whether a `FRESH` item scanned at exactly `20:00:00` qualifies for the 10% clearance discount.
- **Resolution:**
  - BR-04 specifies `time >= 20:00:00`.
  - A scan at `20:00:00` satisfies the condition and receives the 10% discount.
  - A scan at `19:59:59` fails the condition and receives 0% clearance discount.
- **Test Reference:** `TestPOSBillingEngine.test_edge_case_4_evening_clearance_exactly_20_00`.

### Edge Case 5: Bill Subtotal of Exactly Rs 2,000.00 After Coupon
- **Problem Statement:** Verify threshold boundary condition where post-coupon subtotal equals exactly Rs 2,000.00.
- **Resolution:**
  - BR-08 specifies subtotal `>= Rs 2,000.00` receives Rs 100.00 discount.
  - Exactly Rs 2,000.00 triggers the Rs 100.00 threshold discount.
- **Test Reference:** `TestPOSBillingEngine.test_edge_case_5_subtotal_exactly_2000_threshold`.

### Edge Case 6: Loyalty Burn 20% Cap Blocked on Rs 100 Bill
- **Problem Statement:** A member requests redemption of 100 points (Rs 25.00) on a bill with a post-threshold subtotal of Rs 100.00.
- **Resolution:**
  - 20% cap on Rs 100.00 is Rs 20.00.
  - 100 points is worth Rs 25.00, which exceeds the Rs 20.00 cap.
  - Since points must be redeemed in multiples of 100 and even 100 points exceeds the cap, 0 points are redeemed (blocked).
- **Test Reference:** `TestPOSBillingEngine.test_edge_case_6_loyalty_burn_20_percent_cap_blocked`.

### Edge Case 7: Return of the Free Item in a Multi-Buy Group
- **Problem Statement:** A customer attempts to return the free promotional item in a Buy 2 Get 1 Free deal.
- **Resolution:**
  - The free item's net paid price was Rs 0.00.
  - Its refund value is strictly Rs 0.00, and no clawback is deducted from the customer.
- **Test Reference:** `TestPOSBillingEngine.test_edge_case_7_return_free_item_multibuy`.

### Edge Case 8: Return on Day 7 at Store Closing vs Day 8
- **Problem Statement:** Return window definition: `return_timestamp <= bill_timestamp + 7 days`.
- **Resolution:**
  - The 7-day window is inclusive of Day +7 up to store closing at `23:59:59`.
  - Return on Day +7 at `23:59:59` is ACCEPTED.
  - Return on Day +8 at `00:00:00` is REJECTED with a `ValueError`.
- **Test Reference:** `TestPOSBillingEngine.test_edge_case_8_return_day_7_closing_vs_day_8`.
