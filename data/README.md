# PS-047 – Supermarket POS Engine with Weighted Items, Offer Precedence and Loyalty — Sample Data Pack

Prepared by 10 SECONDS for Team T002.

## Files

| File | What it holds | Row count |
|---|---|---|
| `products.csv` | 300 SKUs (80 weighed per kg) with barcode, MRP, selling / member price, GST rate, tare and multi-buy group | 300 data rows |
| `offers.csv` | Multi-buy offer groups | 4 data rows |
| `store_parameters.csv` | Store timings, clearance, thresholds, loyalty and return parameters | 15 data rows |
| `coupons.csv` | 8 coupons (percentage and fixed value) | 8 data rows |
| `members.csv` | Loyalty members with opening point balance | 40 data rows |
| `commands.txt` | 50 bills over 2 days on 3 tills, 10 returns, Z-reports | 499 command lines (excluding comments) |

Row numbers quoted below are 1-based data-row numbers (the header is row 0). Line numbers for `commands.txt` are physical line numbers including comment lines.

## Column reference

Conventions: dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS` (24h, IST, no timezone suffix); money in Rs as plain decimals with 2 places (no commas, no symbol); percentages as plain numbers (12.5 means 12.5%); booleans `true`/`false`; IDs uppercase with a fixed prefix.

### `products.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `sku` | string | SKU-nnnn | — | primary key |
| `barcode` | string | EAN-13 | — | scan key used in commands.txt |
| `product_name` | string | — | — | — |
| `category` | enum | — | FRESH, STAPLES, DAIRY, SNACKS, BEVERAGES, PERSONAL_CARE, HOUSEHOLD, TOBACCO, LIQUOR | TOBACCO and LIQUOR earn no points |
| `unit` | enum | — | PIECE, KG | KG = weighed, price is per kg |
| `mrp` | decimal | Rs per unit (per kg for KG) | — | price ceiling; all prices in this pack are GST-exclusive taxable values, GST is added per rule 9 |
| `selling_price` | decimal | Rs per unit (per kg for KG) | — | may exceed MRP (data error) -> cap at MRP |
| `member_price` | decimal | Rs per unit | — | members only; subject to MRP ceiling; may be blank |
| `gst_rate` | int | percent | 0, 5, 12, 18 | — |
| `tare_kg` | decimal | kg, 3 dp | — | packaging tare for KG items; blank = 0; may be blank |
| `multibuy_group` | string | MB-nn | offers.csv | blank = not in a multi-buy; may be blank |

### `offers.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `offer_group` | string | MB-nn | — | — |
| `description` | string | — | — | — |
| `buy_qty` | int | — | — | — |
| `free_qty` | int | — | — | — |
| `max_free_per_bill` | int | — | — | — |
| `valid_from` | date | — | — | — |
| `valid_to` | date | — | — | inclusive |

### `store_parameters.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `param` | string | — | — | key |
| `value` | string | time HH:MM:SS, Rs, percent, kg or count | — | — |
| `notes` | string | — | — | — |

### `coupons.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `coupon_code` | string | — | — | — |
| `coupon_type` | enum | — | PERCENT, FIXED | — |
| `value` | decimal | percent or Rs | — | — |
| `max_discount` | decimal | Rs | — | PERCENT only; may be blank |
| `valid_from` | date | — | — | — |
| `valid_to` | date | — | — | inclusive |

### `members.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `member_id` | string | MEM-nnnn | — | — |
| `member_name` | string | — | — | — |
| `mobile` | string | 10 digits | — | — |
| `join_date` | date | — | — | — |
| `opening_points` | int | points | — | redeemable balance at the start of the pack period |

## Command file format

`commands.txt` holds one command per line in the form `COMMAND_NAME|arg1|arg2|...`. Commands must be processed strictly in file order. Lines starting with `#` are comments and blank lines are ignored. Empty optional arguments are written as nothing between the pipes. Every command used in this pack:

| Command | Arguments (in order) | Meaning |
|---|---|---|
| `OPEN_BILL` | `timestamp|bill_id|till_id|member_id` | Start a bill; empty member_id = non-member |
| `SCAN` | `timestamp|bill_id|barcode|qty` | PIECE item; unknown barcode is rejected |
| `SCAN_WEIGHED` | `timestamp|bill_id|barcode|gross_kg` | KG item; net = gross - tare; the scan timestamp is the 'weighed at' time |
| `QTY_OVERRIDE` | `timestamp|bill_id|line_no|new_qty` | Replace the quantity on a PIECE line |
| `VOID` | `timestamp|bill_id|line_no` | Remove a line from the bill |
| `APPLY_COUPON` | `timestamp|bill_id|coupon_code` | One coupon per bill |
| `REDEEM_POINTS` | `timestamp|bill_id|points` | Member burns points (multiples of 100, max 20% of bill) |
| `CLOSE_BILL` | `timestamp|bill_id|payment_mode` | Finalise: offers in precedence, GST, loyalty earn; payment_mode CASH, UPI, CARD |
| `RETURN` | `timestamp|return_id|till_id|original_bill_id|barcode|qty` | Return against the original bill |
| `Z_REPORT` | `timestamp|till_id|business_date` | Till totals for that date |

## Planted scenarios

Every edge case in the brief, mapped to the exact record where it occurs, followed by extra traps.

- **EC-01 Net weight of exactly 0.005 kg**
  - BILL-0002: SKU-0001 (Tomato (per kg), tare 0.010 kg) scanned with gross 0.015 kg -> net exactly 0.005 kg (not below 0.005, accept) — `commands.txt line 21`
- **EC-02 Member price above MRP**
  - BILL-0008 (member MEM-0001): SKU-0222 member_price 93.00 > MRP 89.00 (selling 84.00) — member price is capped at MRP — `commands.txt line 59; products.csv SKU-0222 (row 222)`
- **EC-03 Three items of different prices in one multi-buy group with 4th item added (which is free?)**
  - BILL-0014: MB-02 cross-SKU group scanned as SKU-0188 (245.00), SKU-0189 (210.00), SKU-0190 (180.00), then a 4th SKU-0191 (150.00) — one group of 3 forms, decide which item is free and which is left over — `commands.txt line 118`
- **EC-04 Evening clearance scan at exactly 20:00**
  - BILL-0021: SKU-0008 (Cauliflower (per kg)) SCAN_WEIGHED at exactly 2026-10-17 20:00:00 — boundary of 'weighed after 20:00' clearance; the next FRESH scan is clearly after — `commands.txt line 178`
- **EC-05 Subtotal exactly Rs 2,000 after coupon**
  - BILL-0035: non-member, 6 plain lines totalling Rs 2,100.00, coupon FLAT100 (fixed Rs 100, needs subtotal >= 300) -> subtotal after coupon exactly Rs 2,000.00 -> Rs 100 bill threshold applies (>=) — `commands.txt line 341`
- **EC-06 Redemption of 100 points on a Rs 100 bill (20% cap)**
  - BILL-0028 (member MEM-0002, opening balance 640 points): bill subtotal Rs 100.00, REDEEM_POINTS 100 (= Rs 25) exceeds the 20% cap of Rs 20 — `commands.txt line 255`
- **EC-07 Return of the free item in a multi-buy group**
  - BILL-0017: MB-03 group of 3 different biscuits, the cheapest SKU-0141 (110.00) is the free item; it is returned on 2026-10-20 — `commands.txt line 150; commands.txt line 496`
- **EC-08 Return on day 7 at store closing**
  - BILL-0020 closed on 2026-10-17; RETURN at 2026-10-24 22:00:00 = day 7 at store closing (STORE_CLOSE 22:00:00) — `commands.txt line 500`
- **Extra traps (not in the brief, but realistic):**
  - BILL-0005: SKU-0002 tare 0.005 kg, gross 0.009 kg -> net 0.004 kg < 0.005 — reject the scan (no bill line is created) — `commands.txt line 44`
  - BILL-0006: SKU-0003 has a blank tare_kg in products.csv — default tare 0, net = gross 1.237 kg — `commands.txt line 48`
  - BILL-0009: SKU-0218 selling_price 350.00 exceeds MRP 347.00 in the master — bill at MRP — `commands.txt line 63`
  - BILL-0048: three SKU-0017 (Watermelon (per kg), MB-04 buy-2-get-1) weighed after 20:00 — they are consumed by the multi-buy, so no 10% evening clearance on them — `commands.txt line 461`
  - BILL-0032: REDEEM_POINTS 250 — not a multiple of 100, reject the redemption — `commands.txt line 312`
  - BILL-0039: 10 units of SKU-0186 (MB-01 buy 2 get 1) — 3 groups of 3, so 3 free; the 10th is not part of a group (max 3 free per bill) — `commands.txt line 374`
  - BILL-0043: APPLY_COUPON SAVE10 then APPLY_COUPON FLAT50 — only one coupon per bill, reject the second — `commands.txt line 412`
  - RETURN against BILL-0035 8 days after the bill — outside the 7-day window, reject — `commands.txt line 501`
  - RETURN of weighed item SKU-0048 from BILL-0001 — weighed items are not returnable, reject — `commands.txt line 493`
  - RETURN of 2 of the 10 MB-01 soaps on BILL-0039 — breaks a buy-2-get-1 group, deduct the free item's value from the refund — `commands.txt line 497`
  - RETURN of SKU-0081 against BILL-0002, which never had that item — reject — `commands.txt line 276`
  - Partial return from BILL-0035 (threshold Rs 100 + coupon apportioned across lines) — refund the line's effective price after apportionment — `commands.txt line 499`

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.

## Output format expected at evaluation

Produce these CSV files (header row, same conventions as above, rows sorted as stated). Where the brief is silent on a format detail the choice below is binding for evaluation.

### `bill_lines.csv`

One row per accepted bill line (after voids/overrides), in bill_id, line_no order.

Columns, in order: `bill_id`, `line_no`, `sku`, `qty`, `net_kg`, `unit_price`, `gross_amount`, `multibuy_discount`, `category_discount`, `member_discount`, `coupon_share`, `threshold_share`, `points_share`, `taxable_value`, `gst_rate`, `gst_amount`, `line_total`

### `bills.csv`

One row per closed bill.

Columns, in order: `bill_id`, `till_id`, `member_id`, `close_ts`, `gross_total`, `item_offer_total`, `subtotal`, `coupon_code`, `coupon_discount`, `threshold_discount`, `points_redeemed`, `points_value`, `taxable_total`, `gst_0`, `gst_5`, `gst_12`, `gst_18`, `gst_total`, `bill_total`, `points_earned`

### `offer_lines.csv`

One row per offer applied, in bill and precedence order.

Columns, in order: `bill_id`, `offer_type`, `offer_ref`, `line_no`, `discount_amount`

### `return_notes.csv`

One row per RETURN command in file order.

Columns, in order: `return_id`, `original_bill_id`, `sku`, `qty`, `status`, `refund_amount`, `multibuy_clawback`, `reason`

### `z_report.csv`

One row per Z_REPORT command.

Columns, in order: `till_id`, `business_date`, `bills_count`, `gross_sales`, `total_discounts`, `gst_total`, `net_sales`, `returns_count`, `refunds_total`, `cash`, `upi`, `card`

Binding choices: `offer_type` is MULTIBUY, CATEGORY, MEMBER, COUPON, THRESHOLD or POINTS; return `status` is ACCEPTED or REJECTED; rejected scans produce no bill line; `net_kg` is blank for PIECE lines; points earned are reported on the bill but credited after the 7-day window.
