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
from src.parser import load_products, parse_command_file
from src.formatter import format_bill, format_return_note, format_z_report
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
        help="Directory to store generated Bills, Return Notes, and Z-Reports (default: output)",
    )
    args = parser.parse_args()

    products_path = Path(args.products)
    commands_path = Path(args.commands)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

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

    print(f"Parsing Command File: {commands_path}...")
    try:
        events = parse_command_file(commands_path)
        print(f"Successfully parsed {len(events)} command events.")
    except Exception as e:
        print(f"Error parsing commands: {e}", file=sys.stderr)
        sys.exit(1)

    engine = POSEngine(catalog=catalog)
    # Pre-register some sample loyalty accounts if needed
    engine.register_loyalty_account(member_id="MEM001", name="Aditi Anshu", points_balance=500)
    engine.register_loyalty_account(member_id="MEM002", name="Aditi Chaudhary", points_balance=200)

    print("\nExecuting POS Transaction Pipeline...")
    bills_count = 0
    returns_count = 0
    zreports_count = 0

    for event in events:
        try:
            result = engine.execute_event(event)

            if isinstance(result, Bill) and result.is_finalized:
                bills_count += 1
                formatted = format_bill(result)
                out_file = output_dir / f"{result.bill_id}.txt"
                out_file.write_text(formatted, encoding="utf-8")
                print(f"  [CHECKOUT] Finalized Bill {result.bill_id} -> Rs {result.grand_total:.2f} (Saved to {out_file})")

            elif isinstance(result, ReturnNote):
                returns_count += 1
                formatted = format_return_note(result)
                out_file = output_dir / f"{result.return_id}.txt"
                out_file.write_text(formatted, encoding="utf-8")
                print(f"  [RETURN] Processed Return {result.return_id} -> Refund Rs {result.total_refund:.2f} (Saved to {out_file})")

            elif isinstance(result, TillZReport):
                zreports_count += 1
                formatted = format_z_report(result)
                out_file = output_dir / f"Z_REPORT_{result.report_date.strftime('%Y-%m-%d')}.txt"
                out_file.write_text(formatted, encoding="utf-8")
                print(f"  [Z-REPORT] Generated Z-Report for {result.report_date} -> Net Revenue Rs {result.net_revenue:.2f} (Saved to {out_file})")

        except Exception as e:
            print(f"  [ERROR] Event '{event.event_type}': {e}", file=sys.stderr)

    print("\n" + "=" * 70)
    print("  EXECUTION COMPLETE SUMMARY")
    print("=" * 70)
    print(f"  Total Bills Processed   : {bills_count}")
    print(f"  Total Returns Processed : {returns_count}")
    print(f"  Total Z-Reports Emitted : {zreports_count}")
    print(f"  All outputs saved to    : {output_dir.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
