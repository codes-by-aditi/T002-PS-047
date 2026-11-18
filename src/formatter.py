"""
Deterministic Plain-text and CSV Formatter for Bills, Return Notes, and Till Z-Reports.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)

Generates clean, deterministic, professional supermarket terminal outputs and
statutory evaluation CSV files:
  - bill_lines.csv
  - bills.csv
  - offer_lines.csv
  - return_notes.csv
  - z_report.csv
"""

import csv
import io
from decimal import Decimal
from typing import Dict, List, Optional
from pathlib import Path

from .models import Bill, BillLine, OfferLine, ReturnNote, TillZReport


SEP_DOUBLE = "=" * 78
SEP_SINGLE = "-" * 78
SEP_DOT = "." * 78


def format_bill(bill: Bill) -> str:
    """Format a customer bill receipt into a deterministic plain-text document."""
    lines = []
    lines.append(SEP_DOUBLE)
    lines.append("              SUPERMARKET POS - RETAIL TAX INVOICE")
    lines.append("          Capstone Project PS-047 | Team IDT002")
    lines.append("              Aditi Anshu & Aditi Chaudhary")
    lines.append(SEP_DOUBLE)
    lines.append(f" Bill ID    : {bill.bill_id:<25} Till ID  : {bill.till_id}")
    date_str = bill.close_ts.strftime('%Y-%m-%d %H:%M:%S') if bill.close_ts else bill.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    lines.append(f" Date/Time  : {date_str:<25} Payment  : {bill.payment_mode}")
    member_str = bill.member_id if bill.member_id else "Guest (Non-Member)"
    lines.append(f" Member ID  : {member_str}")
    lines.append(SEP_SINGLE)
    lines.append(f"{'#':<3} {'Item Description':<25} {'Qty/Wt':<10} {'Rate':>8} {'Gross':>9} {'Disc':>8} {'Taxable':>9}")
    lines.append(SEP_SINGLE)

    for line in bill.lines:
        name = line.product.name[:24]
        if line.product.is_weighed:
            qty_str = f"{line.net_weight:.3f} KG"
        else:
            qty_str = f"{int(line.qty)} PC"

        lines.append(
            f"{line.line_no:<3} {name:<25} {qty_str:<10} "
            f"{line.unit_price:>8.2f} {line.gross_total:>9.2f} "
            f"{line.total_discount:>8.2f} {line.taxable_value:>9.2f}"
        )

    lines.append(SEP_SINGLE)
    lines.append(f" Subtotal (Gross Sales)                            : Rs {bill.gross_total:>10.2f}")

    if bill.offer_lines:
        lines.append(SEP_DOT)
        lines.append(" APPLIED PROMOTIONS & DISCOUNTS:")
        for off in bill.offer_lines:
            lines.append(f"   * {off.description:<50} : -Rs {off.discount_amount:>7.2f}")
        lines.append(f" Total Savings & Discounts                          : -Rs {bill.total_discount:>9.2f}")

    lines.append(SEP_SINGLE)
    lines.append(f" Net Taxable Value                                 : Rs {bill.subtotal_taxable:>10.2f}")

    lines.append(SEP_DOT)
    lines.append(" GST BREAKDOWN BY RATE SLAB (Rounded per Slab):")
    lines.append(f"   {'Slab':<8} {'Taxable Val':>14} {'CGST':>12} {'SGST':>12} {'Total Tax':>14}")
    lines.append(f"   {'-'*8} {'-'*14} {'-'*12} {'-'*12} {'-'*14}")

    for slab_rate in sorted(bill.gst_by_slab.keys()):
        slab_data = bill.gst_by_slab[slab_rate]
        slab_name = f"{slab_rate:.0f}%"
        lines.append(
            f"   {slab_name:<8} {slab_data['taxable']:>14.2f} "
            f"{slab_data['cgst']:>12.2f} {slab_data['sgst']:>12.2f} "
            f"{slab_data['total_gst']:>14.2f}"
        )

    lines.append(f" Total GST Collected                               : Rs {bill.total_gst:>10.2f}")
    lines.append(SEP_DOUBLE)
    lines.append(f" GRAND TOTAL (NET PAYABLE)                         : Rs {bill.grand_total:>10.2f}")
    lines.append(SEP_DOUBLE)

    lines.append(" LOYALTY SUMMARY:")
    if bill.member_id:
        if bill.points_redeemed > 0:
            lines.append(f"   Points Redeemed : {bill.points_redeemed} pts (Saved Rs {bill.loyalty_burn_amount:.2f})")
        lines.append(f"   Points Earned   : {bill.loyalty_points_earned} pts (Status: PENDING - Available after 7 days)")
    else:
        lines.append("   (No loyalty account linked to this transaction)")

    lines.append(SEP_SINGLE)
    lines.append(" RETURN POLICY:")
    lines.append(" * Valid for 7 days up to store closing against this original bill.")
    lines.append(" * Weighed items (KG) are strictly non-returnable (BR-12).")
    lines.append(" * Multi-buy deals subject to clawback reversal upon partial return (BR-13).")
    lines.append(SEP_DOUBLE)
    lines.append("                   THANK YOU FOR SHOPPING WITH US!")
    lines.append(SEP_DOUBLE)
    lines.append("")
    return "\n".join(lines)


def format_return_note(return_note: ReturnNote) -> str:
    """Format a product return and refund voucher."""
    lines = []
    lines.append(SEP_DOUBLE)
    lines.append("           SUPERMARKET POS - RETURN & REFUND VOUCHER")
    lines.append("          Capstone Project PS-047 | Team IDT002")
    lines.append(SEP_DOUBLE)
    lines.append(f" Return ID     : {return_note.return_id:<25} Till ID  : {return_note.till_id}")
    lines.append(f" Date/Time     : {return_note.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f" Orig Bill ID  : {return_note.original_bill_id:<25} Status   : {return_note.status}")
    lines.append(SEP_SINGLE)

    if return_note.lines:
        lines.append(f"{'Barcode':<14} {'Product Name':<25} {'Qty':<6} {'Unit Paid':>10} {'Clawback':>10} {'Refund':>10}")
        lines.append(SEP_SINGLE)
        for r in return_note.lines:
            lines.append(
                f"{r.barcode:<14} {r.product_name[:24]:<25} {int(r.qty):<6} "
                f"{r.effective_unit_refund:>10.2f} {r.multibuy_reversal_deduction:>10.2f} "
                f"{r.net_refund:>10.2f}"
            )
        lines.append(SEP_SINGLE)

    lines.append(f" TOTAL REFUND AMOUNT DISBURSED                     : Rs {return_note.refund_amount:>10.2f}")
    if return_note.multibuy_clawback > Decimal('0.00'):
        lines.append(f" MULTI-BUY PROMOTIONAL CLAWBACK DEDUCTED           : Rs {return_note.multibuy_clawback:>10.2f}")
    lines.append(SEP_DOUBLE)
    lines.append(f" Reason / Audit: {return_note.reason}")
    lines.append(SEP_DOUBLE)
    lines.append("")
    return "\n".join(lines)


def format_z_report(z_report: TillZReport) -> str:
    """Format an End-of-Day Till Z-Report."""
    lines = []
    lines.append(SEP_DOUBLE)
    lines.append("                 SUPERMARKET POS - TILL Z-REPORT")
    lines.append("          Capstone Project PS-047 | Team IDT002")
    lines.append(SEP_DOUBLE)
    lines.append(f" Till ID        : {z_report.till_id:<25} Date: {z_report.business_date.strftime('%Y-%m-%d')}")
    lines.append(f" Generated At   : {z_report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(SEP_SINGLE)
    lines.append(f" Total Bills Finalized                             : {z_report.bills_count:>14}")
    lines.append(f" Total Return Notes Processed                      : {z_report.returns_count:>14}")
    lines.append(SEP_SINGLE)
    lines.append(f" Gross Sales Subtotal                              : Rs {z_report.gross_sales:>11.2f}")
    lines.append(f" Total Discounts Granted                           : -Rs {z_report.total_discounts:>10.2f}")
    lines.append(f" Total GST Collected                               : Rs {z_report.gst_total:>11.2f}")
    lines.append(f" Net Till Sales (Post-GST)                         : Rs {z_report.net_sales:>11.2f}")
    lines.append(SEP_DOT)
    lines.append(" PAYMENT MODE BREAKDOWN:")
    lines.append(f"   CASH                                            : Rs {z_report.cash:>11.2f}")
    lines.append(f"   UPI                                             : Rs {z_report.upi:>11.2f}")
    lines.append(f"   CARD                                            : Rs {z_report.card:>11.2f}")
    lines.append(SEP_DOT)
    lines.append(f" Total Customer Refunds Disbursed                  : -Rs {z_report.refunds_total:>10.2f}")
    lines.append(SEP_DOUBLE)
    net_rev = z_report.net_sales - z_report.refunds_total
    lines.append(f" NET DRAWER REVENUE (Cash Drawer Total)            : Rs {net_rev:>11.2f}")
    lines.append(SEP_DOUBLE)
    lines.append("              *** END OF Z-REPORT TRANSMISSION ***")
    lines.append(SEP_DOUBLE)
    lines.append("")
    return "\n".join(lines)


# =========================================================================
# EVALUATION CSV EXPORT FUNCTIONS
# =========================================================================

def export_bill_lines_csv(bills: List[Bill]) -> str:
    """
    Produce bill_lines.csv:
    Columns: bill_id, line_no, sku, qty, net_kg, unit_price, gross_amount,
             multibuy_discount, category_discount, member_discount, coupon_share,
             threshold_share, points_share, taxable_value, gst_rate, gst_amount, line_total
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "bill_id", "line_no", "sku", "qty", "net_kg", "unit_price", "gross_amount",
        "multibuy_discount", "category_discount", "member_discount", "coupon_share",
        "threshold_share", "points_share", "taxable_value", "gst_rate", "gst_amount", "line_total"
    ])

    # Sort bills by bill_id
    sorted_bills = sorted(bills, key=lambda b: b.bill_id)
    for bill in sorted_bills:
        for line in bill.lines:
            sku = line.product.sku or f"SKU-{line.product.barcode}"
            if line.product.is_weighed:
                qty_str = ""
                net_kg_str = f"{line.net_weight:.3f}"
            else:
                qty_str = f"{int(line.qty)}"
                net_kg_str = ""

            gst_rate_int = int(line.gst_rate)

            writer.writerow([
                bill.bill_id,
                line.line_no,
                sku,
                qty_str,
                net_kg_str,
                f"{line.unit_price:.2f}",
                f"{line.gross_total:.2f}",
                f"{line.multibuy_discount:.2f}",
                f"{line.category_discount:.2f}",
                f"{line.member_discount:.2f}",
                f"{line.coupon_discount:.2f}",
                f"{line.threshold_discount:.2f}",
                f"{line.loyalty_burn_discount:.2f}",
                f"{line.taxable_value:.2f}",
                gst_rate_int,
                f"{line.gst_amount:.2f}",
                f"{line.final_total:.2f}",
            ])

    return output.getvalue()


def export_bills_csv(bills: List[Bill]) -> str:
    """
    Produce bills.csv:
    Columns: bill_id, till_id, member_id, close_ts, gross_total, item_offer_total,
             subtotal, coupon_code, coupon_discount, threshold_discount, points_redeemed,
             points_value, taxable_total, gst_0, gst_5, gst_12, gst_18, gst_total,
             bill_total, points_earned
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "bill_id", "till_id", "member_id", "close_ts", "gross_total", "item_offer_total",
        "subtotal", "coupon_code", "coupon_discount", "threshold_discount", "points_redeemed",
        "points_value", "taxable_total", "gst_0", "gst_5", "gst_12", "gst_18", "gst_total",
        "bill_total", "points_earned"
    ])

    for bill in bills:
        close_ts_str = bill.close_ts.strftime("%Y-%m-%d %H:%M:%S") if bill.close_ts else bill.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        member_str = bill.member_id or ""
        coupon_str = bill.coupon.code if (bill.coupon and bill.coupon_discount > Decimal('0.00')) else ""

        gst_0 = bill.gst_by_slab.get(Decimal('0'), {}).get('total_gst', Decimal('0.00'))
        gst_5 = bill.gst_by_slab.get(Decimal('5.0'), {}).get('total_gst', Decimal('0.00'))
        if Decimal('5') in bill.gst_by_slab and Decimal('5.0') not in bill.gst_by_slab:
            gst_5 = bill.gst_by_slab[Decimal('5')]['total_gst']

        gst_12 = bill.gst_by_slab.get(Decimal('12.0'), {}).get('total_gst', Decimal('0.00'))
        if Decimal('12') in bill.gst_by_slab and Decimal('12.0') not in bill.gst_by_slab:
            gst_12 = bill.gst_by_slab[Decimal('12')]['total_gst']

        gst_18 = bill.gst_by_slab.get(Decimal('18.0'), {}).get('total_gst', Decimal('0.00'))
        if Decimal('18') in bill.gst_by_slab and Decimal('18.0') not in bill.gst_by_slab:
            gst_18 = bill.gst_by_slab[Decimal('18')]['total_gst']

        writer.writerow([
            bill.bill_id,
            bill.till_id,
            member_str,
            close_ts_str,
            f"{bill.gross_total:.2f}",
            f"{bill.item_offer_total:.2f}",
            f"{bill.subtotal:.2f}",
            coupon_str,
            f"{bill.coupon_discount:.2f}",
            f"{bill.threshold_discount:.2f}",
            bill.points_redeemed,
            f"{bill.loyalty_burn_amount:.2f}",
            f"{bill.subtotal_taxable:.2f}",
            f"{gst_0:.2f}",
            f"{gst_5:.2f}",
            f"{gst_12:.2f}",
            f"{gst_18:.2f}",
            f"{bill.total_gst:.2f}",
            f"{bill.grand_total:.2f}",
            bill.loyalty_points_earned,
        ])

    return output.getvalue()


def export_offer_lines_csv(bills: List[Bill]) -> str:
    """
    Produce offer_lines.csv:
    Columns: bill_id, offer_type, offer_ref, line_no, discount_amount
    In bill and precedence order.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["bill_id", "offer_type", "offer_ref", "line_no", "discount_amount"])

    precedence_rank = {
        "MULTIBUY": 1,
        "CATEGORY": 2,
        "MEMBER": 3,
        "COUPON": 4,
        "THRESHOLD": 5,
        "POINTS": 6,
    }

    for bill in bills:
        # Sort offer lines by precedence rank, then by line_no
        sorted_offers = sorted(
            bill.offer_lines,
            key=lambda o: (precedence_rank.get(o.offer_type, 99), o.line_no or 0)
        )
        for off in sorted_offers:
            line_str = str(off.line_no) if off.line_no is not None else ""
            writer.writerow([
                bill.bill_id,
                off.offer_type,
                off.offer_ref,
                line_str,
                f"{off.discount_amount:.2f}",
            ])

    return output.getvalue()


def export_return_notes_csv(returns: List[ReturnNote]) -> str:
    """
    Produce return_notes.csv:
    Columns: return_id, original_bill_id, sku, qty, status, refund_amount, multibuy_clawback, reason
    One row per RETURN command in file order.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "return_id", "original_bill_id", "sku", "qty", "status",
        "refund_amount", "multibuy_clawback", "reason"
    ])

    for r in returns:
        writer.writerow([
            r.return_id,
            r.original_bill_id,
            r.sku,
            int(r.qty),
            r.status,
            f"{r.refund_amount:.2f}",
            f"{r.multibuy_clawback:.2f}",
            r.reason,
        ])

    return output.getvalue()


def export_z_report_csv(z_reports: List[TillZReport]) -> str:
    """
    Produce z_report.csv:
    Columns: till_id, business_date, bills_count, gross_sales, total_discounts,
             gst_total, net_sales, returns_count, refunds_total, cash, upi, card
    One row per Z_REPORT command.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "till_id", "business_date", "bills_count", "gross_sales", "total_discounts",
        "gst_total", "net_sales", "returns_count", "refunds_total", "cash", "upi", "card"
    ])

    for z in z_reports:
        writer.writerow([
            z.till_id,
            z.business_date.strftime("%Y-%m-%d"),
            z.bills_count,
            f"{z.gross_sales:.2f}",
            f"{z.total_discounts:.2f}",
            f"{z.gst_total:.2f}",
            f"{z.net_sales:.2f}",
            z.returns_count,
            f"{z.refunds_total:.2f}",
            f"{z.cash:.2f}",
            f"{z.upi:.2f}",
            f"{z.card:.2f}",
        ])

    return output.getvalue()
