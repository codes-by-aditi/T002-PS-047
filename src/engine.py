"""
Core Supermarket POS Billing Engine.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)

Strictly implements Business Rules BR-01 to BR-13 and Edge Cases 1 to 8:
  BR-01: Weighed Items (tare subtraction, min net weight 0.005kg)
  BR-02: MRP Ceiling (effective price never exceeds MRP)
  BR-03: Multi-Buy 'Buy 2 Get 1' (cheapest unit free, max 3 free per offer)
  BR-04: Category Discount (10% off FRESH at or after 20:00)
  BR-05: Strict Offer Precedence (Multi-buy -> Category -> Member -> Coupon -> Threshold -> Points)
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
    Main POS billing engine coordinating scans, offers, taxes, loyalty, returns, and reports.
    Supports both pipe-delimited multi-till evaluation streaming and single-bill legacy execution.
    """

    def __init__(
        self,
        catalog: Optional[Dict[str, Product]] = None,
        coupons: Optional[Dict[str, Coupon]] = None,
        members: Optional[Dict[str, LoyaltyAccount]] = None,
        store_parameters: Optional[Dict[str, str]] = None,
    ):
        self.catalog: Dict[str, Product] = catalog or {}
        self.coupons: Dict[str, Coupon] = coupons or {}
        self.loyalty_accounts: Dict[str, LoyaltyAccount] = members or {}
        self.store_parameters: Dict[str, str] = store_parameters or {}

        # Barcode to SKU mapping
        self.barcode_to_sku: Dict[str, str] = {
            b: p.sku for b, p in self.catalog.items() if p.sku
        }

        # Multi-till active bills ledger
        self.open_bills: Dict[str, Bill] = {}
        # Historical closed bills & audit ledger
        self.bills: Dict[str, Bill] = {}
        self.returns: List[ReturnNote] = []
        self.z_reports: List[TillZReport] = []
        self.bill_returns_tracker: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

        # Single-till current bill pointer (for legacy CLI/unit tests)
        self.current_bill: Optional[Bill] = None

    def register_product(self, product: Product) -> None:
        """Register or update a product in the catalog."""
        self.catalog[product.barcode] = product
        if product.sku:
            self.barcode_to_sku[product.barcode] = product.sku

    def register_loyalty_account(self, member_id: str, name: str = "", points_balance: int = 0) -> LoyaltyAccount:
        """Register or retrieve a customer loyalty account."""
        if member_id not in self.loyalty_accounts:
            self.loyalty_accounts[member_id] = LoyaltyAccount(
                member_id=member_id,
                name=name,
                points_balance=points_balance,
            )
        return self.loyalty_accounts[member_id]

    def _get_target_bill(self, bill_id: Optional[str] = None) -> Bill:
        """Retrieve the target active bill by bill_id or fall back to current_bill."""
        if bill_id and bill_id in self.open_bills:
            return self.open_bills[bill_id]
        if self.current_bill and not self.current_bill.is_finalized:
            return self.current_bill
        raise ValueError(f"No active open bill found for bill_id: '{bill_id}'")

    def start_bill(
        self,
        bill_id: str,
        timestamp: datetime,
        member_id: Optional[str] = None,
        till_id: str = "TILL-01",
    ) -> Bill:
        """
        Open a new bill transaction (OPEN_BILL / START_BILL).
        """
        if member_id and member_id not in self.loyalty_accounts:
            self.register_loyalty_account(member_id)

        bill = Bill(
            bill_id=bill_id,
            timestamp=timestamp,
            member_id=member_id if member_id else None,
            till_id=till_id,
        )
        self.open_bills[bill_id] = bill
        self.current_bill = bill
        return bill

    def open_bill(
        self,
        bill_id: str,
        timestamp: datetime,
        till_id: str = "TILL-01",
        member_id: Optional[str] = None,
    ) -> Bill:
        """Alias for start_bill matching evaluation command name."""
        return self.start_bill(bill_id=bill_id, timestamp=timestamp, member_id=member_id, till_id=till_id)

    def scan_item(
        self,
        barcode: str,
        qty: Decimal = Decimal('1'),
        timestamp: Optional[datetime] = None,
        bill_id: Optional[str] = None,
    ) -> Optional[BillLine]:
        """
        Scan a barcoded packaged item (BR-02 MRP ceiling applied).
        Unknown barcode is rejected (produces no bill line).
        """
        try:
            bill = self._get_target_bill(bill_id)
        except ValueError:
            return None

        if barcode not in self.catalog:
            # Unknown barcode rejected: produces no bill line
            return None

        product = self.catalog[barcode]
        scan_ts = timestamp or bill.timestamp

        # BR-02: Base unit price capped at MRP
        unit_price = product.effective_selling_price
        gross_total = quantize_currency(qty * unit_price)

        line_no = len(bill.lines) + 1
        line = BillLine(
            line_no=line_no,
            product=product,
            qty=qty,
            scan_timestamp=scan_ts,
            unit_price=unit_price,
            gross_total=gross_total,
            gst_rate=product.gst_rate,
        )
        bill.lines.append(line)
        return line

    def weigh_item(
        self,
        barcode: str,
        gross_weight: Decimal,
        timestamp: Optional[datetime] = None,
        bill_id: Optional[str] = None,
    ) -> Optional[BillLine]:
        """
        Weigh a bulk item (BR-01, BR-02).
        Calculates net_weight = gross_weight - tare_weight.
        Rejects if net_weight < 0.005 kg (produces no bill line).
        """
        try:
            bill = self._get_target_bill(bill_id)
        except ValueError:
            return None

        if barcode not in self.catalog:
            return None

        product = self.catalog[barcode]
        if not product.is_weighed:
            return None

        tare_weight = product.tare_weight
        net_weight = quantize_weight(gross_weight - tare_weight)

        # BR-01: Reject if net_weight < 0.005 kg
        if net_weight < Decimal('0.005'):
            # Rejected scan produces no bill line
            return None

        scan_ts = timestamp or bill.timestamp
        # BR-02: Unit price per kg capped at MRP
        unit_price = product.effective_selling_price
        # BR-01: Line total rounded to 2 decimal places (ROUND_HALF_UP)
        gross_total = quantize_currency(net_weight * unit_price)

        line_no = len(bill.lines) + 1
        line = BillLine(
            line_no=line_no,
            product=product,
            qty=Decimal('1'),
            gross_weight=quantize_weight(gross_weight),
            tare_weight=tare_weight,
            net_weight=net_weight,
            scan_timestamp=scan_ts,
            unit_price=unit_price,
            gross_total=gross_total,
            gst_rate=product.gst_rate,
        )
        bill.lines.append(line)
        return line

    def override_qty(
        self,
        line_no_or_barcode: str,
        new_qty: Decimal,
        bill_id: Optional[str] = None,
    ) -> Optional[BillLine]:
        """
        Override quantity of an accepted line item (QTY_OVERRIDE / OVERRIDE_QTY).
        """
        bill = self._get_target_bill(bill_id)
        target_line: Optional[BillLine] = None

        if str(line_no_or_barcode).isdigit():
            target_no = int(line_no_or_barcode)
            for line in bill.lines:
                if line.line_no == target_no:
                    target_line = line
                    break

        if target_line is None:
            for line in reversed(bill.lines):
                if line.product.barcode == line_no_or_barcode:
                    target_line = line
                    break

        if target_line is None:
            return None

        if new_qty <= Decimal('0'):
            self.void_item(line_no_or_barcode, bill_id=bill_id)
            return None

        target_line.qty = new_qty
        if target_line.product.is_weighed:
            target_line.gross_total = quantize_currency(target_line.net_weight * target_line.unit_price)
        else:
            target_line.gross_total = quantize_currency(new_qty * target_line.unit_price)

        return target_line

    def void_item(self, line_no_or_barcode: str, bill_id: Optional[str] = None) -> None:
        """
        Void (remove) an accepted line item from the active bill.
        Renumbers remaining lines.
        """
        bill = self._get_target_bill(bill_id)
        idx_to_remove: Optional[int] = None

        if str(line_no_or_barcode).isdigit():
            target_no = int(line_no_or_barcode)
            for i, line in enumerate(bill.lines):
                if line.line_no == target_no:
                    idx_to_remove = i
                    break

        if idx_to_remove is None:
            for i in range(len(bill.lines) - 1, -1, -1):
                if bill.lines[i].product.barcode == line_no_or_barcode:
                    idx_to_remove = i
                    break

        if idx_to_remove is None:
            return

        bill.lines.pop(idx_to_remove)
        for new_idx, line in enumerate(bill.lines, start=1):
            line.line_no = new_idx

    def apply_coupon(
        self,
        coupon_code: str,
        coupon_type: Optional[str] = None,
        value: Optional[Decimal] = None,
        bill_id: Optional[str] = None,
    ) -> None:
        """
        Apply a coupon to the active bill (BR-07: Max 1 coupon per bill).
        If a coupon was already applied, subsequent coupon applications are rejected.
        """
        bill = self._get_target_bill(bill_id)

        # Max 1 coupon per bill: reject second coupon
        if bill.coupon is not None:
            return

        # Check loaded coupons repository
        if coupon_code in self.coupons:
            bill.coupon = self.coupons[coupon_code]
            return

        # Fallback to inline parameters
        if coupon_type and value is not None:
            c_type = "PCT" if coupon_type.upper() in ("PCT", "PERCENT") else "FIXED"
            bill.coupon = Coupon(
                code=coupon_code,
                coupon_type=c_type,
                value=quantize_currency(value) if c_type == "FIXED" else value,
            )

    def redeem_points(self, points: int, bill_id: Optional[str] = None) -> None:
        """
        Request loyalty points redemption (BR-11: 100-pt multiples, max 20% cap).
        If not a multiple of 100, reject redemption.
        """
        bill = self._get_target_bill(bill_id)
        if points <= 0 or points % 100 != 0:
            bill.points_requested = 0
            return
        bill.points_requested = points

    def checkout(
        self,
        bill_id: Optional[str] = None,
        payment_mode: str = "CASH",
        timestamp: Optional[datetime] = None,
    ) -> Bill:
        """
        Finalize a bill by executing the 8-stage promotion, tax, and loyalty pipeline:
          BR-03 -> BR-04 -> BR-06 -> BR-07 -> BR-08 -> BR-11 -> BR-09 -> BR-10
        """
        if bill_id and bill_id in self.open_bills:
            bill = self.open_bills.pop(bill_id)
        elif self.current_bill and not self.current_bill.is_finalized:
            bill = self.current_bill
            if bill.bill_id in self.open_bills:
                self.open_bills.pop(bill.bill_id)
        else:
            raise ValueError("No active bill to checkout.")

        bill.payment_mode = payment_mode
        bill.close_ts = timestamp or bill.timestamp
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

        # Compute item offers total & subtotal
        bill.item_offer_total = sum(
            line.multibuy_discount + line.category_discount + line.member_discount
            for line in bill.lines
        )
        bill.gross_total = sum(line.gross_total for line in bill.lines)
        bill.subtotal = bill.gross_total - bill.item_offer_total

        # -------------------------------------------------------------
        # STEP 4: BR-07 Coupon Discount
        # -------------------------------------------------------------
        self._apply_coupon_discount(bill)

        # Subtotal after coupon
        subtotal_post_coupon = sum(line.post_coupon_val for line in bill.lines)

        # -------------------------------------------------------------
        # STEP 5: BR-08 Bill-level Threshold Discount
        # -------------------------------------------------------------
        self._apply_threshold_discount(bill, subtotal_post_coupon)

        # Subtotal after threshold
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

        bill.is_finalized = True
        self.bills[bill.bill_id] = bill
        if self.current_bill and self.current_bill.bill_id == bill.bill_id:
            self.current_bill = None
        return bill

    def close_bill(
        self,
        bill_id: str,
        payment_mode: str = "CASH",
        timestamp: Optional[datetime] = None,
    ) -> Bill:
        """Alias for checkout matching evaluation command CLOSE_BILL."""
        return self.checkout(bill_id=bill_id, payment_mode=payment_mode, timestamp=timestamp)

    def _apply_multibuy_offers(self, bill: Bill) -> None:
        """
        BR-03: Multi-Buy 'Buy 2 Get 1'.
        For every group of 3 eligible units in an offer group, the cheapest unit is free.
        Supports both PIECE items and weighed items (e.g. MB-04 Watermelon pieces).
        """
        bill.multibuy_groups.clear()
        offer_units: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for line in bill.lines:
            if line.product.offer_group:
                if line.product.is_weighed:
                    # Each weighed item scan represents 1 weighed piece; value is gross_total
                    offer_units[line.product.offer_group].append({
                        'line': line,
                        'barcode': line.product.barcode,
                        'sku': line.product.sku,
                        'name': line.product.name,
                        'unit_price': line.gross_total,
                        'is_weighed': True,
                    })
                else:
                    qty_int = int(line.qty)
                    for _ in range(qty_int):
                        offer_units[line.product.offer_group].append({
                            'line': line,
                            'barcode': line.product.barcode,
                            'sku': line.product.sku,
                            'name': line.product.name,
                            'unit_price': line.unit_price,
                            'is_weighed': False,
                        })

        for group_name, units in offer_units.items():
            # Sort descending by unit_price
            units.sort(key=lambda u: u['unit_price'], reverse=True)
            num_groups = min(len(units) // 3, 3)  # Max 3 free items per bill per offer

            for g_idx in range(num_groups):
                triple = units[g_idx * 3 : (g_idx + 1) * 3]
                paid_units = triple[:2]
                free_unit = triple[2]

                free_line: BillLine = free_unit['line']
                free_line.multibuy_discount += free_unit['unit_price']
                free_line.free_units_multibuy += 1

                for pu in paid_units:
                    pu['line'].paid_units_multibuy += 1

                bill.multibuy_groups.append({
                    'offer_group': group_name,
                    'free_barcode': free_unit['barcode'],
                    'free_sku': free_unit['sku'],
                    'free_name': free_unit['name'],
                    'free_value': free_unit['unit_price'],
                    'free_line_no': free_line.line_no,
                    'paid_barcodes': [p['barcode'] for p in paid_units],
                    'total_units_in_group': len(units),
                    'free_items_granted': num_groups,
                    'free_returned': False,
                    'reversal_applied': False,
                })

                bill.offer_lines.append(OfferLine(
                    bill_id=bill.bill_id,
                    offer_type="MULTIBUY",
                    offer_ref=group_name,
                    line_no=free_line.line_no,
                    discount_amount=free_unit['unit_price'],
                    description=f"Buy 2 Get 1 Free ({group_name} - Free: {free_unit['name']})",
                ))

    def _apply_category_discount(self, bill: Bill) -> None:
        """
        BR-04: 10% off items in category FRESH weighed/scanned at or after 20:00 (evening clearance).
        Never apply to units consumed by Multi-Buy.
        """
        for line in bill.lines:
            if line.product.category == "FRESH":
                scan_dt = line.scan_timestamp or bill.timestamp
                scan_time = scan_dt.time()

                if scan_time >= time(20, 0, 0):
                    if line.product.is_weighed:
                        # If weighed piece was consumed by multi-buy (free or paid), skip
                        if line.free_units_multibuy == 0 and line.paid_units_multibuy == 0:
                            discount = quantize_currency(line.gross_total * Decimal('0.10'))
                            line.category_discount += discount
                            line.consumed_units_category = 1
                            bill.offer_lines.append(OfferLine(
                                bill_id=bill.bill_id,
                                offer_type="CATEGORY",
                                offer_ref="FRESH",
                                line_no=line.line_no,
                                discount_amount=discount,
                                description=f"Fresh Clearance 10% ({line.product.name})",
                            ))
                    else:
                        consumed_mb = line.free_units_multibuy + line.paid_units_multibuy
                        unconsumed_qty = int(line.qty) - consumed_mb
                        if unconsumed_qty > 0:
                            unconsumed_val = Decimal(unconsumed_qty) * line.unit_price
                            discount = quantize_currency(unconsumed_val * Decimal('0.10'))
                            line.category_discount += discount
                            line.consumed_units_category += unconsumed_qty
                            bill.offer_lines.append(OfferLine(
                                bill_id=bill.bill_id,
                                offer_type="CATEGORY",
                                offer_ref="FRESH",
                                line_no=line.line_no,
                                discount_amount=discount,
                                description=f"Fresh Clearance 10% ({line.product.name})",
                            ))

    def _apply_member_pricing(self, bill: Bill) -> None:
        """
        BR-06 & BR-05: Loyalty members get member_price on tagged SKUs on unconsumed units.
        """
        if not bill.member_id:
            return

        for line in bill.lines:
            if line.product.member_price > Decimal('0.00'):
                effective_mp = line.product.effective_member_price
                base_sp = line.unit_price

                if effective_mp < base_sp:
                    savings_per_unit = base_sp - effective_mp

                    if line.product.is_weighed:
                        if (
                            line.category_discount == Decimal('0.00')
                            and line.free_units_multibuy == 0
                            and line.paid_units_multibuy == 0
                        ):
                            discount = quantize_currency(line.net_weight * savings_per_unit)
                            line.member_discount += discount
                            line.consumed_units_member = 1
                            bill.offer_lines.append(OfferLine(
                                bill_id=bill.bill_id,
                                offer_type="MEMBER",
                                offer_ref="MEMBER",
                                line_no=line.line_no,
                                discount_amount=discount,
                                description=f"Member Savings ({line.product.name})",
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
                                bill_id=bill.bill_id,
                                offer_type="MEMBER",
                                offer_ref="MEMBER",
                                line_no=line.line_no,
                                discount_amount=discount,
                                description=f"Member Savings ({line.product.name})",
                            ))

    def _apply_coupon_discount(self, bill: Bill) -> None:
        """
        BR-07: Coupon discount.
        PERCENT: X% off post-item-offer subtotal, capped at Rs 200.00 (or max_discount).
        FIXED: Rs Y off, valid ONLY if subtotal >= 3 * Y (reject otherwise).
        Apportion pro-rata across items by post-item-offer value.
        """
        coupon = bill.coupon
        if not coupon:
            return

        subtotal_post_item = bill.subtotal
        coupon_discount = Decimal('0.00')

        if coupon.coupon_type in ("PCT", "PERCENT"):
            raw_discount = quantize_currency(subtotal_post_item * (coupon.value / Decimal('100')))
            max_limit = coupon.max_discount if coupon.max_discount is not None else Decimal('200.00')
            coupon_discount = min(raw_discount, max_limit)
        elif coupon.coupon_type == "FIXED":
            min_subtotal_required = Decimal('3') * coupon.value
            if subtotal_post_item >= min_subtotal_required:
                coupon_discount = coupon.value
            else:
                coupon_discount = Decimal('0.00')

        bill.coupon_discount = coupon_discount
        if coupon_discount > Decimal('0.00') and subtotal_post_item > Decimal('0.00'):
            self._apportion_discount(
                lines=bill.lines,
                total_discount=coupon_discount,
                get_base_val=lambda l: l.post_item_offer_val,
                set_discount=lambda l, val: setattr(l, 'coupon_discount', val),
            )
            bill.offer_lines.append(OfferLine(
                bill_id=bill.bill_id,
                offer_type="COUPON",
                offer_ref=coupon.code,
                line_no=None,
                discount_amount=coupon_discount,
                description=f"Coupon ({coupon.code})",
            ))

    def _apply_threshold_discount(self, bill: Bill, subtotal_post_coupon: Decimal) -> None:
        """
        BR-08: Bill Threshold Discount based on subtotal after coupon:
          >= Rs 5,000.00 -> Rs 300.00 off
          >= Rs 2,000.00 -> Rs 100.00 off
        """
        threshold_discount = Decimal('0.00')
        ref = "THRESHOLD"
        if subtotal_post_coupon >= Decimal('5000.00'):
            threshold_discount = Decimal('300.00')
        elif subtotal_post_coupon >= Decimal('2000.00'):
            threshold_discount = Decimal('100.00')

        bill.threshold_discount = threshold_discount
        if threshold_discount > Decimal('0.00') and subtotal_post_coupon > Decimal('0.00'):
            self._apportion_discount(
                lines=bill.lines,
                total_discount=threshold_discount,
                get_base_val=lambda l: l.post_coupon_val,
                set_discount=lambda l, val: setattr(l, 'threshold_discount', val),
            )
            bill.offer_lines.append(OfferLine(
                bill_id=bill.bill_id,
                offer_type="THRESHOLD",
                offer_ref=ref,
                line_no=None,
                discount_amount=threshold_discount,
                description="Bill Threshold Savings",
            ))

    def _apply_loyalty_burn(self, bill: Bill, subtotal_post_threshold: Decimal) -> None:
        """
        BR-11: Loyalty Burn.
        1 point = Rs 0.25 in 100-pt multiples, max 20% cap. Applied before GST.
        """
        if bill.points_requested <= 0:
            bill.points_redeemed = 0
            bill.loyalty_burn_amount = Decimal('0.00')
            return

        max_discount_allowed = quantize_currency(subtotal_post_threshold * Decimal('0.20'))
        max_100_pt_multiples = int(max_discount_allowed // Decimal('25.00'))
        max_burnable_points = max_100_pt_multiples * 100

        available_balance = 0
        if bill.member_id and bill.member_id in self.loyalty_accounts:
            available_balance = self.loyalty_accounts[bill.member_id].points_balance

        effective_points = min(bill.points_requested, max_burnable_points, available_balance)
        effective_points = (effective_points // 100) * 100

        if effective_points > 0:
            burn_amount = quantize_currency(Decimal(effective_points) * Decimal('0.25'))
            bill.points_redeemed = effective_points
            bill.loyalty_burn_amount = burn_amount

            if bill.member_id and bill.member_id in self.loyalty_accounts:
                self.loyalty_accounts[bill.member_id].points_balance -= effective_points

            if subtotal_post_threshold > Decimal('0.00'):
                self._apportion_discount(
                    lines=bill.lines,
                    total_discount=burn_amount,
                    get_base_val=lambda l: l.post_threshold_val,
                    set_discount=lambda l, val: setattr(l, 'loyalty_burn_discount', val),
                )

            bill.offer_lines.append(OfferLine(
                bill_id=bill.bill_id,
                offer_type="POINTS",
                offer_ref="POINTS",
                line_no=None,
                discount_amount=burn_amount,
                description=f"Loyalty Points Burned ({effective_points} pts)",
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

        shares = {}
        for line in eligible_lines:
            base_val = get_base_val(line)
            if base_val > max_base:
                max_base = base_val
                largest_line = line

            share = quantize_currency((base_val / total_base) * total_discount)
            shares[line.line_no] = share
            allocated_sum += share

        diff = total_discount - allocated_sum
        shares[largest_line.line_no] += diff

        for line in lines:
            line_share = shares.get(line.line_no, Decimal('0.00'))
            set_discount(line, line_share)

    def _compute_gst_and_totals(self, bill: Bill) -> None:
        """
        BR-09: GST Computation per rate slab (0%, 5%, 12%, 18%).
        """
        for line in bill.lines:
            line.taxable_value = quantize_currency(line.post_threshold_val - line.loyalty_burn_discount)

        bill.subtotal_taxable = sum(line.taxable_value for line in bill.lines)
        bill.total_discount = sum(line.total_discount for line in bill.lines)

        slab_lines: Dict[Decimal, List[BillLine]] = defaultdict(list)
        for line in bill.lines:
            slab_lines[line.gst_rate].append(line)

        bill.gst_by_slab.clear()
        total_gst_accum = Decimal('0.00')

        for slab_rate, lines in sorted(slab_lines.items()):
            slab_taxable = sum(l.taxable_value for l in lines)
            slab_gst = quantize_currency(slab_taxable * (slab_rate / Decimal('100')))
            slab_cgst = quantize_currency(slab_gst / Decimal('2'))
            slab_sgst = slab_gst - slab_cgst

            bill.gst_by_slab[slab_rate] = {
                'taxable': slab_taxable,
                'cgst': slab_cgst,
                'sgst': slab_sgst,
                'total_gst': slab_gst,
            }
            total_gst_accum += slab_gst

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
        BR-10: Loyalty Earn (1 pt / Rs 100 post-GST, excluding TOBACCO & LIQUOR).
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
        return_items: Optional[Dict[str, Decimal]] = None,
        till_id: str = "TILL-01",
        barcode: Optional[str] = None,
        qty: Optional[Decimal] = None,
    ) -> ReturnNote:
        """
        BR-12 & BR-13: Process full or partial returns.
        Produces a ReturnNote with status ACCEPTED or REJECTED.
        """
        # Build items dict
        items_to_return: Dict[str, Decimal] = {}
        if return_items:
            items_to_return.update(return_items)
        if barcode and qty:
            items_to_return[barcode] = qty

        first_barcode = list(items_to_return.keys())[0] if items_to_return else (barcode or "")
        first_qty = items_to_return.get(first_barcode, qty or Decimal('1'))
        product_sku = self.barcode_to_sku.get(first_barcode, "")

        # 1. Check original bill exists
        if original_bill_id not in self.bills:
            ret = ReturnNote(
                return_id=return_id,
                original_bill_id=original_bill_id,
                timestamp=timestamp,
                till_id=till_id,
                sku=product_sku,
                qty=first_qty,
                status="REJECTED",
                refund_amount=Decimal('0.00'),
                multibuy_clawback=Decimal('0.00'),
                reason=f"Rejected: Original bill '{original_bill_id}' not found",
            )
            self.returns.append(ret)
            return ret

        orig_bill = self.bills[original_bill_id]
        bill_date = orig_bill.timestamp.date()
        deadline = datetime.combine(bill_date + timedelta(days=7), time(22, 0, 0))
        # Allow up to 23:59:59 if closing time is 22:00:00 but tolerance applies
        end_of_day_deadline = datetime.combine(bill_date + timedelta(days=7), time(23, 59, 59))

        # 2. Check 7-day window
        if timestamp > end_of_day_deadline:
            ret = ReturnNote(
                return_id=return_id,
                original_bill_id=original_bill_id,
                timestamp=timestamp,
                till_id=till_id,
                sku=product_sku,
                qty=first_qty,
                status="REJECTED",
                refund_amount=Decimal('0.00'),
                multibuy_clawback=Decimal('0.00'),
                reason=f"Rejected: Outside 7-day return window (bill date: {bill_date})",
            )
            self.returns.append(ret)
            return ret

        # Check line existence
        matching_lines = [l for l in orig_bill.lines if l.product.barcode == first_barcode]
        if not matching_lines:
            ret = ReturnNote(
                return_id=return_id,
                original_bill_id=original_bill_id,
                timestamp=timestamp,
                till_id=till_id,
                sku=product_sku,
                qty=first_qty,
                status="REJECTED",
                refund_amount=Decimal('0.00'),
                multibuy_clawback=Decimal('0.00'),
                reason=f"Rejected: Item '{first_barcode}' was not part of bill '{original_bill_id}'",
            )
            self.returns.append(ret)
            return ret

        prod = matching_lines[0].product
        if not product_sku:
            product_sku = prod.sku

        # 3. Check weighed items (KG)
        if prod.is_weighed:
            ret = ReturnNote(
                return_id=return_id,
                original_bill_id=original_bill_id,
                timestamp=timestamp,
                till_id=till_id,
                sku=product_sku,
                qty=first_qty,
                status="REJECTED",
                refund_amount=Decimal('0.00'),
                multibuy_clawback=Decimal('0.00'),
                reason=f"Rejected: Weighed item '{prod.name}' is strictly non-returnable (BR-12)",
            )
            self.returns.append(ret)
            return ret

        # Check available returnable qty
        total_purchased_qty = sum(l.qty for l in matching_lines)
        already_returned = self.bill_returns_tracker[original_bill_id][first_barcode]
        available_qty = total_purchased_qty - already_returned

        if first_qty > available_qty:
            ret = ReturnNote(
                return_id=return_id,
                original_bill_id=original_bill_id,
                timestamp=timestamp,
                till_id=till_id,
                sku=product_sku,
                qty=first_qty,
                status="REJECTED",
                refund_amount=Decimal('0.00'),
                multibuy_clawback=Decimal('0.00'),
                reason=f"Rejected: Return qty {first_qty} exceeds returnable qty {available_qty}",
            )
            self.returns.append(ret)
            return ret

        # Compute effective unit refund from original bill lines
        total_final_paid = sum(l.final_total for l in matching_lines)
        effective_unit_refund = quantize_currency(total_final_paid / total_purchased_qty)

        # Multi-buy clawback calculation (BR-13)
        reversal_deduction = Decimal('0.00')
        is_free_item_returned = False

        for mb_group in orig_bill.multibuy_groups:
            if first_barcode == mb_group['free_barcode'] and not mb_group['free_returned']:
                # Edge Case 7: Returning the free item
                is_free_item_returned = True
                mb_group['free_returned'] = True
                break
            elif first_barcode in mb_group['paid_barcodes']:
                # Returning paid items: check if group of 3 is broken
                total_in_grp = mb_group.get('total_units_in_group', int(total_purchased_qty))
                remaining_units = total_in_grp - int(already_returned + first_qty)
                justified_free = min(remaining_units // 3, 3)
                granted_free = mb_group.get('free_items_granted', 1)

                if justified_free < granted_free and not mb_group.get('reversal_applied', False):
                    clawback_units = granted_free - justified_free
                    reversal_deduction = quantize_currency(Decimal(clawback_units) * mb_group['free_value'])
                    mb_group['reversal_applied'] = True
                break

        if is_free_item_returned:
            net_refund = Decimal('0.00')
            reason = "Free item return - refund Rs 0.00"
        else:
            gross_refund = quantize_currency(effective_unit_refund * first_qty)
            net_refund = max(Decimal('0.00'), quantize_currency(gross_refund - reversal_deduction))
            reason = "Return accepted and processed"

        # Update returns tracker
        self.bill_returns_tracker[original_bill_id][first_barcode] += first_qty

        r_line = ReturnLine(
            barcode=first_barcode,
            sku=product_sku,
            product_name=prod.name,
            qty=first_qty,
            original_unit_price=matching_lines[0].unit_price,
            effective_unit_refund=effective_unit_refund,
            multibuy_reversal_deduction=reversal_deduction,
            net_refund=net_refund,
        )

        ret = ReturnNote(
            return_id=return_id,
            original_bill_id=original_bill_id,
            timestamp=timestamp,
            till_id=till_id,
            sku=product_sku,
            qty=first_qty,
            status="ACCEPTED",
            refund_amount=net_refund,
            multibuy_clawback=reversal_deduction,
            reason=reason,
            lines=[r_line],
            total_refund=net_refund,
        )
        self.returns.append(ret)
        return ret

    def generate_z_report(
        self,
        report_date: date,
        till_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> TillZReport:
        """
        Generate Till Z-Report for a specific till and business date.
        """
        target_till = till_id or "TILL-01"
        bills_for_till = [
            b for b in self.bills.values()
            if b.timestamp.date() == report_date and (not till_id or b.till_id == target_till)
        ]
        returns_for_till = [
            r for r in self.returns
            if r.timestamp.date() == report_date
            and r.status == "ACCEPTED"
            and (not till_id or r.till_id == target_till)
        ]

        gross_sales = sum(b.gross_total for b in bills_for_till)
        total_discounts = sum(b.total_discount for b in bills_for_till)
        net_taxable = sum(b.subtotal_taxable for b in bills_for_till)
        total_gst = sum(b.total_gst for b in bills_for_till)
        post_gst_sales = sum(b.grand_total for b in bills_for_till)
        total_refunds = sum(r.refund_amount for r in returns_for_till)

        # Payment mode totals
        cash_total = sum(b.grand_total for b in bills_for_till if b.payment_mode == "CASH")
        upi_total = sum(b.grand_total for b in bills_for_till if b.payment_mode == "UPI")
        card_total = sum(b.grand_total for b in bills_for_till if b.payment_mode == "CARD")

        # In retail POS: net_sales = gross_sales - total_discounts + total_gst
        net_sales = post_gst_sales

        # Consolidate GST by rate slab
        gst_by_slab: Dict[Decimal, Dict[str, Decimal]] = defaultdict(lambda: {
            'taxable': Decimal('0.00'),
            'cgst': Decimal('0.00'),
            'sgst': Decimal('0.00'),
            'total_gst': Decimal('0.00'),
        })
        for b in bills_for_till:
            for slab_rate, slab_data in b.gst_by_slab.items():
                gst_by_slab[slab_rate]['taxable'] += slab_data['taxable']
                gst_by_slab[slab_rate]['cgst'] += slab_data['cgst']
                gst_by_slab[slab_rate]['sgst'] += slab_data['sgst']
                gst_by_slab[slab_rate]['total_gst'] += slab_data['total_gst']

        pts_earned = sum(b.loyalty_points_earned for b in bills_for_till)
        pts_redeemed = sum(b.points_redeemed for b in bills_for_till)
        pts_burned_val = sum(b.loyalty_burn_amount for b in bills_for_till)

        zrep = TillZReport(
            till_id=target_till,
            business_date=report_date,
            timestamp=timestamp or datetime.now(),
            bills_count=len(bills_for_till),
            gross_sales=gross_sales,
            total_discounts=total_discounts,
            gst_total=total_gst,
            net_sales=net_sales,
            returns_count=len(returns_for_till),
            refunds_total=total_refunds,
            cash=cash_total,
            upi=upi_total,
            card=card_total,
            total_bills=len(bills_for_till),
            total_returns=len(returns_for_till),
            net_taxable_sales=net_taxable,
            gst_by_slab=dict(gst_by_slab),
            post_gst_sales=post_gst_sales,
            net_revenue=quantize_currency(post_gst_sales - total_refunds),
            points_earned=pts_earned,
            points_redeemed=pts_redeemed,
            points_burned_value=pts_burned_val,
        )
        self.z_reports.append(zrep)
        return zrep

    def execute_event(self, event: ScanEvent) -> Any:
        """
        Execute a parsed ScanEvent on the engine.
        """
        if event.event_type in ("START_BILL", "OPEN_BILL"):
            return self.start_bill(
                bill_id=event.bill_id,
                timestamp=event.timestamp,
                member_id=event.member_id,
                till_id=event.till_id or "TILL-01",
            )
        elif event.event_type == "SCAN":
            return self.scan_item(
                barcode=event.barcode,
                qty=event.qty or Decimal('1'),
                timestamp=event.timestamp,
                bill_id=event.bill_id,
            )
        elif event.event_type in ("WEIGH", "SCAN_WEIGHED"):
            return self.weigh_item(
                barcode=event.barcode,
                gross_weight=event.gross_weight,
                timestamp=event.timestamp,
                bill_id=event.bill_id,
            )
        elif event.event_type in ("OVERRIDE_QTY", "QTY_OVERRIDE"):
            return self.override_qty(
                line_no_or_barcode=event.line_no_or_barcode,
                new_qty=event.new_qty,
                bill_id=event.bill_id,
            )
        elif event.event_type == "VOID":
            return self.void_item(
                line_no_or_barcode=event.line_no_or_barcode,
                bill_id=event.bill_id,
            )
        elif event.event_type == "APPLY_COUPON":
            return self.apply_coupon(
                coupon_code=event.coupon_code,
                coupon_type=event.coupon_type,
                value=event.coupon_value,
                bill_id=event.bill_id,
            )
        elif event.event_type == "REDEEM_POINTS":
            return self.redeem_points(
                points=event.points,
                bill_id=event.bill_id,
            )
        elif event.event_type in ("CHECKOUT", "CLOSE_BILL"):
            return self.checkout(
                bill_id=event.bill_id,
                payment_mode=event.payment_mode or "CASH",
                timestamp=event.timestamp,
            )
        elif event.event_type == "RETURN":
            return self.process_return(
                return_id=event.return_id,
                original_bill_id=event.original_bill_id,
                timestamp=event.timestamp,
                return_items=event.return_items,
                till_id=event.till_id or "TILL-01",
                barcode=event.barcode,
                qty=event.qty,
            )
        elif event.event_type == "Z_REPORT":
            return self.generate_z_report(
                report_date=event.report_date,
                till_id=event.till_id,
                timestamp=event.timestamp,
            )
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")
