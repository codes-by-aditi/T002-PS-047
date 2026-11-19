# Validation results

Validation was performed using the supplied PS-047 data pack included in `data/`.

## Automated tests

Command:

```bash
python -m unittest discover -s tests -v
```

Result: **24 tests passed** (23 original unit tests, with two rejection assertions aligned to the supplied data-pack contract, plus one full-stream integration test).

## Full event stream

Command:

```bash
python main.py --products data/products.csv --commands data/commands.txt --output output
```

Observed:
- Products loaded: 300
- Coupons loaded: 8
- Loyalty members loaded: 40
- Store parameters loaded: 15
- Multi-buy offer groups loaded: 4
- Parsed command events: 499
- Closed bills: 50
- Return records: 10
- Z-reports: 6

## Evaluation CSV row counts

| File | Data rows |
|---|---:|
| `bill_lines.csv` | 355 |
| `bills.csv` | 50 |
| `offer_lines.csv` | 65 |
| `return_notes.csv` | 10 |
| `z_report.csv` | 6 |

## Planted outcomes checked

- Below-minimum weighed scan is rejected and does not create a bill line.
- Return of an item not present on the original bill is rejected.
- Weighed-item return is rejected.
- Return of the free item in a multi-buy group has zero refund.
- Partial return of two identical multi-buy soaps creates a Rs 60.00 clawback and Rs 39.12 refund.
- Day +8 return is rejected as outside the return window.

The sample data pack does not provide golden expected CSV files; therefore these results are structural and rule-based validation, not a field-by-field comparison against a supplied expected-output oracle.
