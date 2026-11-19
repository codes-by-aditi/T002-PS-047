# Supermarket POS Billing Engine — PS-047

**Team IDT002 | Authors: Aditi Anshu (1AT24CD004) and Aditi Chaudhary (1AT24CD005)**

**Python 3.10+ | Standard library only | Command-file driven terminal backend**

## 1. Project Overview

This project processes supermarket point-of-sale commands in chronological file order. It supports piece and weighed products, MRP price caps, multi-buy offers, evening clearance, member pricing, coupons, bill thresholds, GST slabs, loyalty points, returns, and till Z-reports. It has no GUI or web interface.

All currency calculations use `decimal.Decimal` with `ROUND_HALF_UP`; weights are quantized to three decimal places.

## 2. Project Structure

```text
PS047_Supermarket_POS_Project/
├── main.py
├── src/
│   ├── __init__.py
│   ├── models.py
│   ├── parser.py
│   ├── engine.py
│   └── formatter.py
├── data/
│   ├── products.csv
│   ├── offers.csv
│   ├── store_parameters.csv
│   ├── coupons.csv
│   ├── members.csv
│   ├── commands.txt
│   └── DATA_PACK_README.md
├── tests/
│   ├── __init__.py
│   ├── test_pos_engine.py
│   └── test_data_pack_integration.py
├── docs/
│   ├── DESIGN.md
│   ├── DECISION_LOG.md
│   └── WORK_SPLIT.md
└── output/                    # Generated invoices, vouchers, reports, and evaluation CSVs
```

## 3. Supplied Data Pack

The `data/` directory contains the provided data without changing its values:

- 300 products (including 80 weighed products)
- 4 multi-buy offer groups
- 15 store parameters
- 8 coupons
- 40 loyalty members
- 499 parsed command events representing 50 bills, 10 returns, and 6 Z-reports

The full source data dictionary and planted edge cases are in `data/DATA_PACK_README.md`.

## 4. How to Run the Complete Project

Open a terminal in the project root folder. Confirm Python 3.10 or newer:

```bash
python --version
```

Run the supplied full event stream:

```bash
python main.py --products data/products.csv --commands data/commands.txt --output output
```

The CLI automatically loads `coupons.csv`, `members.csv`, `store_parameters.csv`, and `offers.csv` from the same `data/` directory as the product file. You can also specify optional paths explicitly:

```bash
python main.py --products data/products.csv --commands data/commands.txt --output output --coupons data/coupons.csv --members data/members.csv --parameters data/store_parameters.csv
```

### Expected Execution Summary

```text
Successfully loaded 300 products.
Loaded 8 coupons.
Loaded 40 loyalty members.
Loaded 15 store parameters.
Loaded 4 multi-buy offers.
Successfully parsed 499 command events.
Total Bills Finalized   : 50
Total Returns Processed : 10
Total Z-Reports Emitted : 6
```

One deliberately invalid weighed scan in the data pack has net weight below the minimum and is rejected at event level; it does not create a bill line. Rejected return commands are retained in `return_notes.csv` with status `REJECTED`.

## 5. Generated Output

The run creates individual `.txt` invoices, return vouchers, and till reports, plus the five evaluation CSVs:

| Output | Contents |
|---|---|
| `bill_lines.csv` | Accepted bill lines after voids and quantity overrides |
| `bills.csv` | One row per closed bill |
| `offer_lines.csv` | Applied offer/discount records in precedence order |
| `return_notes.csv` | Accepted and rejected return command outcomes |
| `z_report.csv` | One row per Z_REPORT command |

The current supplied-data run produces 355 bill-line rows, 50 bill rows, 65 offer rows, 10 return rows, and 6 Z-report rows (excluding headers).

## 6. Run Automated Tests

From the project root:

```bash
python -m unittest discover -s tests -v
```

The unit suite checks BR-01 to BR-13 and the eight stated edge cases. The integration test processes the complete supplied command stream and checks the transaction counts and planted return/clawback outcomes.

## 7. Command Format

Commands are pipe-delimited and processed in file order. The supported commands are:

- `OPEN_BILL|timestamp|bill_id|till_id|member_id`
- `SCAN|timestamp|bill_id|barcode|qty`
- `SCAN_WEIGHED|timestamp|bill_id|barcode|gross_kg`
- `QTY_OVERRIDE|timestamp|bill_id|line_no|new_qty`
- `VOID|timestamp|bill_id|line_no`
- `APPLY_COUPON|timestamp|bill_id|coupon_code`
- `REDEEM_POINTS|timestamp|bill_id|points`
- `CLOSE_BILL|timestamp|bill_id|payment_mode`
- `RETURN|timestamp|return_id|till_id|original_bill_id|barcode|qty`
- `Z_REPORT|timestamp|till_id|business_date`

See the data-pack README for argument details, units, expected CSV columns, and planted cases.

## 8. Business Rules

The engine follows the supplied team specification for:

1. Tare subtraction and minimum net weight
2. MRP ceiling
3. Multi-buy offers (cheapest eligible unit free)
4. Evening FRESH clearance
5. Offer precedence and unit consumption
6. Member pricing
7. Coupon limits and proration
8. Bill threshold discounts
9. GST slab calculation
10. Loyalty earning and maturity
11. Loyalty redemption and cap
12. Return window and weighed-item restrictions
13. Multi-buy return clawback

Detailed technical decisions and diagrams are in `docs/DESIGN.md` and `docs/DECISION_LOG.md`.

## 9. Contribution and GitHub Attribution

The top-level `src/`, `main.py`, tests, and generated `output/` form the runnable integrated project. See `docs/WORK_SPLIT.md` before making individual author claims or splitting commits. Do not attribute existing team files to one person unless your Git history or team records establish who wrote them.

## 10. Validation Report

See `docs/VALIDATION_RESULTS.md` for the test result, full-stream counts, output row counts, and planted outcomes checked.
