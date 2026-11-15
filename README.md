# Supermarket POS Billing Engine

**Capstone Project PS-047 | Team IDT002**  
**Authors:** Aditi Anshu & Aditi Chaudhary  
**Technology:** Python 3.10+ (Standard Library Only, Zero External Dependencies, No UI)

---

## 1. Project Overview

The Supermarket POS Billing Engine is an enterprise-grade retail transactional engine built to handle high-precision point-of-sale calculations without third-party dependencies. It processes product catalogs (CSV or JSON) and scan command files, enforcing strict promotional precedence, pro-rata discount apportionment, Indian GST rate-slab grouping, loyalty earn and burn, 7-day returns with promotional clawbacks, and end-of-day till Z-report reconciliation.

All currency operations use `decimal.Decimal` with `ROUND_HALF_UP` to 2 decimal places (paisa), and all weight operations use 3 decimal places (grams). Binary floating-point arithmetic is strictly prohibited.

---

## 2. Directory Structure

```
Supermarket-POS/
├── src/
│   ├── __init__.py           # Package initialization & capstone metadata
│   ├── models.py             # Domain models (Product, ScanEvent, BillLine, Bill, etc.)
│   ├── parser.py             # Product master (CSV/JSON) & command stream parser
│   ├── engine.py             # Core billing engine implementing BR-01 to BR-13
│   └── formatter.py          # Deterministic plain-text generators for invoices & reports
├── data/
│   ├── products.csv          # Sample product master catalog
│   └── commands.txt          # Scan command stream exercising all rules & edge cases
├── tests/
│   ├── __init__.py
│   └── test_pos_engine.py    # Complete unittest test suite covering BR-01 to BR-13 & all 8 edge cases
├── docs/
│   ├── DESIGN.md             # System design document with mathematical formulations
│   └── DECISION_LOG.md       # Explicit technical decisions & edge-case resolutions
├── output/                   # Generated invoices, refund vouchers, & Z-reports
├── main.py                   # Command-Line Interface (CLI) entry point
└── README.md                 # Project documentation & execution guide
```

---

## 3. Business Rules (BR-01 to BR-13)

- **BR-01 (Weighed Items):** $\text{net\_weight} = \text{gross\_weight} - \text{tare\_weight}$. Reject if $\text{net\_weight} < 0.005\text{ kg}$. Line total rounded to 2 decimals using `ROUND_HALF_UP`.
- **BR-02 (MRP Ceiling):** No item may ever be billed above its MRP. Unit price is capped at $\min(\text{price}, \text{MRP})$.
- **BR-03 (Multi-Buy 'Buy 2 Get 1'):** For every 3 units in an offer group, the cheapest unit is 100% free. Units are sorted descending by price so highest triples are formed first. Capped at maximum 3 free items per bill per offer.
- **BR-04 (Category Discount):** 10% off items in category `FRESH` scanned at or after 20:00 (`time >= 20:00:00`). Never applies to units already consumed by multi-buy.
- **BR-05 (Offer Precedence):** Applied in strict fixed order:
  1. Multi-buy
  2. Category discount
  3. Member pricing
  4. Coupon
  5. Bill-level threshold  
  Units consumed by an earlier item-level offer are excluded from later item-level offers.
- **BR-06 (Member Pricing):** Loyalty members get `member_price` on tagged SKUs for units not consumed by multi-buy or category discount, subject to MRP ceiling (BR-02).
- **BR-07 (Coupon):** Maximum 1 coupon per bill, applied to subtotal post-item-offers:
  - `PCT`: $X\%$ off, capped at Rs 200.00.
  - `FIXED`: Rs $Y$ off, valid ONLY if subtotal $\ge 3Y$ (rejected otherwise).  
  Apportioned pro-rata across items by post-item-offer value.
- **BR-08 (Bill Threshold):** Based on subtotal after coupon:
  - $\ge \text{Rs } 5,000.00 \to \text{Rs } 300.00$ off
  - $\ge \text{Rs } 2,000.00 \to \text{Rs } 100.00$ off  
  Apportioned pro-rata across items, adjusting largest item by residual paisa.
- **BR-09 (GST Computation):** GST is computed on the final post-discount, post-loyalty-burn taxable value. Grouped and rounded per rate slab (`0%`, `5%`, `12%`, `18%`), NOT per individual item.
- **BR-10 (Loyalty Earn):** Earn 1 point per full Rs 100 ($\lfloor \text{post-GST total} / 100 \rfloor$), excluding `TOBACCO` and `LIQUOR` categories. Points remain `PENDING` for 7 days.
- **BR-11 (Loyalty Burn):** 1 point = Rs 0.25. Allowed ONLY in multiples of 100 points, capped at 20% of post-threshold bill subtotal. Applied before GST and apportioned pro-rata.
- **BR-12 (Returns):** Returns allowed within 7 days ($\le \text{bill date} + 7\text{ days}$ up to 23:59:59) against original `bill_id`. Weighed items (`unit == KG`) are strictly non-returnable. Refund equals item's effective final price on the bill.
- **BR-13 (Multi-Buy Return Reversal):** Returning a paid item that breaks an active group of 3 while the free item was kept triggers deduction of the free item's original value from the refund. If the free item itself is returned, its refund is Rs 0.00.

---

## 4. Command File Specification

The parser accepts plain-text commands (`#` denotes comments):

| Command Format | Description | Example |
| :--- | :--- | :--- |
| `START_BILL <bill_id> <timestamp> [member_id]` | Open a new billing session | `START_BILL BILL-001 2026-11-15T18:30:00 MEM001` |
| `SCAN <barcode> [qty] [timestamp]` | Scan packaged item | `SCAN 8901001 2` |
| `WEIGH <barcode> <gross_weight> [timestamp]` | Weigh bulk item | `WEIGH 8902002 1.520` |
| `OVERRIDE_QTY <line_no_or_barcode> <new_qty>` | Override item quantity | `OVERRIDE_QTY 1 3` |
| `VOID <line_no_or_barcode>` | Remove item from bill | `VOID 8904002` |
| `APPLY_COUPON <coupon_code> <PCT\|FIXED> <value>` | Apply bill coupon | `APPLY_COUPON SAVE10 PCT 10` |
| `REDEEM_POINTS <points>` | Redeem loyalty points | `REDEEM_POINTS 100` |
| `CHECKOUT` | Finalize bill & print receipt | `CHECKOUT` |
| `RETURN <ret_id> <orig_bill_id> <ts> <item:qty,...>` | Process return & refund | `RETURN RET-001 BILL-001 2026-11-17T11:00:00 8901001:1` |
| `Z_REPORT <date>` | Generate till Z-report | `Z_REPORT 2026-11-15` |

---

## 5. Execution Instructions

### Running the CLI Application
Execute `main.py` with the sample product catalog and command file:

```bash
python main.py --products data/products.csv --commands data/commands.txt --output output/
```

### Running the Unit Test Suite
Run the complete automated test suite covering all 13 Business Rules and 8 Edge Cases:

```bash
python -m unittest discover -s tests -v
```

---

## 6. Edge Cases Handled & Tested

1. **Net Weight Boundary:** Exactly 0.005 kg is accepted; 0.004 kg is rejected.
2. **Member Price Above MRP:** Capped at MRP ceiling.
3. **Four Items in Multi-Buy:** Top 3 items form triple with cheapest free; 4th item remains full price.
4. **Evening Clearance Boundary:** Exactly 20:00:00 qualifies for 10% discount; 19:59:59 does not.
5. **Threshold Boundary:** Exactly Rs 2,000.00 post-coupon triggers Rs 100.00 discount.
6. **Loyalty 20% Cap Blocked:** 100 points (Rs 25.00) on Rs 100.00 bill exceeds 20% cap (Rs 20.00) $\to$ 0 points redeemed.
7. **Free Item Return:** Returning the free item in a multi-buy group yields Rs 0.00 refund.
8. **7-Day Return Window:** Day +7 at 23:59:59 accepted; Day +8 at 00:00:00 rejected.
