"""
Data models for the Supermarket POS Billing Engine.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)

All financial figures are stored as decimal.Decimal with ROUND_HALF_UP to 2 decimal places.
All weights are stored as decimal.Decimal with ROUND_HALF_UP to 3 decimal places.
Floats are strictly prohibited.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from typing import Optional, List, Dict, Any


CURRENCY_QUANT = Decimal('0.01')
WEIGHT_QUANT = Decimal('0.001')


def quantize_currency(value: Decimal) -> Decimal:
    """Round currency amount to 2 decimal places using ROUND_HALF_UP."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CURRENCY_QUANT, rounding=ROUND_HALF_UP)


def quantize_weight(value: Decimal) -> Decimal:
    """Round weight to 3 decimal places using ROUND_HALF_UP."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(WEIGHT_QUANT, rounding=ROUND_HALF_UP)


@dataclass
class Product:
    """
    Product Master Record.
    """
    barcode: str
    name: str
    mrp: Decimal
    selling_price: Decimal
    member_price: Decimal
    gst_rate: Decimal
    unit: str  # 'PC' or 'KG'
    category: str  # 'FRESH', 'GROCERY', 'DAIRY', 'TOBACCO', 'LIQUOR', etc.
    tare_weight: Decimal = Decimal('0.000')
    offer_group: str = ""

    def __post_init__(self):
        if not isinstance(self.mrp, Decimal):
            self.mrp = Decimal(str(self.mrp))
        if not isinstance(self.selling_price, Decimal):
            self.selling_price = Decimal(str(self.selling_price))
        if not isinstance(self.member_price, Decimal):
            self.member_price = Decimal(str(self.member_price))
        if not isinstance(self.gst_rate, Decimal):
            self.gst_rate = Decimal(str(self.gst_rate))
        if not isinstance(self.tare_weight, Decimal):
            self.tare_weight = Decimal(str(self.tare_weight))

        self.mrp = quantize_currency(self.mrp)
        self.selling_price = quantize_currency(self.selling_price)
        self.member_price = quantize_currency(self.member_price)
        self.tare_weight = quantize_weight(self.tare_weight)
        self.unit = self.unit.strip().upper()
        self.category = self.category.strip().upper()

    @property
    def effective_selling_price(self) -> Decimal:
        """BR-02: Selling price capped at MRP."""
        return min(self.selling_price, self.mrp)

    @property
    def effective_member_price(self) -> Decimal:
        """BR-02 & BR-06: Member price capped at MRP."""
        if self.member_price > Decimal('0.00'):
            return min(self.member_price, self.mrp)
        return self.effective_selling_price


@dataclass
class ScanEvent:
    """
    Represents an parsed scan action or command event.
    """
    event_type: str  # START_BILL, SCAN, WEIGH, OVERRIDE_QTY, VOID, APPLY_COUPON, REDEEM_POINTS, CHECKOUT, RETURN, Z_REPORT
    barcode: Optional[str] = None
    qty: Optional[Decimal] = None
    gross_weight: Optional[Decimal] = None
    timestamp: Optional[datetime] = None
    line_no_or_barcode: Optional[str] = None
    new_qty: Optional[Decimal] = None
    coupon_code: Optional[str] = None
    coupon_type: Optional[str] = None  # PCT, FIXED
    coupon_value: Optional[Decimal] = None
    points: Optional[int] = None
    bill_id: Optional[str] = None
    member_id: Optional[str] = None
    return_id: Optional[str] = None
    original_bill_id: Optional[str] = None
    return_items: Optional[Dict[str, Decimal]] = None
    report_date: Optional[date] = None


@dataclass
class BillLine:
    """
    Individual itemized line item on a bill.
    """
    line_no: int
    product: Product
    qty: Decimal = Decimal('1')
    gross_weight: Decimal = Decimal('0.000')
    tare_weight: Decimal = Decimal('0.000')
    net_weight: Decimal = Decimal('0.000')
    scan_timestamp: Optional[datetime] = None
    unit_price: Decimal = Decimal('0.00')  # Base effective unit price before discounts: min(selling_price, mrp)
    gross_total: Decimal = Decimal('0.00')

    # Item-level discounts
    multibuy_discount: Decimal = Decimal('0.00')
    category_discount: Decimal = Decimal('0.00')
    member_discount: Decimal = Decimal('0.00')

    # Bill-level apportioned discounts
    coupon_discount: Decimal = Decimal('0.00')
    threshold_discount: Decimal = Decimal('0.00')
    loyalty_burn_discount: Decimal = Decimal('0.00')

    # Tax & totals
    taxable_value: Decimal = Decimal('0.00')
    gst_rate: Decimal = Decimal('0.00')
    gst_amount: Decimal = Decimal('0.00')
    final_total: Decimal = Decimal('0.00')

    # Multi-buy and offer consumption tracking
    free_units_multibuy: int = 0
    paid_units_multibuy: int = 0
    consumed_units_category: int = 0
    consumed_units_member: int = 0

    def __post_init__(self):
        if not isinstance(self.qty, Decimal):
            self.qty = Decimal(str(self.qty))
        if not isinstance(self.gross_weight, Decimal):
            self.gross_weight = Decimal(str(self.gross_weight))
        if not isinstance(self.tare_weight, Decimal):
            self.tare_weight = Decimal(str(self.tare_weight))
        if not isinstance(self.net_weight, Decimal):
            self.net_weight = Decimal(str(self.net_weight))

        if self.product.unit == 'KG':
            self.net_weight = quantize_weight(self.net_weight)
            self.gross_weight = quantize_weight(self.gross_weight)
            self.tare_weight = quantize_weight(self.tare_weight)
        else:
            self.qty = quantize_currency(self.qty)  # or exact integer count

    @property
    def total_discount(self) -> Decimal:
        """Sum of all item-level and apportioned discounts on this line."""
        return quantize_currency(
            self.multibuy_discount +
            self.category_discount +
            self.member_discount +
            self.coupon_discount +
            self.threshold_discount +
            self.loyalty_burn_discount
        )

    @property
    def post_item_offer_val(self) -> Decimal:
        """Value after item-level offers (before coupon, threshold, loyalty burn)."""
        return quantize_currency(
            self.gross_total - (self.multibuy_discount + self.category_discount + self.member_discount)
        )

    @property
    def post_coupon_val(self) -> Decimal:
        """Value after coupon discount."""
        return quantize_currency(self.post_item_offer_val - self.coupon_discount)

    @property
    def post_threshold_val(self) -> Decimal:
        """Value after threshold discount."""
        return quantize_currency(self.post_coupon_val - self.threshold_discount)


@dataclass
class OfferLine:
    """
    Representation of an offer / discount applied to a bill.
    """
    offer_type: str  # 'MULTIBUY', 'CATEGORY', 'MEMBER', 'COUPON', 'THRESHOLD', 'LOYALTY_BURN'
    description: str
    discount_amount: Decimal


@dataclass
class Coupon:
    """
    Coupon details applied to a bill.
    """
    code: str
    coupon_type: str  # 'PCT' or 'FIXED'
    value: Decimal


@dataclass
class Bill:
    """
    Full customer billing transaction.
    """
    bill_id: str
    timestamp: datetime
    member_id: Optional[str] = None
    lines: List[BillLine] = field(default_factory=list)
    offer_lines: List[OfferLine] = field(default_factory=list)
    coupon: Optional[Coupon] = None
    points_requested: int = 0
    points_redeemed: int = 0
    loyalty_burn_amount: Decimal = Decimal('0.00')
    loyalty_points_earned: int = 0  # Earned pending points

    gross_total: Decimal = Decimal('0.00')
    total_discount: Decimal = Decimal('0.00')
    subtotal_taxable: Decimal = Decimal('0.00')
    gst_by_slab: Dict[Decimal, Dict[str, Decimal]] = field(default_factory=dict)
    total_gst: Decimal = Decimal('0.00')
    grand_total: Decimal = Decimal('0.00')
    is_finalized: bool = False

    # Multi-buy group metadata for BR-13 return reversal tracking
    # List of dicts: {'offer_group': str, 'free_barcode': str, 'free_unit_price': Decimal,
    #                 'paid_barcodes': List[str], 'free_returned': bool, 'reversal_applied': bool}
    multibuy_groups: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReturnLine:
    """
    Line item inside a return note.
    """
    barcode: str
    product_name: str
    qty: Decimal
    original_unit_price: Decimal
    effective_unit_refund: Decimal
    multibuy_reversal_deduction: Decimal = Decimal('0.00')
    net_refund: Decimal = Decimal('0.00')


@dataclass
class ReturnNote:
    """
    Record of processed product return and customer refund.
    """
    return_id: str
    original_bill_id: str
    timestamp: datetime
    lines: List[ReturnLine] = field(default_factory=list)
    total_refund: Decimal = Decimal('0.00')
    reason_or_notes: str = ""


@dataclass
class LoyaltyAccount:
    """
    Customer loyalty balance and transaction history.
    """
    member_id: str
    name: str = ""
    points_balance: int = 0
    pending_points: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TillZReport:
    """
    End-of-day till reconciliation report.
    """
    report_date: date
    generated_at: datetime
    total_bills: int = 0
    total_returns: int = 0
    gross_sales: Decimal = Decimal('0.00')
    total_discounts: Decimal = Decimal('0.00')
    net_taxable_sales: Decimal = Decimal('0.00')
    gst_by_slab: Dict[Decimal, Dict[str, Decimal]] = field(default_factory=dict)
    total_gst: Decimal = Decimal('0.00')
    post_gst_sales: Decimal = Decimal('0.00')
    total_refunds: Decimal = Decimal('0.00')
    net_revenue: Decimal = Decimal('0.00')
    points_earned: int = 0
    points_redeemed: int = 0
    points_burned_value: Decimal = Decimal('0.00')
