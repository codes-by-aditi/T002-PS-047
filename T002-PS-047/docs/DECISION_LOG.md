# POS Engine Architecture & Technical Decision Log

**Capstone Project PS-047: Supermarket POS Billing Engine**  
**Team IDT002: Aditi Anshu & Aditi Chaudhary**

---

## 1. Architectural & Engineering Decisions

### DEC-001: Strict Decimal Arithmetic (Zero-Float Guarantee)
- **Context:** Binary floating-point arithmetic introduces IEEE-754 representation artifacts (e.g., `0.1 + 0.2 = 0.30000000000000004`), which lead to fatal currency drift and audit failure in fiscal POS engines.
- **Decision:** Mandate `decimal.Decimal` with `ROUND_HALF_UP` for all currency (2 decimal places) and weights (3 decimal places). Floats are strictly barred across models, engines, and tests.
- **Consequences:** Deterministic, legally compliant calculations where `subtotal - discounts == taxable_value` and `taxable + gst == grand_total` to the exact paisa.

### DEC-002: Standard Library Only (Zero External Dependencies)
- **Context:** Retail embedded edge nodes and till controllers require minimal runtime overhead and airtight security sandboxing.
- **Decision:** Rely solely on Python 3.10+ standard libraries (`decimal`, `csv`, `json`, `datetime`, `dataclasses`, `typing`, `argparse`, `unittest`).
- **Consequences:** Eliminates external attack surfaces, supply-chain vulnerabilities, and pip deployment overhead.

### DEC-003: Pure Data Domain Models with Dataclasses
- **Context:** High throughput scanning requires lightweight, serializable objects for catalog products, scan events, and bill line states.
- **Decision:** Implemented `@dataclass` domain objects in `src/models.py`. Encapsulated business constraints such as MRP ceiling directly into product properties.
- **Consequences:** Clean separation of concerns between state storage (`models.py`), lexing/parsing (`parser.py`), business rules orchestration (`engine.py`), and presentation (`formatter.py`).

### DEC-004: Pro-Rata Apportionment with Largest-Item Residual Adjustment
- **Context:** Dividing bill-level discounts (coupons, threshold, loyalty points) across line items often produces fractional paise that do not sum to the exact nominal discount.
- **Decision:** Implemented a two-pass apportionment algorithm. The first pass computes proportional shares quantized to `Decimal('0.01')`. The residual discrepancy $\Delta = D_{\text{nominal}} - \sum S_i$ is attributed to the item having the largest base value.
- **Consequences:** The sum of apportioned discounts always equals the nominal discount to the exact paisa, preventing penny-drift across itemized lines.

### DEC-005: Per-Slab GST Grouping and Line-Level Proportional Allocation
- **Context:** Indian GST statutory rules require tax computation and rounding per rate slab (`0%`, `5%`, `12%`, `18%`), rather than individual line items. However, partial returns require knowing the exact post-tax effective price paid for each individual line item.
- **Decision:** The engine groups lines by GST rate slab, rounds per slab to 2 decimal places, and then proportionally assigns slab GST to individual lines within that slab (adjusting residual paise on the largest taxable line).
- **Consequences:** Full statutory compliance with rate-slab rounding while enabling exact line-item refund calculations during returns.

---

## 2. Explicit Edge-Case Handling & Resolution Log

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

### Edge Case 4: Evening Clearance Scan at Exactly 20:00
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
