# Supermarket POS Billing Engine with Weighted Items, Offer Precedence, and Loyalty

**Capstone Project PS-047 | Team IDT002**  
**Authors:** Aditi Anshu (1AT24CD004) & Aditi Chaudhary (1AT24CD005)  
**Section:** CSDS A  
**Technology:** Python 3.10+ (Standard Library Only, Zero External Dependencies)  
**Execution Paradigm:** Command-File Driven Terminal Backend (Strictly No UI)

---

## 1. Project Overview

The **Supermarket POS Billing Engine** is an enterprise-grade transactional retail core engineered for supermarket till operations. Built exclusively with Python 3.10+ standard libraries, the engine ingests product catalogs and sequential POS command streams to execute high-precision billing without any graphical or web overhead.

### Key Capabilities:
- **Zero-Float Guarantee:** Pure `decimal.Decimal` arithmetic quantized with `ROUND_HALF_UP` (2 decimal places for currency, 3 decimal places for weights). Binary floating-point representation errors are completely eliminated.
- **Weighed Item Scale Integration:** Accurate tare subtraction ($\text{net} = \text{gross} - \text{tare}$) with legal scale sensitivity cutoff ($\ge 0.005\text{ kg}$).
- **Statutory MRP Ceiling:** Automatic capping of selling and member prices to packaging Maximum Retail Price (MRP).
- **Strict 5-Stage Offer Precedence:** Sequential promotion evaluation (Multi-Buy $\to$ Category Discount $\to$ Member Pricing $\to$ Coupon $\to$ Bill Threshold) with physical unit consumption tracking.
- **Two-Pass Pro-Rata Apportionment:** Even distribution of bill-level discounts across items, allocating odd residual paise to the largest line item for exact-to-the-paisa totals.
- **Indian GST Compliance:** Tax calculation and rounding per rate slab (`0%`, `5%`, `12%`, `18%`), with proportional line allocation for return tracking.
- **Customer Loyalty Engine:** Accrual of 1 point per Rs 100 post-GST (excluding tobacco and liquor) with 7-day pending maturity; redemption at Rs 0.25/pt in 100-point multiples (capped at 20% before GST).
- **Audit-Compliant Returns:** 7-day return validation window, exclusion of weighed perishables, and automatic clawback of free multi-buy items when groups of 3 are broken.
- **Till Z-Report Reconciliation:** End-of-day balancing reconciling gross sales, discounts, slab taxes, refunds, and cash drawer net sales.

---

## 2. Directory Structure

```
Supermarket-POS/
├── src/
│   ├── __init__.py           # Package namespace, version, and author metadata
│   ├── models.py             # Pure domain entities, dataclasses, and Decimal quantization
│   ├── parser.py             # CSV/JSON catalog loader and command stream lexer
│   ├── engine.py             # Transaction orchestrator implementing BR-01 through BR-13
│   └── formatter.py          # Deterministic plain-text fiscal invoices, return notes, & Z-reports
├── data/
│   ├── products.csv          # Master product catalog covering all categories and units
│   └── commands.txt          # POS batch command script exercising all normal and edge scenarios
├── tests/
│   ├── __init__.py
│   └── test_pos_engine.py    # 23 automated unit tests verifying BR-01..BR-13 and Edge Cases 1..8
├── docs/
│   ├── DESIGN.md             # Technical design, glossary, Mermaid diagrams, and mathematical specs
│   └── DECISION_LOG.md       # Architectural decision register and edge-case resolution logs
├── output/                   # Generated transaction files and fiscal audit records
│   ├── BILL-001.txt          # Retail Invoice: Member grocery shopping with weighed item & coupon
│   ├── BILL-002.txt          # Retail Invoice: Evening FRESH clearance, Multi-Buy, & Loyalty Burn
│   ├── BILL-003.txt          # Retail Invoice: High-value purchase, bill threshold, & tobacco exclusion
│   ├── RET-001.txt           # Return & Refund Voucher: 7-day return audit
│   ├── Z_REPORT_2026-11-15.txt # Till Z-Report: Daily sales, GST consolidation, & drawer balance
│   └── Z_REPORT_2026-11-17.txt # Till Z-Report: Return reconciliation
├── main.py                   # Command-Line Interface (CLI) entry point
├── .gitignore                # Git repository hygiene ignoring caches and temporary files
└── README.md                 # Complete project documentation and execution guide
```

---

## 3. How to Run the Program

### A. Executing the CLI Billing Engine
Run the main script by providing the product catalog, scan commands file, and output directory:

```bash
python main.py --products data/products.csv --commands data/commands.txt --output output/
```

#### CLI Options:
| Argument | Flag | Required | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `--products` | `-p` | **Yes** | — | Path to product catalog file (`.csv` or `.json`) |
| `--commands` | `-c` | **Yes** | — | Path to scan commands text file (`.txt`) |
| `--output` | `-o` | No | `output` | Directory where generated bills, vouchers, and Z-reports are saved |

#### Expected Console Output:
```text
======================================================================
  SUPERMARKET POS BILLING ENGINE - CAPSTONE PS-047
  Team IDT002: Aditi Anshu & Aditi Chaudhary
======================================================================
Loading Product Master: data\products.csv...
Successfully loaded 16 products.
Parsing Command File: data\commands.txt...
Successfully parsed 27 command events.

Executing POS Transaction Pipeline...
  [CHECKOUT] Finalized Bill BILL-001 -> Rs 627.35 (Saved to output\BILL-001.txt)
  [CHECKOUT] Finalized Bill BILL-002 -> Rs 342.22 (Saved to output\BILL-002.txt)
  [CHECKOUT] Finalized Bill BILL-003 -> Rs 7611.00 (Saved to output\BILL-003.txt)
  [RETURN] Processed Return RET-001 -> Refund Rs 122.85 (Saved to output\RET-001.txt)
  [Z-REPORT] Generated Z-Report for 2026-11-15 -> Net Revenue Rs 8580.57 (Saved to output\Z_REPORT_2026-11-15.txt)
  [Z-REPORT] Generated Z-Report for 2026-11-17 -> Net Revenue Rs -122.85 (Saved to output\Z_REPORT_2026-11-17.txt)

======================================================================
  EXECUTION COMPLETE SUMMARY
======================================================================
  Total Bills Processed   : 3
  Total Returns Processed : 1
  Total Z-Reports Emitted : 2
  All outputs saved to    : C:\Users\Dell\Desktop\Supermarket-POS\output
======================================================================
```

---

## 4. How to Run the Unit Test Suite

Run Python's built-in `unittest` discovery:

```bash
python -m unittest discover -s tests -v
```

All **23 unit tests** pass cleanly with zero warnings, failures, or errors:
```text
test_br01_weighed_items_tare_subtraction (test_pos_engine.TestPOSBillingEngine) ... ok
test_br02_mrp_ceiling_enforcement (test_pos_engine.TestPOSBillingEngine) ... ok
test_br03_multibuy_buy2_get1_free (test_pos_engine.TestPOSBillingEngine) ... ok
test_br04_category_discount_evening_clearance (test_pos_engine.TestPOSBillingEngine) ... ok
test_br05_offer_precedence_exclusion (test_pos_engine.TestPOSBillingEngine) ... ok
test_br06_member_pricing_on_unconsumed_items (test_pos_engine.TestPOSBillingEngine) ... ok
test_br07_coupon_percentage_and_fixed (test_pos_engine.TestPOSBillingEngine) ... ok
test_br08_bill_threshold_discount (test_pos_engine.TestPOSBillingEngine) ... ok
test_br09_gst_rate_slab_grouping_and_rounding (test_pos_engine.TestPOSBillingEngine) ... ok
test_br10_loyalty_earn_and_exclusions (test_pos_engine.TestPOSBillingEngine) ... ok
test_br11_loyalty_burn_rules (test_pos_engine.TestPOSBillingEngine) ... ok
test_br12_returns_and_window (test_pos_engine.TestPOSBillingEngine) ... ok
test_br13_multibuy_return_reversal (test_pos_engine.TestPOSBillingEngine) ... ok
test_edge_case_1_net_weight_boundary (test_pos_engine.TestPOSBillingEngine) ... ok
test_edge_case_2_member_price_above_mrp (test_pos_engine.TestPOSBillingEngine) ... ok
test_edge_case_3_four_items_different_prices_multibuy (test_pos_engine.TestPOSBillingEngine) ... ok
test_edge_case_4_evening_clearance_exactly_20_00 (test_pos_engine.TestPOSBillingEngine) ... ok
test_edge_case_5_subtotal_exactly_2000_threshold (test_pos_engine.TestPOSBillingEngine) ... ok
test_edge_case_6_loyalty_burn_20_percent_cap_blocked (test_pos_engine.TestPOSBillingEngine) ... ok
test_edge_case_7_return_free_item_multibuy (test_pos_engine.TestPOSBillingEngine) ... ok
test_edge_case_8_return_day_7_closing_vs_day_8 (test_pos_engine.TestPOSBillingEngine) ... ok
test_override_qty_and_void (test_pos_engine.TestPOSBillingEngine) ... ok
test_till_z_report_reconciliation (test_pos_engine.TestPOSBillingEngine) ... ok
----------------------------------------------------------------------
Ran 23 tests in 0.010s

OK
```

---

## 5. POS Command File Syntax

The engine reads ASCII command streams line-by-line. Blank lines and lines beginning with `#` are ignored.

| Command Syntax | Parameters | Description |
| :--- | :--- | :--- |
| `START_BILL <bill_id> <timestamp> [member_id]` | Bill ID, ISO timestamp, optional Member ID | Opens a new transaction session for a customer |
| `SCAN <barcode> [qty] [timestamp]` | Barcode, optional quantity (default 1), timestamp | Scans a barcoded packaged item (`unit == 'PC'`) |
| `WEIGH <barcode> <gross_weight> [timestamp]` | Barcode, gross scale weight in kg, timestamp | Weighs a bulk item; computes net weight after tare |
| `OVERRIDE_QTY <line_no_or_barcode> <new_qty>` | Target line number or barcode, new quantity | Updates the scanned quantity of an existing line |
| `VOID <line_no_or_barcode>` | Target line number or barcode | Removes the item line from the active bill |
| `APPLY_COUPON <coupon_code> <PCT\|FIXED> <value>` | Coupon code, discount type, value | Adds a coupon to be applied at checkout (max 1) |
| `REDEEM_POINTS <points>` | Number of points to burn | Requests loyalty points redemption (multiples of 100) |
| `CHECKOUT` | None | Executes the 8-stage promotion pipeline and finalizes bill |
| `RETURN <return_id> <original_bill_id> <timestamp> <barcode:qty,...>` | Return ID, Original Bill ID, timestamp, item pairs | Processes full/partial return and issues refund voucher |
| `Z_REPORT <date>` | Business date (`YYYY-MM-DD`) | Reconciles till transactions and emits daily Z-report |

---

## 6. Business Rules Register (BR-01 through BR-13)

- **BR-01 (Weighed Items):** $\text{net\_weight} = \text{gross\_weight} - \text{tare\_weight}$. Reject if $\text{net\_weight} < 0.005\text{ kg}$. Line total rounded half-up to 2 decimals.
- **BR-02 (MRP Ceiling):** Unit price may never exceed MRP. Effective price = $\min(\text{price}, \text{MRP})$.
- **BR-03 (Multi-Buy 'Buy 2 Get 1'):** Triples sorted descending by price; cheapest unit is 100% free. Max 3 free items per bill per offer.
- **BR-04 (Category Discount):** 10% off items in category `FRESH` scanned at or after 20:00:00. Applies only to unconsumed units.
- **BR-05 (Offer Precedence):** Rigid fixed order: Multi-buy $\to$ Category $\to$ Member $\to$ Coupon $\to$ Threshold. Prior promotions consume physical units.
- **BR-06 (Member Pricing):** Loyalty members receive `member_price` on tagged SKUs on unconsumed units, capped at MRP (BR-02).
- **BR-07 (Coupon):** Max 1 coupon per bill. `PCT`: capped at Rs 200.00. `FIXED`: valid only if subtotal $\ge 3 \times \text{value}$. Apportioned pro-rata.
- **BR-08 (Bill Threshold):** Subtotal post-coupon $\ge \text{Rs } 5,000 \to \text{Rs } 300$ off; $\ge \text{Rs } 2,000 \to \text{Rs } 100$ off. Apportioned pro-rata.
- **BR-09 (GST Computation):** GST computed on taxable value after all discounts and loyalty burn. Grouped and rounded per rate slab (`0%`, `5%`, `12%`, `18%`), not per line.
- **BR-10 (Loyalty Earn):** 1 point per full Rs 100 post-GST value, excluding `TOBACCO` and `LIQUOR`. Points pending for 7 days.
- **BR-11 (Loyalty Burn):** 1 point = Rs 0.25 in 100-pt multiples, capped at 20% of post-threshold subtotal. Applied before GST and apportioned pro-rata.
- **BR-12 (Returns):** Allowed within 7 days ($\le \text{bill date} + 7\text{ days}$ up to 23:59:59). Weighed items (`KG`) strictly non-returnable. Refund equals effective price paid.
- **BR-13 (Multi-Buy Return Reversal):** Returning a paid item that breaks an active group of 3 while the free item was kept claws back the free item's value. Returning the free item yields Rs 0.00 refund.

---

## 7. Explicit Edge Cases Handled

1. **Net Weight Scale Boundary (EC-1):** Net weight of exactly 0.005 kg accepted; 0.004 kg rejected with `ValueError`.
2. **Member Price Above MRP (EC-2):** Member price capped at packaging MRP ceiling (`min(member_price, mrp)`).
3. **Four Items in Multi-Buy (EC-3):** Top 3 items form triple with cheapest free; 4th item remains full price.
4. **Evening Clearance Boundary (EC-4):** Exactly 20:00:00 receives 10% discount; 19:59:59 does not.
5. **Threshold Boundary (EC-5):** Exactly Rs 2,000.00 post-coupon triggers Rs 100.00 discount.
6. **Loyalty 20% Cap Blocked (EC-6):** 100 points (Rs 25.00) on Rs 100.00 bill exceeds 20% cap (Rs 20.00) $\to$ 0 points redeemed.
7. **Free Item Return (EC-7):** Returning the promotional free item in a multi-buy group yields Rs 0.00 refund.
8. **7-Day Return Window (EC-8):** Return on Day +7 at 23:59:59 accepted; Day +8 at 00:00:00 rejected with `ValueError`.

---

## 8. Sample Output Walkthrough

All generated text artifacts are placed in `output/`:

1. **`BILL-001.txt`:** Member grocery shopping showing:
   - Packaged and weighed items (`Fresh Tomatoes` 1.500 kg net weight after 0.020 kg tare).
   - Member pricing savings applied on eligible unconsumed items.
   - Percentage coupon (`SAVE10`) apportioned pro-rata.
   - GST consolidated by 0%, 5%, and 12% rate slabs.
   - 6 pending loyalty points earned.
2. **`BILL-002.txt`:** Evening perishables and multi-buy showing:
   - Scanned at 20:15:00 triggering 10% evening clearance on `Fresh Exotic Kiwi Pack`.
   - Multi-buy triple on chocolates (`Dark 100`, `Milk 80`, `White 60`, `Almond 40`) awarding `White Chocolate` (Rs 60.00) free.
   - Redemption of 100 loyalty points (Rs 25.00) within the 20% cap.
3. **`BILL-003.txt`:** High-value purchase showing:
   - Bill total exceeding Rs 5,000.00 triggering the Rs 300.00 threshold discount.
   - Inclusion of tobacco products (`Premium Cigarettes 20s`) properly excluded from loyalty accrual.
4. **`RET-001.txt`:** Product return voucher:
   - Return of 1 unit of `Premium Basmati Rice 5kg` from `BILL-001`.
   - Disburses exact effective post-discount post-tax price paid (Rs 122.85).
5. **`Z_REPORT_2026-11-15.txt` & `Z_REPORT_2026-11-17.txt`:** Till Z-reports:
   - Balancing gross sales, total discounts, net taxable value, consolidated GST by slab, returns, and cash drawer net revenue.

---

## 9. Capstone Project Compliance Checklist

- [x] **Zero External Dependencies:** Built strictly using Python 3.10+ standard libraries (`decimal`, `csv`, `json`, `datetime`, `dataclasses`, `typing`, `argparse`, `unittest`).
- [x] **No UI / Command-File Driven:** Executed purely via CLI batch processing with ASCII plain-text report generation.
- [x] **Pure Decimal Arithmetic:** Zero usage of binary floats in financial and weight paths.
- [x] **100% Test Coverage:** All 13 business rules and all 8 edge cases covered by automated unit tests.
- [x] **Team Metadata:** Proper attribution to Aditi Anshu (1AT24CD004) & Aditi Chaudhary (1AT24CD005), Team IDT002, Project PS-047.
- [x] **Complete Documentation:** Includes `README.md`, `docs/DESIGN.md` (with Glossary, Class Diagram, State Diagram, and Business-Rule Register), and `docs/DECISION_LOG.md`.
