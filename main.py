"""
Main CLI entry point for Supermarket POS Billing Engine.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)

Usage:
  python main.py --products data/products.csv --commands data/commands.txt --output output/
"""

import argparse
import sys
from pathlib import Path

from src.engine import POSEngine
from src.parser import (
    load_products,
    load_coupons_csv,
    load_members_csv,
    load_store_parameters_csv,
    parse_command_file,
)
from src.formatter import (
    format_bill,
    format_return_note,
    format_z_report,
    export_bill_lines_csv,
    export_bills_csv,
    export_offer_lines_csv,
    export_return_notes_csv,
    export_z_report_csv,
)
from src.models import Bill, ReturnNote, TillZReport


def main():
    parser = argparse.ArgumentParser(
        description="Command-file-driven Supermarket POS Billing Engine (Capstone PS-047, Team IDT002)"
    )
    parser.add_argument(
        "--products",
        "-p",
        required=True,
        help="Path to product master CSV or JSON file",
    )
    parser.add_argument(
        "--commands",
        "-c",
        required=True,
        help="Path to scan commands text file",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="output",
        help="Directory to store generated Bills, CSVs, Return Notes, and Z-Reports (default: output)",
    )
    parser.add_argument(
        "--coupons",
        default=None,
        help="Optional path to coupons.csv (defaults to same folder as products)",
    )
    parser.add_argument(
        "--members",
        default=None,
        help="Optional path to members.csv (defaults to same folder as products)",
    )
    parser.add_argument(
        "--parameters",
        default=None,
        help="Optional path to store_parameters.csv (defaults to same folder as products)",
    )

    args = parser.parse_args()

    products_path = Path(args.products)
    commands_path = Path(args.commands)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_dir = products_path.parent

    # Locate aux files
    coupons_path = Path(args.coupons) if args.coupons else (data_dir / "coupons.csv")
    members_path = Path(args.members) if args.members else (data_dir / "members.csv")
    params_path = Path(args.parameters) if args.parameters else (data_dir / "store_parameters.csv")

    print("=" * 70)
    print("  SUPERMARKET POS BILLING ENGINE - CAPSTONE PS-047")
    print("  Team IDT002: Aditi Anshu & Aditi Chaudhary")
    print("=" * 70)
    print(f"Loading Product Master: {products_path}...")
    try:
        catalog = load_products(products_path)
        print(f"Successfully loaded {len(catalog)} products.")
    except Exception as e:
        print(f"Error loading products: {e}", file=sys.stderr)
        sys.exit(1)

    coupons = {}
    if coupons_path.is_file():
        coupons = load_coupons_csv(coupons_path)
        print(f"Loaded {len(coupons)} coupons from {coupons_path}.")

    members = {}
    if members_path.is_file():
        members = load_members_csv(members_path)
        print(f"Loaded {len(members)} loyalty members from {members_path}.")

    params = {}
    if params_path.is_file():
        params = load_store_parameters_csv(params_path)
        print(f"Loaded {len(params)} store parameters from {params_path}.")

    print(f"Parsing Command File: {commands_path}...")
    try:
        events = parse_command_file(commands_path)
        print(f"Successfully parsed {len(events)} command events.")
    except Exception as e:
        print(f"Error parsing commands: {e}", file=sys.stderr)
        sys.exit(1)

    engine = POSEngine(
        catalog=catalog,
        coupons=coupons,
        members=members,
        store_parameters=params,
    )

    print("\nExecuting POS Transaction Pipeline...")
    bills_count = 0
    returns_count = 0
    zreports_count = 0

    for idx, event in enumerate(events, 1):
        try:
            result = engine.execute_event(event)

            if isinstance(result, Bill) and result.is_finalized:
                bills_count += 1
                formatted = format_bill(result)
                out_file = output_dir / f"{result.bill_id}.txt"
                out_file.write_text(formatted, encoding="utf-8")

            elif isinstance(result, ReturnNote):
                returns_count += 1
                formatted = format_return_note(result)
                out_file = output_dir / f"{result.return_id}.txt"
                out_file.write_text(formatted, encoding="utf-8")

            elif isinstance(result, TillZReport):
                zreports_count += 1
                formatted = format_z_report(result)
                out_file = output_dir / f"Z_REPORT_{result.till_id}_{result.business_date.strftime('%Y-%m-%d')}.txt"
                out_file.write_text(formatted, encoding="utf-8")

        except Exception as e:
            print(f"  [ERROR] Line {idx} Event '{event.event_type}': {e}", file=sys.stderr)

    # -------------------------------------------------------------
    # EXPORT OFFICIAL EVALUATION CSV ARTIFACTS
    # -------------------------------------------------------------
    print("\nExporting Evaluation CSV Datasets...")
    all_bills = list(engine.bills.values())
    all_returns = engine.returns
    all_zreports = engine.z_reports

    bill_lines_csv = export_bill_lines_csv(all_bills)
    (output_dir / "bill_lines.csv").write_text(bill_lines_csv, encoding="utf-8")
    print(f"  * Generated {output_dir / 'bill_lines.csv'} ({len(bill_lines_csv.splitlines()) - 1} bill lines)")

    bills_csv = export_bills_csv(all_bills)
    (output_dir / "bills.csv").write_text(bills_csv, encoding="utf-8")
    print(f"  * Generated {output_dir / 'bills.csv'} ({len(bills_csv.splitlines()) - 1} bills)")

    offer_lines_csv = export_offer_lines_csv(all_bills)
    (output_dir / "offer_lines.csv").write_text(offer_lines_csv, encoding="utf-8")
    print(f"  * Generated {output_dir / 'offer_lines.csv'} ({len(offer_lines_csv.splitlines()) - 1} offer lines)")

    return_notes_csv = export_return_notes_csv(all_returns)
    (output_dir / "return_notes.csv").write_text(return_notes_csv, encoding="utf-8")
    print(f"  * Generated {output_dir / 'return_notes.csv'} ({len(return_notes_csv.splitlines()) - 1} return records)")

    z_report_csv = export_z_report_csv(all_zreports)
    (output_dir / "z_report.csv").write_text(z_report_csv, encoding="utf-8")
    print(f"  * Generated {output_dir / 'z_report.csv'} ({len(z_report_csv.splitlines()) - 1} Z-reports)")

    print("\n" + "=" * 70)
    print("  EXECUTION COMPLETE SUMMARY")
    print("=" * 70)
    print(f"  Total Bills Finalized   : {bills_count}")
    print(f"  Total Returns Processed : {returns_count}")
    print(f"  Total Z-Reports Emitted : {zreports_count}")
    print(f"  All outputs saved to    : {output_dir.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
