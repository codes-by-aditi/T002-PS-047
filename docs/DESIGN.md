# System Architecture & Technical Design Document

**Capstone Project PS-047: Supermarket POS Billing Engine**  
**Team IDT002: Aditi Anshu & Aditi Chaudhary**  
**Standard Library Only (Python 3.10+) | Zero External Dependencies | No UI**

---

## 1. System Overview & Core Objectives

The Supermarket Point of Sale (POS) Billing Engine is a high-precision, command-file-driven transactional billing core developed for modern enterprise retail environments. Built strictly using the Python 3.10+ Standard Library with zero third-party dependencies, the system eliminates floating-point rounding errors by enforcing `decimal.Decimal` with `ROUND_HALF_UP` throughout all monetary (2 decimals) and weight (3 decimals) operations.

The engine executes deterministic batch processing of product catalogs and scan events, implementing a strict 5-stage promotion precedence hierarchy, pro-rata discount apportionment, rate-slab GST consolidation, customer loyalty management, and a robust 7-day return policy with multi-buy promotional clawbacks.

---

## 2. Architectural Structure & Module Breakdown

The codebase is organized into a modular domain-driven architecture:

```
c:\Users\Dell\Desktop\Supermarket-POS\
├── src/
│   ├── __init__.py           # Package namespace and team metadata
│   ├── models.py             # Dataclasses and decimal quantization helpers
│   ├── parser.py             # Product catalog loader (CSV/JSON) & command stream parser
│   ├── engine.py             # Core transactional engine & business logic rules (BR-01 to BR-13)
│   └── formatter.py          # Deterministic terminal plain-text receipt, voucher, & report generators
├── data/
│   ├── products.csv          # Comprehensive product master dataset
│   └── commands.txt          # Scan command script demonstrating all transactions & edge cases
├── tests/
│   ├── __init__.py
│   └── test_pos_engine.py    # Complete unittest suite covering BR-01 to BR-13 & all 8 edge cases
├── docs/
│   ├── DESIGN.md             # Complete technical design & mathematical documentation
│   └── DECISION_LOG.md       # Explicit design rationale & edge-case resolutions
├── main.py                   # Command-Line Interface (CLI) entry point
└── README.md                 # Project overview, installation, CLI usage, & test verification
```

### Module Responsibilities

1. **`src/models.py`**:
   - `Product`: Master catalog entry with barcode, name, MRP, selling price, member price, GST rate, unit (`PC` or `KG`), category, tare weight, and offer group. Implements the MRP ceiling property (`effective_selling_price` and `effective_member_price`).
   - `BillLine`: Line item on a bill tracking gross total, item-level discounts, apportioned bill discounts, final taxable value, slab GST, and multi-buy unit consumption states.
   - `OfferLine`: Record of promotional discounts applied to a bill.
   - `Coupon`: Validated coupon discount parameters.
   - `Bill`: Represents an entire transaction lifecycle, from scan lines to rate-slab tax breakdown and grand total.
   - `ReturnLine` & `ReturnNote`: Audit voucher tracking refunded items, effective unit prices, and promotional clawbacks.
   - `LoyaltyAccount`: Customer loyalty point ledger tracking active and pending balances.
   - `TillZReport`: End-of-day till reconciliation record aggregating gross sales, discounts, net taxable value, consolidated GST by slab, customer returns, cash drawer revenue, and loyalty movements.

2. **`src/parser.py`**:
   - `load_products_csv` & `load_products_json`: Parses product catalogs with automated normalization of GST rates, categories, units, and decimal quantization.
   - `parse_command_line` & `parse_command_file`: Lexer and parser converting plain-text POS command streams into structured `ScanEvent` objects with timestamp tracking.

3. **`src/engine.py`**:
   - `POSEngine`: Primary stateful controller managing open bills, the product catalog, loyalty ledger, finalized bill history, and return tracking.
   - Coordinates the 8-stage discount, tax, and loyalty pipeline at checkout.

4. **`src/formatter.py`**:
   - Generates deterministic, human-readable terminal prints for retail invoices (`format_bill`), refund vouchers (`format_return_note`), and daily till reconciliations (`format_z_report`).

5. **`main.py`**:
   - CLI harness connecting arguments (`--products`, `--commands`, `--output`), driving execution, and serializing transaction artifacts.

---

## 3. Business Rules Mapping (BR-01 to BR-13)

| Rule ID | Name | Core Requirement | Engine Implementation |
| :--- | :--- | :--- | :--- |
| **BR-01** | Weighed Items | $\text{net\_weight} = \text{gross\_weight} - \text{tare\_weight}$. Min net weight $0.005\text{ kg}$. Line total rounded to 2 decimals. | `POSEngine.weigh_item`: Subtracts tare weight, asserts $\ge 0.005\text{ kg}$, computes $\text{net\_weight} \times \text{unit\_price}$ with `ROUND_HALF_UP`. |
| **BR-02** | MRP Ceiling | Unit price may never exceed MRP. | Implemented via `Product.effective_selling_price` and `Product.effective_member_price` as $\min(\text{price}, \text{MRP})$. |
| **BR-03** | Multi-Buy 'Buy 2 Get 1' | For every 3 units in an offer group, cheapest is 100% free. Sort units descending. Max 3 free per offer per bill. | `_apply_multibuy_offers`: Gathers units, sorts by unit price descending, groups into triples, awards cheapest unit free, marks 3 units as consumed. |
| **BR-04** | Category Discount | 10% off `FRESH` category scanned at or after 20:00. Excludes units consumed by multi-buy. | `_apply_category_discount`: Checks scan timestamp $\ge \text{20:00:00}$, computes 10% on unconsumed units. |
| **BR-05** | Offer Precedence | Strict fixed order: Multi-buy $\to$ Category $\to$ Member $\to$ Coupon $\to$ Threshold. Prior item offers consume units. | Checkout pipeline sequence: Multi-Buy consumes units first; Category consumes unconsumed FRESH units; Member pricing only applies to remaining unconsumed units. |
| **BR-06** | Member Pricing | Loyalty members get `member_price` on tagged SKUs on unconsumed units, capped at MRP. | `_apply_member_pricing`: Computes $\min(\text{member\_price}, \text{MRP})$, applies discount $\text{base\_sp} - \text{effective\_mp}$ on unconsumed units. |
| **BR-07** | Coupon Discount | Max 1 coupon per bill. `PCT`: $X\%$ off post-item subtotal, capped at Rs 200.00. `FIXED`: Rs $Y$ off, valid only if subtotal $\ge 3Y$. Pro-rata apportioned. | `_apply_coupon_discount`: Enforces single-coupon check, validates $3Y$ threshold, caps PCT at Rs 200.00, apportions pro-rata with largest-item adjustment. |
| **BR-08** | Bill Threshold | Based on subtotal after coupon: $\ge \text{Rs } 5,000 \to \text{Rs } 300$ off; $\ge \text{Rs } 2,000 \to \text{Rs } 100$ off. Pro-rata apportioned. | `_apply_threshold_discount`: Compares subtotal post-coupon, apportions Rs 300 or Rs 100 pro-rata with residual paisa adjustment on largest line. |
| **BR-09** | GST Computation | GST computed on final post-discount, post-burn taxable value. Grouped and rounded per rate slab (0%, 5%, 12%, 18%). | `_compute_gst_and_totals`: Aggregates taxable values per slab, computes slab tax and CGST/SGST, and rounds per rate slab. Pro-rata allocates slab GST to lines for returns. |
| **BR-10** | Loyalty Earn | Earn 1 point per full Rs 100 of post-GST bill value, excluding `TOBACCO` and `LIQUOR`. Points pending for 7 days. | `_apply_loyalty_earn`: Filters lines where category not in `(TOBACCO, LIQUOR)`, computes $\lfloor \text{eligible\_total} / 100 \rfloor$, posts as pending. |
| **BR-11** | Loyalty Burn | 1 pt = Rs 0.25. Multiples of 100 pts only. Capped at 20% of post-threshold bill subtotal. Applied before GST. | `_apply_loyalty_burn`: Validates 20% cap, determines max 100-pt multiple within cap and balance, applies burn discount pro-rata before GST. |
| **BR-12** | Returns & Window | Returns within 7 days against original bill up to 23:59:59 on Day +7. Weighed items non-returnable. Refund at effective price. | `process_return`: Verifies return window, blocks `KG` items, tracks returned quantities, calculates proportional refund per unit paid. |
| **BR-13** | Multi-Buy Return Reversal | Returning paid items that breaks group of 3 while free item kept triggers clawback of free item value. Free item return refund is Rs 0.00. | `process_return`: Tracks multi-buy group status; if free item returned $\to$ refund is Rs 0.00; if paid item returned breaks group $\to$ deducts free item value. |

---

## 4. Checkout Promotion Pipeline & Precedence Architecture

The checkout process executes sequentially across 8 distinct phases:

```
[ Active Bill Lines ]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 1: BR-03 Multi-Buy (Buy 2 Get 1)                 │
│ Triples sorted descending by price; cheapest free;     │
│ all 3 units marked as consumed.                        │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 2: BR-04 Category Clearance                      │
│ 10% off FRESH category scanned >= 20:00:00;            │
│ applied only to units NOT consumed by Multi-Buy.       │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 3: BR-06 Member Pricing (BR-05 Precedence)       │
│ Applied only to member-tagged units NOT consumed by    │
│ Multi-Buy or Category offers; capped at MRP (BR-02).   │
└────────────────────────────────────────────────────────┘
          │
          ▼
   [ Subtotal Post-Item-Offers ]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 4: BR-07 Coupon Discount                         │
│ PCT (max Rs 200) or FIXED (valid if subtotal >= 3*Y).  │
│ Apportioned pro-rata across items by value.            │
└────────────────────────────────────────────────────────┘
          │
          ▼
   [ Subtotal Post-Coupon ]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 5: BR-08 Bill-Level Threshold Discount           │
│ >= Rs 5000 -> Rs 300; >= Rs 2000 -> Rs 100.           │
│ Apportioned pro-rata across items by post-coupon value.│
└────────────────────────────────────────────────────────┘
          │
          ▼
   [ Subtotal Post-Threshold ]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 6: BR-11 Loyalty Burn                            │
│ 100-pt multiples; <= 20% post-threshold subtotal.      │
│ Apportioned pro-rata across items before GST.          │
└────────────────────────────────────────────────────────┘
          │
          ▼
   [ Final Taxable Value per Line ]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 7: BR-09 GST Computation                         │
│ Grouped by rate slab (0%, 5%, 12%, 18%); rounded per   │
│ slab; allocated to lines for return tracking.          │
└────────────────────────────────────────────────────────┘
          │
          ▼
   [ Grand Total (Post-GST) ]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│ Stage 8: BR-10 Loyalty Earn                            │
│ 1 pt per Rs 100 post-GST (excluding TOBACCO & LIQUOR); │
│ credited as PENDING for 7 days.                        │
└────────────────────────────────────────────────────────┘
```

---

## 5. Mathematical Formulations & Pro-Rata Apportionment

### 5.1 Weighed Items (BR-01)
For a product with unit `KG`, gross weight $W_{\text{gross}}$, tare weight $W_{\text{tare}}$, and effective unit price $P_{\text{unit}}$:
$$\text{net\_weight} = \text{quantize\_weight}(W_{\text{gross}} - W_{\text{tare}})$$
$$\text{If } \text{net\_weight} < 0.005\text{ kg} \implies \text{REJECT}$$
$$\text{Line Gross Total} = \text{quantize\_currency}(\text{net\_weight} \times P_{\text{unit}})$$

### 5.2 Multi-Buy Grouping (BR-03)
Given $N$ units of an offer group sorted descending by price:
$$P_1 \ge P_2 \ge P_3 \ge \dots \ge P_N$$
The number of eligible groups is:
$$K = \min\left(\left\lfloor \frac{N}{3} \right\rfloor, 3\right)$$
For each group $k \in \{0, \dots, K-1\}$, the units are:
$$\text{Group}_k = \{P_{3k}, P_{3k+1}, P_{3k+2}\}$$
$$\text{Discount}_k = P_{3k+2} \quad (\text{cheapest in the triple, awarded 100\% free})$$
$$\text{Total Multi-Buy Discount} = \sum_{k=0}^{K-1} P_{3k+2}$$
Any units $P_{3K}, \dots, P_{N-1}$ are outside the triples, receive 0 multi-buy discount, and remain available for subsequent promotions.

### 5.3 Pro-Rata Discount Apportionment Algorithm (BR-07, BR-08, BR-11)
When a bill-level discount $D_{\text{total}}$ is applied to a set of lines with base values $V_1, V_2, \dots, V_M$ having total base $V_{\text{total}} = \sum_{i=1}^M V_i$:

1. Calculate proportional shares:
$$S_i = \text{quantize\_currency}\left( \frac{V_i}{V_{\text{total}}} \times D_{\text{total}} \right)$$

2. Compute residual rounding drift:
$$\Delta = D_{\text{total}} - \sum_{i=1}^M S_i$$

3. Adjust the line with the largest base value $V_{\text{max}}$:
$$S_{\text{max}} \leftarrow S_{\text{max}} + \Delta$$

This guarantees:
$$\sum_{i=1}^M S_i \equiv D_{\text{total}} \quad \text{strictly to the exact paisa.}$$

### 5.4 GST Computation & Slab Rounding (BR-09)
For each GST rate slab $R \in \{0, 5, 12, 18\}$:
1. Aggregate taxable base:
$$T_R = \sum_{i \in \text{Slab } R} \text{Line Taxable Value}_i$$
2. Compute slab tax:
$$\text{GST}_R = \text{quantize\_currency}\left( T_R \times \frac{R}{100} \right)$$
$$\text{CGST}_R = \text{quantize\_currency}\left( \frac{\text{GST}_R}{2} \right)$$
$$\text{SGST}_R = \text{GST}_R - \text{CGST}_R$$
3. Total Bill GST:
$$\text{Total GST} = \sum_{R} \text{GST}_R$$
$$\text{Grand Total} = \sum_{i=1}^M \text{Line Taxable Value}_i + \text{Total GST}$$

### 5.5 Multi-Buy Return Reversal Algebra (BR-13)
When a customer purchases a multi-buy group ($P_1$ paid, $P_2$ paid, $P_3$ free):
- If the free item $P_3$ is returned:
$$\text{Refund} = \text{Rs } 0.00$$
- If a paid item $P_1$ is returned while $P_3$ was kept:
$$\text{Gross Refund} = \text{Effective Paid Price of } P_1$$
$$\text{Clawback Deduction} = P_3$$
$$\text{Net Refund} = \max(\text{Rs } 0.00, \text{Gross Refund} - \text{Clawback Deduction})$$
$$\text{Reversal Applied} \leftarrow \text{True (ensures clawback is never deducted twice)}$$

---

## 6. End-of-Day Till Reconciliation (Z-Report)

The Till Z-Report guarantees cash drawer balance reconciliation through the fundamental accounting identity:

$$\text{Gross Sales} - \text{Total Discounts} = \text{Net Taxable Sales}$$
$$\text{Net Taxable Sales} + \text{Total GST} = \text{Post-GST Sales}$$
$$\text{Cash Drawer Net Revenue} = \text{Post-GST Sales} - \text{Total Returns (Refunds)}$$

All sales figures, returns, slab taxes, and loyalty balances reconcile deterministically with 100% zero-drift precision.
