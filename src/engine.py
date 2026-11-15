"""
Core Supermarket POS Billing Engine.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)

Strictly implements Business Rules BR-01 to BR-13 and Edge Cases 1 to 8:
  BR-01: Weighed Items (tare subtraction, min net weight 0.005kg)
  BR-02: MRP Ceiling (effective price never exceeds MRP)
  BR-03: Multi-Buy 'Buy 2 Get 1' (cheapest unit free, max 3 free per offer)
  BR-04: Category Discount (10% off FRESH at or after 20:00)
  BR-05: Strict Offer Precedence (Multi-buy -> Category -> Member -> Coupon -> Threshold)
  BR-06: Member Pricing (replaces SP for unconsumed units, capped at MRP)
  BR-07: Coupon (Max 1, PCT max Rs 200, FIXED valid if subtotal >= 3*value, pro-rata)
  BR-08: Bill Threshold (>=5000 -> 300, >=2000 -> 100, pro-rata with largest-item adjustment)
  BR-09: GST Computation (Group by rate slab 0%, 5%, 12%, 18% & round per slab)
  BR-10: Loyalty Earn (1 pt / Rs 100 post-GST excluding TOBACCO & LIQUOR; pending 7 days)
  BR-11: Loyalty Burn (1 pt = Rs 0.25, 100-pt multiples, max 20% cap; before GST)
  BR-12: Returns (7-day window, weighed items non-returnable, refund at effective price)
  BR-13: Multi-Buy Return Reversal (deduct free item value if group broken)
"""

from collections import defaultdict
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any

from .models import (
    Product,
    ScanEvent,
    BillLine,
    OfferLine,
    Coupon,
    Bill,
    ReturnLine,
    ReturnNote,
    LoyaltyAccount,
    TillZReport,
    quantize_currency,
    quantize_weight,
)


class POSEngine:
    """
    Main billing engine coordinating scans, offers, taxes, loyalty, returns, and reports.
    """

    def __init__(self, catalog: Optional[Dict[str, Product]] = None):
        self.catalog: Dict[str, Product] = catalog or {}
        self.loyalty_accounts: Dict[str, LoyaltyAccount] = {}
        self.bills: Dict[str, Bill] = {}
        self.returns: Dict[str, ReturnNote] = {}
        self.bill_returns_tracker: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

        # Current active billing session
        self.current_bill: Optional[Bill] = None
        self.active_coupon: Optional[Coupon] = None
        self.active_points_to_redeem: int = 0

    def register_product(self, product: Product) -> None:
        """Register or update a product in the catalog."""
        self.catalog[product.barcode] = product

    def register_loyalty_account(self, member_id: str, name: str = "", points_balance: int = 0) -> LoyaltyAccount:
        """Register or retrieve a customer loyalty account."""
        if member_id not in self.loyalty_accounts:
            self.loyalty_accounts[member_id] = LoyaltyAccount(
                member_id=member_id,
                name=name,
                points_balance=points_balance,
            )
        return self.loyalty_accounts[member_id]

    def start_bill(self, bill_id: str, timestamp: datetime, member_id: Optional[str] = None) -> Bill:
        """
        Start a new bill transaction.
        """
        if self.current_bill and not self.current_bill.is_finalized:
            raise ValueError(f"Previous bill {self.current_bill.bill_id} is still open. Must CHECKOUT first.")

        if member_id and member_id not in self.loyalty_accounts:
            self.register_loyalty_account(member_id)

        bill = Bill(
            bill_id=bill_id,
            timestamp=timestamp,
            member_id=member_id,
        )
        self.current_bill = bill
        self.active_coupon = None
        self.active_points_to_redeem = 0
        return bill

    def scan_item(self, barcode: str, qty: Decimal = Decimal('1'), timestamp: Optional[datetime] = None) -> BillLine:
        """
        Scan a barcoded packaged item (BR-02 MRP ceiling applied).
        """
        if not self.current_bill or self.current_bill.is_finalized:
            raise ValueError("No active bill. Call START_BILL first.")

        if barcode not in self.catalog:
            raise ValueError(f"Product barcode {barcode} not found in catalog.")

        product = self.catalog[barcode]
        scan_ts = timestamp or self.current_bill.timestamp

        # BR-02: Base unit price capped at MRP
        unit_price = product.effective_selling_price
        gross_total = quantize_currency(qty * unit_price)

        line_no = len(self.current_bill.lines) + 1
        line = BillLine(
            line_no=line_no,
            product=product,
            qty=qty,
            scan_timestamp=scan_ts,
            unit_price=unit_price,
            gross_total=gross_total,
            gst_rate=product.gst_rate,
        )
        self.current_bill.lines.append(line)
        return line

    def weigh_item(self, barcode: str, gross_weight: Decimal, timestamp: Optional[datetime] = None) -> BillLine:
        """
        Weigh a bulk item (BR-01, BR-02).
        Calculates net_weight = gross_weight - tare_weight.
        Rejects if net_weight < 0.005 kg.
        """
        if not self.current_bill or self.current_bill.is_finalized:
            raise ValueError("No active bill. Call START_BILL first.")

        if barcode not in self.catalog:
            raise ValueError(f"Product barcode {barcode} not found in catalog.")

        product = self.catalog[barcode]
        if product.unit != 'KG':
            raise ValueError(f"Product {barcode} ({product.name}) is not a weighed item (unit is {product.unit}).")

        tare_weight = product.tare_weight
        net_weight = quantize_weight(gross_weight - tare_weight)

        # BR-01: Reject if net_weight < 0.005 kg
        if net_weight < Decimal('0.005'):
            raise ValueError(f"Scan rejected for {product.name}: Net weight {net_weight} kg is below minimum 0.005 kg.")

        scan_ts = timestamp or self.current_bill.timestamp
        # BR-02: Unit price per kg capped at MRP
        unit_price = product.effective_selling_price
        # BR-01: Line total rounded to 2 decimal places (ROUND_HALF_UP)
        gross_total = quantize_currency(net_weight * unit_price)

        line_no = len(self.current_bill.lines) + 1
        line = BillLine(
            line_no=line_no,
            product=product,
            qty=Decimal('1'),  # 1 weigh event
            gross_weight=quantize_weight(gross_weight),
            tare_weight=tare_weight,
            net_weight=net_weight,
            scan_timestamp=scan_ts,
            unit_price=unit_price,
            gross_total=gross_total,
            gst_rate=product.gst_rate,
        )
        self.current_bill.lines.append(line)
        return line

    def override_qty(self, line_no_or_barcode: str, new_qty: Decimal) -> Optional[BillLine]:
        """
        Override the quantity of a line item by line number or latest matching barcode.
        """
        if not self.current_bill or self.current_bill.is_finalized:
            raise ValueError("No active bill.")

        target_line: Optional[BillLine] = None
        # Try line_no first if numeric
        if line_no_or_barcode.isdigit():
            target_no = int(line_no_or_barcode)
            for line in self.current_bill.lines:
                if line.line_no == target_no:
                    target_line = line
                    break

        # Fallback to barcode (most recent)
        if target_line is None:
            for line in reversed(self.current_bill.lines):
                if line.product.barcode == line_no_or_barcode:
                    target_line = line
                    break

        if target_line is None:
            raise ValueError(f"Line item '{line_no_or_barcode}' not found to override quantity.")

        if new_qty <= Decimal('0'):
            self.void_item(line_no_or_barcode)
            return None

        target_line.qty = new_qty
        if target_line.product.unit == 'KG':
            target_line.gross_total = quantize_currency(target_line.net_weight * target_line.unit_price)
        else:
            target_line.gross_total = quantize_currency(new_qty * target_line.unit_price)

        return target_line

    def void_item(self, line_no_or_barcode: str) -> None:
        """
        Void (remove) a line item from the active bill.
        """
        if not self.current_bill or self.current_bill.is_finalized:
            raise ValueError("No active bill.")

        idx_to_remove: Optional[int] = None
        if line_no_or_barcode.isdigit():
            target_no = int(line_no_or_barcode)
            for i, line in enumerate(self.current_bill.lines):
                if line.line_no == target_no:
                    idx_to_remove = i
                    break

        if idx_to_remove is None:
            for i in range(len(self.current_bill.lines) - 1, -1, -1):
                if self.current_bill.lines[i].product.barcode == line_no_or_barcode:
                    idx_to_remove = i
                    break

        if idx_to_remove is None:
            raise ValueError(f"Line item '{line_no_or_barcode}' not found to void.")

        self.current_bill.lines.pop(idx_to_remove)
        # Re-number remaining lines
        for new_idx, line in enumerate(self.current_bill.lines, start=1):
            line.line_no = new_idx

    def apply_coupon(self, coupon_code: str, coupon_type: str, value: Decimal) -> None:
        """
        Set the coupon to be applied at checkout (BR-07: Max 1 coupon per bill).
        """
        if not self.current_bill or self.current_bill.is_finalized:
            raise ValueError("No active bill.")

        if self.active_coupon is not None:
            raise ValueError(f"Coupon already applied ({self.active_coupon.code}). Maximum 1 coupon per bill (BR-07).")

        self.active_coupon = Coupon(
            code=coupon_code,
            coupon_type=coupon_type.upper(),
            value=quantize_currency(value) if coupon_type.upper() == "FIXED" else value,
        )

    def redeem_points(self, points: int) -> None:
        """
        Request loyalty points redemption (BR-11: 100-pt multiples, max 20% cap).
        Validated and deducted at checkout.
        """
        if not self.current_bill or self.current_bill.is_finalized:
            raise ValueError("No active bill.")

        if points < 0:
            raise ValueError("Points to redeem must be non-negative.")

        self.active_points_to_redeem = points

    def checkout(self) -> Bill:
        """
        Finalize the current bill by executing the full discount and tax pipeline:
          BR-03 -> BR-04 -> BR-06 -> BR-07 -> BR-08 -> BR-11 -> BR-09 -> BR-10
        """
        if not self.current_bill or self.current_bill.is_finalized:
            raise ValueError("No active bill to checkout.")

        bill = self.current_bill
        bill.offer_lines.clear()

        # -------------------------------------------------------------
        # STEP 1: BR-03 Multi-Buy 'Buy 2 Get 1'
        # -------------------------------------------------------------
        self._apply_multibuy_offers(bill)

        # -------------------------------------------------------------
        # STEP 2: BR-04 Category Discount (10% FRESH >= 20:00)
        # -------------------------------------------------------------
        self._apply_category_discount(bill)

        # -------------------------------------------------------------
        # STEP 3: BR-06 Member Pricing (Strict Precedence BR-05)
        # -------------------------------------------------------------
        self._apply_member_pricing(bill)

        # Calculate post-item-offer subtotal
        subtotal_post_item = sum(line.post_item_offer_val for line in bill.lines)

        # -------------------------------------------------------------
        # STEP 4: BR-07 Coupon Discount
        # -------------------------------------------------------------
        self._apply_coupon_discount(bill, subtotal_post_item)

        # Calculate subtotal after coupon
        subtotal_post_coupon = sum(line.post_coupon_val for line in bill.lines)

        # -------------------------------------------------------------
        # STEP 5: BR-08 Bill-level Threshold Discount
        # -------------------------------------------------------------
        self._apply_threshold_discount(bill, subtotal_post_coupon)

        # Calculate subtotal after threshold
        subtotal_post_threshold = sum(line.post_threshold_val for line in bill.lines)

        # -------------------------------------------------------------
        # STEP 6: BR-11 Loyalty Burn
        # -------------------------------------------------------------
        self._apply_loyalty_burn(bill, subtotal_post_threshold)

        # -------------------------------------------------------------
        # STEP 7: BR-09 GST Computation (Per Rate Slab)
        # -------------------------------------------------------------
        self._compute_gst_and_totals(bill)

        # -------------------------------------------------------------
        # STEP 8: BR-10 Loyalty Earn (1 pt / Rs 100 post-GST, excl TOBACCO/LIQUOR)
        # -------------------------------------------------------------
        self._apply_loyalty_earn(bill)

        # Mark finalized and record in store history
        bill.is_finalized = True
        self.bills[bill.bill_id] = bill
        self.current_bill = None
        return bill

    def _apply_multibuy_offers(self, bill: Bill) -> None:
        """
        BR-03: Multi-Buy 'Buy 2 Get 1'.
        For every group of 3 eligible units in an offer group, the cheapest unit is free.
        Sort eligible units by effective unit price descending.
        Cap at maximum 3 free items per bill per offer group.
        """
        bill.multibuy_groups.clear()

        # Group eligible unit items by offer_group
        # Each item is a single discrete unit
        offer_units: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for line in bill.lines:
            if line.product.offer_group and line.product.unit == 'PC':
                qty_int = int(line.qty)
                for _ in range(qty_int):
                    offer_units[line.product.offer_group].append({
                        'line': line,
                        'barcode': line.product.barcode,
                        'name': line.product.name,
                        'unit_price': line.unit_price,
                    })

        for group_name, units in offer_units.items():
            # Sort descending by unit_price
            units.sort(key=lambda u: u['unit_price'], reverse=True)

            num_groups = min(len(units) // 3, 3)  # Max 3 free items per bill per offer
            for g_idx in range(num_groups):
                triple = units[g_idx * 3 : (g_idx + 1) * 3]
                # In descending order, triple[2] is the cheapest unit
                paid_units = triple[:2]
                free_unit = triple[2]

                # Update free line
                free_line: BillLine = free_unit['line']
                free_line.multibuy_discount += free_unit['unit_price']
                free_line.free_units_multibuy += 1

                # Update paid lines
                for pu in paid_units:
                    pu_line: BillLine = pu['line']
                    pu_line.paid_units_multibuy += 1

                # Record multi-buy group for return reversal tracking (BR-13)
                group_record = {
                    'offer_group': group_name,
                    'free_barcode': free_unit['barcode'],
                    'free_name': free_unit['name'],
                    'free_value': free_unit['unit_price'],
                    'free_line_no': free_line.line_no,
                    'paid_barcodes': [p['barcode'] for p in paid_units],
                    'free_returned': False,
                    'paid_returned_count': 0,
                    'reversal_applied': False,
                }
                bill.multibuy_groups.append(group_record)

                bill.offer_lines.append(OfferLine(
                    offer_type="MULTIBUY",
                    description=f"Buy 2 Get 1 Free ({group_name} - Free: {free_unit['name']})",
                    discount_amount=free_unit['unit_price'],
                ))

    def _apply_category_discount(self, bill: Bill) -> None:
        """
        BR-04: 10% off items in category FRESH weighed/scanned at or after 20:00 (evening clearance).
        Never apply to items already consumed by a multi-buy group.
        """
        for line in bill.lines:
            if line.product.category == "FRESH":
                scan_dt = line.scan_timestamp or bill.timestamp
                scan_time = scan_dt.time()

                # Evening clearance at or after 20:00
                if scan_time >= time(20, 0, 0):
                    if line.product.unit == 'KG':
                        # Weighed item (not part of multi-buy)
                        discount = quantize_currency(line.gross_total * Decimal('0.10'))
                        line.category_discount += discount
                        bill.offer_lines.append(OfferLine(
                            offer_type="CATEGORY",
                            description=f"Fresh Clearance 10% ({line.product.name})",
                            discount_amount=discount,
                        ))
                    else:
                        # Packaged item: apply only to unconsumed units
                        consumed_mb = line.free_units_multibuy + line.paid_units_multibuy
                        unconsumed_qty = int(line.qty) - consumed_mb
                        if unconsumed_qty > 0:
                            unconsumed_val = Decimal(unconsumed_qty) * line.unit_price
                            discount = quantize_currency(unconsumed_val * Decimal('0.10'))
                            line.category_discount += discount
                            line.consumed_units_category += unconsumed_qty
                            bill.offer_lines.append(OfferLine(
                                offer_type="CATEGORY",
                                description=f"Fresh Clearance 10% ({line.product.name})",
                                discount_amount=discount,
                            ))

    def _apply_member_pricing(self, bill: Bill) -> None:
        """
        BR-06 & BR-05: Loyalty members get member_price on tagged SKUs.
        Replaces selling_price for units not consumed by Multi-buy or Category discount.
        Subject to MRP ceiling (BR-02).
        """
        if not bill.member_id:
            return

        for line in bill.lines:
            if line.product.member_price > Decimal('0.00'):
                effective_mp = line.product.effective_member_price
                base_sp = line.unit_price  # already min(selling_price, mrp)

                if effective_mp < base_sp:
                    savings_per_unit = base_sp - effective_mp

                    if line.product.unit == 'KG':
                        # If category discount was already applied, it was consumed
                        if line.category_discount == Decimal('0.00'):
                            discount = quantize_currency(line.net_weight * savings_per_unit)
                            line.member_discount += discount
                            bill.offer_lines.append(OfferLine(
                                offer_type="MEMBER",
                                description=f"Member Savings ({line.product.name})",
                                discount_amount=discount,
                            ))
                    else:
                        consumed = (
                            line.free_units_multibuy +
                            line.paid_units_multibuy +
                            line.consumed_units_category
                        )
                        unconsumed_qty = max(0, int(line.qty) - consumed)
                        if unconsumed_qty > 0:
                            discount = quantize_currency(Decimal(unconsumed_qty) * savings_per_unit)
                            line.member_discount += discount
                            line.consumed_units_member += unconsumed_qty
                            bill.offer_lines.append(OfferLine(
                                offer_type="MEMBER",
                                description=f"Member Savings ({line.product.name})",
                                discount_amount=discount,
                            ))

    def _apply_coupon_discount(self, bill: Bill, subtotal_post_item: Decimal) -> None:
        """
        BR-07: Coupon discount.
        Maximum 1 coupon per bill.
        PCT: X% off post-item-offer subtotal, capped at Rs 200.00.
        FIXED: Rs Y off, valid ONLY if post-item-offer subtotal >= 3 * Y (reject otherwise).
        Apportion pro-rata across items by post-item-offer value.
        """
        coupon = self.active_coupon
        if not coupon:
            return

        bill.coupon = coupon
        coupon_discount = Decimal('0.00')

        if coupon.coupon_type == "PCT":
            raw_discount = quantize_currency(subtotal_post_item * (coupon.value / Decimal('100')))
            coupon_discount = min(raw_discount, Decimal('200.00'))
        elif coupon.coupon_type == "FIXED":
            min_subtotal_required = Decimal('3') * coupon.value
            if subtotal_post_item >= min_subtotal_required:
                coupon_discount = coupon.value
            else:
                # Reject coupon because subtotal is below 3 * value
                coupon_discount = Decimal('0.00')

        if coupon_discount > Decimal('0.00') and subtotal_post_item > Decimal('0.00'):
            # Apportion pro-rata across lines
            self._apportion_discount(
                lines=bill.lines,
                total_discount=coupon_discount,
                get_base_val=lambda l: l.post_item_offer_val,
                set_discount=lambda l, val: setattr(l, 'coupon_discount', val),
            )
            bill.offer_lines.append(OfferLine(
                offer_type="COUPON",
                description=f"Coupon ({coupon.code})",
                discount_amount=coupon_discount,
            ))

    def _apply_threshold_discount(self, bill: Bill, subtotal_post_coupon: Decimal) -> None:
        """
        BR-08: Bill Threshold Discount based on subtotal after coupon:
          >= Rs 5,000.00 -> Rs 300.00 off
          >= Rs 2,000.00 -> Rs 100.00 off
        Apportion pro-rata across items by value (adjusting largest item by 1 paisa if needed).
        """
        threshold_discount = Decimal('0.00')
        if subtotal_post_coupon >= Decimal('5000.00'):
            threshold_discount = Decimal('300.00')
        elif subtotal_post_coupon >= Decimal('2000.00'):
            threshold_discount = Decimal('100.00')

        if threshold_discount > Decimal('0.00') and subtotal_post_coupon > Decimal('0.00'):
            self._apportion_discount(
                lines=bill.lines,
                total_discount=threshold_discount,
                get_base_val=lambda l: l.post_coupon_val,
                set_discount=lambda l, val: setattr(l, 'threshold_discount', val),
            )
            bill.offer_lines.append(OfferLine(
                offer_type="THRESHOLD",
                description="Bill Threshold Savings",
                discount_amount=threshold_discount,
            ))

    def _apply_loyalty_burn(self, bill: Bill, subtotal_post_threshold: Decimal) -> None:
        """
        BR-11: Loyalty Burn.
        1 point = Rs 0.25.
        Redemption allowed ONLY in multiples of 100 points, capped at 20% of post-threshold bill subtotal.
        If requested points exceed 20% of bill, cap to valid 100-point multiple within 20%;
        if even 100 points exceeds 20%, 0 points redeemed (blocked).
        Burned points applied before GST computation (apportioned pro-rata).
        """
        bill.points_requested = self.active_points_to_redeem
        if self.active_points_to_redeem <= 0:
            return

        # 20% cap calculation
        max_discount_allowed = quantize_currency(subtotal_post_threshold * Decimal('0.20'))
        # 100 points = Rs 25.00
        max_100_pt_multiples = int(max_discount_allowed // Decimal('25.00'))
        max_burnable_points = max_100_pt_multiples * 100

        # Check customer account balance if member
        available_balance = 0
        if bill.member_id and bill.member_id in self.loyalty_accounts:
            available_balance = self.loyalty_accounts[bill.member_id].points_balance

        effective_points = min(self.active_points_to_redeem, max_burnable_points, available_balance)
        # Ensure strict multiple of 100
        effective_points = (effective_points // 100) * 100

        if effective_points > 0:
            burn_amount = quantize_currency(Decimal(effective_points) * Decimal('0.25'))
            bill.points_redeemed = effective_points
            bill.loyalty_burn_amount = burn_amount

            # Deduct from member account
            if bill.member_id and bill.member_id in self.loyalty_accounts:
                self.loyalty_accounts[bill.member_id].points_balance -= effective_points

            # Apportion pro-rata across lines
            if subtotal_post_threshold > Decimal('0.00'):
                self._apportion_discount(
                    lines=bill.lines,
                    total_discount=burn_amount,
                    get_base_val=lambda l: l.post_threshold_val,
                    set_discount=lambda l, val: setattr(l, 'loyalty_burn_discount', val),
                )

            bill.offer_lines.append(OfferLine(
                offer_type="LOYALTY_BURN",
                description=f"Loyalty Points Burned ({effective_points} pts)",
                discount_amount=burn_amount,
            ))
        else:
            bill.points_redeemed = 0
            bill.loyalty_burn_amount = Decimal('0.00')

    def _apportion_discount(self, lines: List[BillLine], total_discount: Decimal, get_base_val, set_discount) -> None:
        """
        Apportion a bill-level discount pro-rata across eligible lines.
        Adjusts the line with the largest base value to resolve rounding residual paise.
        """
        eligible_lines = [l for l in lines if get_base_val(l) > Decimal('0.00')]
        if not eligible_lines:
            return

        total_base = sum(get_base_val(l) for l in eligible_lines)
        if total_base <= Decimal('0.00'):
            return

        allocated_sum = Decimal('0.00')
        largest_line = eligible_lines[0]
        max_base = get_base_val(largest_line)

        # First pass: calculate proportional shares
        shares = {}
        for line in eligible_lines:
            base_val = get_base_val(line)
            if base_val > max_base:
                max_base = base_val
                largest_line = line

            share = quantize_currency((base_val / total_base) * total_discount)
            shares[line.line_no] = share
            allocated_sum += share

        # Residual adjustment
        diff = total_discount - allocated_sum
        shares[largest_line.line_no] += diff

        # Apply to lines
        for line in lines:
            line_share = shares.get(line.line_no, Decimal('0.00'))
            set_discount(line, line_share)

    def _compute_gst_and_totals(self, bill: Bill) -> None:
        """
        BR-09: GST Computation.
        Compute GST per item on its final post-discount, post-loyalty-burn taxable value.
        Group item GST amounts by rate slab (0%, 5%, 12%, 18%) and round (ROUND_HALF_UP to 2 decimals)
        per rate slab, NOT per individual item.
        Also allocate exact GST to lines within slab for deterministic refund calculations (BR-12).
        """
        # Calculate taxable value for each line
        for line in bill.lines:
            line.taxable_value = quantize_currency(line.post_threshold_val - line.loyalty_burn_discount)

        bill.subtotal_taxable = sum(line.taxable_value for line in bill.lines)
        bill.gross_total = sum(line.gross_total for line in bill.lines)
        bill.total_discount = sum(line.total_discount for line in bill.lines)

        # Group lines by GST rate slab
        slab_lines: Dict[Decimal, List[BillLine]] = defaultdict(list)
        for line in bill.lines:
            slab_lines[line.gst_rate].append(line)

        bill.gst_by_slab.clear()
        total_gst_accum = Decimal('0.00')

        # Compute for each active slab
        for slab_rate, lines in sorted(slab_lines.items()):
            slab_taxable = sum(l.taxable_value for l in lines)
            # BR-09: Round per rate slab
            slab_gst = quantize_currency(slab_taxable * (slab_rate / Decimal('100')))
            slab_cgst = quantize_currency(slab_gst / Decimal('2'))
            slab_sgst = slab_gst - slab_cgst  # Ensure cgst + sgst == slab_gst

            bill.gst_by_slab[slab_rate] = {
                'taxable': slab_taxable,
                'cgst': slab_cgst,
                'sgst': slab_sgst,
                'total_gst': slab_gst,
            }
            total_gst_accum += slab_gst

            # Allocate slab GST to individual lines proportionally
            if slab_taxable > Decimal('0.00') and slab_gst > Decimal('0.00'):
                alloc_gst = Decimal('0.00')
                largest_l = lines[0]
                max_tax = largest_l.taxable_value

                for l in lines:
                    if l.taxable_value > max_tax:
                        max_tax = l.taxable_value
                        largest_l = l
                    l_gst = quantize_currency((l.taxable_value / slab_taxable) * slab_gst)
                    l.gst_amount = l_gst
                    alloc_gst += l_gst

                # Adjust residual on largest item
                l_diff = slab_gst - alloc_gst
                largest_l.gst_amount += l_diff
            else:
                for l in lines:
                    l.gst_amount = Decimal('0.00')

            for l in lines:
                l.final_total = l.taxable_value + l.gst_amount

        bill.total_gst = total_gst_accum
        bill.grand_total = bill.subtotal_taxable + bill.total_gst

    def _apply_loyalty_earn(self, bill: Bill) -> None:
        """
        BR-10: Loyalty Earn.
        Earn 1 point per full Rs 100 (int(eligible_post_gst_total // 100)) of post-GST bill value,
        excluding TOBACCO and LIQUOR categories.
        Points remain PENDING and are credited only after the 7-day return window closes.
        """
        if not bill.member_id:
            bill.loyalty_points_earned = 0
            return

        eligible_total = sum(
            line.final_total
            for line in bill.lines
            if line.product.category not in ("TOBACCO", "LIQUOR")
        )

        points = int(eligible_total // Decimal('100.00'))
        bill.loyalty_points_earned = points

        if bill.member_id in self.loyalty_accounts:
            account = self.loyalty_accounts[bill.member_id]
            account.pending_points.append({
                'bill_id': bill.bill_id,
                'points': points,
                'timestamp': bill.timestamp,
                'available_after': bill.timestamp + timedelta(days=7),
            })

    def process_return(
        self,
        return_id: str,
        original_bill_id: str,
        timestamp: datetime,
        return_items: Dict[str, Decimal],
    ) -> ReturnNote:
        """
        BR-12 & BR-13: Process full or partial returns.
        - Check 7-day window (return_timestamp <= bill_date + 7 days up to 23:59:59).
        - Weighed items (KG) strictly non-returnable.
        - Refund equals item's effective final price on bill (after all discounts & GST).
        - BR-13 Multi-Buy Return Reversal: if returning paid items breaks group of 3 while
          free item kept, deduct free item's original value. If free item returned, refund is Rs 0.00.
        """
        if original_bill_id not in self.bills:
            raise ValueError(f"Original bill '{original_bill_id}' not found.")

        orig_bill = self.bills[original_bill_id]

        # BR-12: 7-day window validation
        # Day +7 up to 23:59:59
        bill_date = orig_bill.timestamp.date()
        deadline = datetime.combine(bill_date + timedelta(days=7), time(23, 59, 59))
        if timestamp > deadline:
            raise ValueError(
                f"Return rejected: 7-day window expired. Bill date: {bill_date}, Deadline: {deadline}, Return timestamp: {timestamp}"
            )

        return_lines: List[ReturnLine] = []
        total_refund_accum = Decimal('0.00')

        for barcode, return_qty in return_items.items():
            if return_qty <= Decimal('0'):
                continue

            matching_lines = [l for l in orig_bill.lines if l.product.barcode == barcode]
            if not matching_lines:
                raise ValueError(f"Barcode '{barcode}' was not part of original bill '{original_bill_id}'.")

            product = matching_lines[0].product

            # BR-12: Weighed items are strictly non-returnable
            if product.unit == "KG":
                raise ValueError(f"Return rejected: Weighed bulk item '{product.name}' ({barcode}) is strictly non-returnable (BR-12).")

            # Check quantity already returned
            total_purchased_qty = sum(l.qty for l in matching_lines)
            already_returned_qty = self.bill_returns_tracker[original_bill_id][barcode]
            available_to_return = total_purchased_qty - already_returned_qty

            if return_qty > available_to_return:
                raise ValueError(
                    f"Return rejected: Requested qty {return_qty} exceeds available returnable qty {available_to_return} for '{product.name}'."
                )

            # Compute effective unit refund from bill line final totals
            total_final_paid = sum(l.final_total for l in matching_lines)
            effective_unit_refund = quantize_currency(total_final_paid / total_purchased_qty)

            # BR-13: Multi-buy return reversal check
            reversal_deduction = Decimal('0.00')
            for mb_group in orig_bill.multibuy_groups:
                if barcode == mb_group['free_barcode'] and not mb_group['free_returned']:
                    # Edge Case 7: Returning the free item
                    effective_unit_refund = Decimal('0.00')
                    mb_group['free_returned'] = True
                    break
                elif barcode in mb_group['paid_barcodes']:
                    mb_group['paid_returned_count'] += int(return_qty)
                    # If free item was kept and group of 3 is broken
                    if not mb_group['free_returned'] and not mb_group['reversal_applied']:
                        reversal_deduction = mb_group['free_value']
                        mb_group['reversal_applied'] = True
                        break

            gross_refund = quantize_currency(effective_unit_refund * return_qty)
            net_refund = max(Decimal('0.00'), quantize_currency(gross_refund - reversal_deduction))

            r_line = ReturnLine(
                barcode=barcode,
                product_name=product.name,
                qty=return_qty,
                original_unit_price=matching_lines[0].unit_price,
                effective_unit_refund=effective_unit_refund,
                multibuy_reversal_deduction=reversal_deduction,
                net_refund=net_refund,
            )
            return_lines.append(r_line)
            total_refund_accum += net_refund

            # Update returns tracker
            self.bill_returns_tracker[original_bill_id][barcode] += return_qty

        return_note = ReturnNote(
            return_id=return_id,
            original_bill_id=original_bill_id,
            timestamp=timestamp,
            lines=return_lines,
            total_refund=total_refund_accum,
            reason_or_notes="Customer return processed successfully",
        )
        self.returns[return_id] = return_note
        return return_note

    def generate_z_report(self, report_date: date) -> TillZReport:
        """
        Generate Till Z-Report for a specific business date.
        Reconciles all bills, returns, GST collections, loyalty transactions, and cash drawer net sales.
        """
        bills_for_day = [
            b for b in self.bills.values()
            if b.timestamp.date() == report_date
        ]
        returns_for_day = [
            r for r in self.returns.values()
            if r.timestamp.date() == report_date
        ]

        gross_sales = sum(b.gross_total for b in bills_for_day)
        total_discounts = sum(b.total_discount for b in bills_for_day)
        net_taxable = sum(b.subtotal_taxable for b in bills_for_day)
        total_gst = sum(b.total_gst for b in bills_for_day)
        post_gst_sales = sum(b.grand_total for b in bills_for_day)
        total_refunds = sum(r.total_refund for r in returns_for_day)
        net_revenue = quantize_currency(post_gst_sales - total_refunds)

        # Consolidate GST by rate slab
        gst_by_slab: Dict[Decimal, Dict[str, Decimal]] = defaultdict(lambda: {
            'taxable': Decimal('0.00'),
            'cgst': Decimal('0.00'),
            'sgst': Decimal('0.00'),
            'total_gst': Decimal('0.00'),
        })

        for b in bills_for_day:
            for slab_rate, slab_data in b.gst_by_slab.items():
                gst_by_slab[slab_rate]['taxable'] += slab_data['taxable']
                gst_by_slab[slab_rate]['cgst'] += slab_data['cgst']
                gst_by_slab[slab_rate]['sgst'] += slab_data['sgst']
                gst_by_slab[slab_rate]['total_gst'] += slab_data['total_gst']

        points_earned = sum(b.loyalty_points_earned for b in bills_for_day)
        points_redeemed = sum(b.points_redeemed for b in bills_for_day)
        burned_val = sum(b.loyalty_burn_amount for b in bills_for_day)

        return TillZReport(
            report_date=report_date,
            generated_at=datetime.now(),
            total_bills=len(bills_for_day),
            total_returns=len(returns_for_day),
            gross_sales=gross_sales,
            total_discounts=total_discounts,
            net_taxable_sales=net_taxable,
            gst_by_slab=dict(gst_by_slab),
            total_gst=total_gst,
            post_gst_sales=post_gst_sales,
            total_refunds=total_refunds,
            net_revenue=net_revenue,
            points_earned=points_earned,
            points_redeemed=points_redeemed,
            points_burned_value=burned_val,
        )

    def execute_event(self, event: ScanEvent) -> Any:
        """
        Execute a parsed ScanEvent on the engine.
        """
        if event.event_type == "START_BILL":
            return self.start_bill(
                bill_id=event.bill_id,
                timestamp=event.timestamp,
                member_id=event.member_id,
            )
        elif event.event_type == "SCAN":
            return self.scan_item(
                barcode=event.barcode,
                qty=event.qty or Decimal('1'),
                timestamp=event.timestamp,
            )
        elif event.event_type == "WEIGH":
            return self.weigh_item(
                barcode=event.barcode,
                gross_weight=event.gross_weight,
                timestamp=event.timestamp,
            )
        elif event.event_type == "OVERRIDE_QTY":
            return self.override_qty(
                line_no_or_barcode=event.line_no_or_barcode,
                new_qty=event.new_qty,
            )
        elif event.event_type == "VOID":
            return self.void_item(
                line_no_or_barcode=event.line_no_or_barcode,
            )
        elif event.event_type == "APPLY_COUPON":
            return self.apply_coupon(
                coupon_code=event.coupon_code,
                coupon_type=event.coupon_type,
                value=event.coupon_value,
            )
        elif event.event_type == "REDEEM_POINTS":
            return self.redeem_points(
                points=event.points,
            )
        elif event.event_type == "CHECKOUT":
            return self.checkout()
        elif event.event_type == "RETURN":
            return self.process_return(
                return_id=event.return_id,
                original_bill_id=event.original_bill_id,
                timestamp=event.timestamp,
                return_items=event.return_items or {},
            )
        elif event.event_type == "Z_REPORT":
            return self.generate_z_report(
                report_date=event.report_date,
            )
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")
