"""
Plain-text Formatter for Bills, Return Notes, and Till Z-Reports.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)

Generates clean, deterministic, professional supermarket terminal outputs.
"""

from decimal import Decimal
from typing import Dict
from .models import Bill, ReturnNote, TillZReport


SEP_DOUBLE = "=" * 78
SEP_SINGLE = "-" * 78
SEP_DOT = "." * 78


def format_bill(bill: Bill) -> str:
    """
    Format a customer bill receipt into a deterministic plain-text document.
    """
    lines = []
    lines.append(SEP_DOUBLE)
    lines.append("              SUPERMARKET POS - RETAIL TAX INVOICE")
    lines.append("          Capstone Project PS-047 | Team IDT002")
    lines.append("              Aditi Anshu & Aditi Chaudhary")
    lines.append(SEP_DOUBLE)
    lines.append(f" Bill ID    : {bill.bill_id:<30} Date/Time: {bill.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    member_str = bill.member_id if bill.member_id else "Guest (Non-Member)"
    lines.append(f" Member ID  : {member_str}")
    lines.append(SEP_SINGLE)
    lines.append(f"{'#':<3} {'Item Description':<25} {'Qty/Wt':<10} {'Rate':>8} {'Gross':>9} {'Disc':>8} {'Taxable':>9}")
    lines.append(SEP_SINGLE)

    for line in bill.lines:
        name = line.product.name[:24]
        if line.product.unit == "KG":
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

    # Offer lines breakdown
    if bill.offer_lines:
        lines.append(SEP_DOT)
        lines.append(" APPLIED PROMOTIONS & DISCOUNTS:")
        for off in bill.offer_lines:
            lines.append(f"   * {off.description:<50} : -Rs {off.discount_amount:>7.2f}")
        lines.append(f" Total Savings & Discounts                          : -Rs {bill.total_discount:>9.2f}")

    lines.append(SEP_SINGLE)
    lines.append(f" Net Taxable Value                                 : Rs {bill.subtotal_taxable:>10.2f}")

    # GST Breakdown by Rate Slab
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

    # Loyalty Summary
    lines.append(" LOYALTY SUMMARY:")
    if bill.member_id:
        if bill.points_redeemed > 0:
            lines.append(f"   Points Redeemed : {bill.points_redeemed} pts (Saved Rs {bill.loyalty_burn_amount:.2f})")
        lines.append(f"   Points Earned   : {bill.loyalty_points_earned} pts (Status: PENDING - Available after 7 days)")
    else:
        lines.append("   (No loyalty account linked to this transaction)")

    lines.append(SEP_SINGLE)
    lines.append(" RETURN POLICY:")
    lines.append(" * Valid for 7 days up to 23:59:59 on Day +7 against this original bill.")
    lines.append(" * Weighed items (KG) are strictly non-returnable (BR-12).")
    lines.append(" * Multi-buy deals subject to clawback reversal upon partial return (BR-13).")
    lines.append(SEP_DOUBLE)
    lines.append("                   THANK YOU FOR SHOPPING WITH US!")
    lines.append(SEP_DOUBLE)
    lines.append("")
    return "\n".join(lines)


def format_return_note(return_note: ReturnNote) -> str:
    """
    Format a product return and refund voucher.
    """
    lines = []
    lines.append(SEP_DOUBLE)
    lines.append("           SUPERMARKET POS - RETURN & REFUND VOUCHER")
    lines.append("          Capstone Project PS-047 | Team IDT002")
    lines.append(SEP_DOUBLE)
    lines.append(f" Return ID     : {return_note.return_id:<25} Date/Time: {return_note.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f" Orig Bill ID  : {return_note.original_bill_id}")
    lines.append(SEP_SINGLE)
    lines.append(f"{'Barcode':<12} {'Product Name':<25} {'Qty':<6} {'Unit Paid':>10} {'Clawback':>10} {'Refund':>10}")
    lines.append(SEP_SINGLE)

    for r in return_note.lines:
        lines.append(
            f"{r.barcode:<12} {r.product_name[:24]:<25} {int(r.qty):<6} "
            f"{r.effective_unit_refund:>10.2f} {r.multibuy_reversal_deduction:>10.2f} "
            f"{r.net_refund:>10.2f}"
        )

    lines.append(SEP_SINGLE)
    lines.append(f" TOTAL REFUND AMOUNT PAYABLE                       : Rs {return_note.total_refund:>10.2f}")
    lines.append(SEP_DOUBLE)
    lines.append(f" Notes: {return_note.reason_or_notes}")
    lines.append(" Refund disbursed to customer drawer/account.")
    lines.append(SEP_DOUBLE)
    lines.append("")
    return "\n".join(lines)


def format_z_report(z_report: TillZReport) -> str:
    """
    Format an End-of-Day Till Z-Report.
    """
    lines = []
    lines.append(SEP_DOUBLE)
    lines.append("                 SUPERMARKET POS - TILL Z-REPORT")
    lines.append("          Capstone Project PS-047 | Team IDT002")
    lines.append(SEP_DOUBLE)
    lines.append(f" Report Date    : {z_report.report_date.strftime('%Y-%m-%d')}")
    lines.append(f" Generated At   : {z_report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(SEP_SINGLE)
    lines.append(f" Total Bills Finalized                             : {z_report.total_bills:>14}")
    lines.append(f" Total Return Notes Processed                      : {z_report.total_returns:>14}")
    lines.append(SEP_SINGLE)
    lines.append(f" Gross Sales Subtotal                              : Rs {z_report.gross_sales:>11.2f}")
    lines.append(f" Total Discounts Granted                           : -Rs {z_report.total_discounts:>10.2f}")
    lines.append(f" Net Taxable Sales                                 : Rs {z_report.net_taxable_sales:>11.2f}")
    lines.append(SEP_DOT)
    lines.append(" GST CONSOLIDATED RECONCILIATION:")
    lines.append(f"   {'Slab':<8} {'Taxable Val':>14} {'CGST':>12} {'SGST':>12} {'Total Tax':>14}")
    lines.append(f"   {'-'*8} {'-'*14} {'-'*12} {'-'*12} {'-'*14}")

    for slab_rate in sorted(z_report.gst_by_slab.keys()):
        slab = z_report.gst_by_slab[slab_rate]
        slab_name = f"{slab_rate:.0f}%"
        lines.append(
            f"   {slab_name:<8} {slab['taxable']:>14.2f} "
            f"{slab['cgst']:>12.2f} {slab['sgst']:>12.2f} "
            f"{slab['total_gst']:>14.2f}"
        )

    lines.append(f" Total GST Collected                               : Rs {z_report.total_gst:>11.2f}")
    lines.append(f" Post-GST Sales Value                              : Rs {z_report.post_gst_sales:>11.2f}")
    lines.append(f" Total Customer Refunds (Returns)                  : -Rs {z_report.total_refunds:>10.2f}")
    lines.append(SEP_DOUBLE)
    lines.append(f" NET TILL REVENUE (Cash Drawer Total)              : Rs {z_report.net_revenue:>11.2f}")
    lines.append(SEP_DOUBLE)
    lines.append(" LOYALTY RECONCILIATION:")
    lines.append(f"   Total Loyalty Points Earned (Pending)           : {z_report.points_earned:>14} pts")
    lines.append(f"   Total Loyalty Points Burned                     : {z_report.points_redeemed:>14} pts")
    lines.append(f"   Total Loyalty Value Redeemed                    : Rs {z_report.points_burned_value:>11.2f}")
    lines.append(SEP_DOUBLE)
    lines.append("              *** END OF Z-REPORT TRANSMISSION ***")
    lines.append(SEP_DOUBLE)
    lines.append("")
    return "\n".join(lines)
