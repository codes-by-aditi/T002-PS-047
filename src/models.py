"""
Data models for the Supermarket POS Billing Engine.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)

All financial figures are stored as decimal.Decimal with ROUND_HALF_UP to 2 decimal places.
All weights are stored as decimal.Decimal with ROUND_HALF_UP to 3 decimal places.
Floats are strictly prohibited.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict, Any, Union


CURRENCY_QUANT = Decimal('0.01')
WEIGHT_QUANT = Decimal('0.001')


def quantize_currency(value: Union[Decimal, float, int, str]) -> Decimal:
    """Round currency amount to 2 decimal places using ROUND_HALF_UP."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CURRENCY_QUANT, rounding=ROUND_HALF_UP)


def quantize_weight(value: Union[Decimal, float, int, str]) -> Decimal:
    """Round weight to 3 decimal places using ROUND_HALF_UP."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(WEIGHT_QUANT, rounding=ROUND_HALF_UP)


@dataclass
class Product:
    """
    Product Master Record.
    Supports both 300-SKU evaluation schema and standard schema.
    """
    barcode: str
    name: str
    mrp: Decimal
    selling_price: Decimal
    member_price: Decimal
    gst_rate: Decimal
    unit: str  # 'PIECE', 'PC', or 'KG'
    category: str  # 'FRESH', 'STAPLES', 'GROCERY', 'DAIRY', 'SNACKS', 'TOBACCO', 'LIQUOR', etc.
    tare_weight: Decimal = Decimal('0.000')
    offer_group: str = ""
    sku: str = ""

    def __post_init__(self):
        if not isinstance(self.mrp, Decimal):
            self.mrp = Decimal(str(self.mrp or '0.00'))
        if not isinstance(self.selling_price, Decimal):
            self.selling_price = Decimal(str(self.selling_price or self.mrp))
        if not isinstance(self.member_price, Decimal):
            self.member_price = Decimal(str(self.member_price or '0.00'))
        if not isinstance(self.gst_rate, Decimal):
            self.gst_rate = Decimal(str(self.gst_rate or '0'))
        if not isinstance(self.tare_weight, Decimal):
            self.tare_weight = Decimal(str(self.tare_weight or '0.000'))

        self.mrp = quantize_currency(self.mrp)
        self.selling_price = quantize_currency(self.selling_price)
        self.member_price = quantize_currency(self.member_price)
        self.tare_weight = quantize_weight(self.tare_weight)
        
        # Normalize unit: 'PC' or 'PIECE' -> 'PIECE'
        u = self.unit.strip().upper()
        self.unit = 'PIECE' if u in ('PC', 'PIECE') else u
        self.category = self.category.strip().upper()
        self.offer_group = self.offer_group.strip()
        self.sku = self.sku.strip()

    @property
    def is_weighed(self) -> bool:
        return self.unit == 'KG'

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
    Represents a parsed scan action or command event.
    Supports both pipe-separated and space-separated syntax.
    """
    event_type: str  # OPEN_BILL / START_BILL, SCAN, SCAN_WEIGHED / WEIGH, QTY_OVERRIDE / OVERRIDE_QTY, VOID, APPLY_COUPON, REDEEM_POINTS, CLOSE_BILL / CHECKOUT, RETURN, Z_REPORT
    barcode: Optional[str] = None
    qty: Optional[Decimal] = None
    gross_weight: Optional[Decimal] = None
    timestamp: Optional[datetime] = None
    line_no_or_barcode: Optional[str] = None
    line_no: Optional[int] = None
    new_qty: Optional[Decimal] = None
    coupon_code: Optional[str] = None
    coupon_type: Optional[str] = None  # PCT / PERCENT, FIXED
    coupon_value: Optional[Decimal] = None
    points: Optional[int] = None
    bill_id: Optional[str] = None
    till_id: Optional[str] = None
    member_id: Optional[str] = None
    payment_mode: Optional[str] = None  # CASH, UPI, CARD
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

        if self.product.is_weighed:
            self.net_weight = quantize_weight(self.net_weight)
            self.gross_weight = quantize_weight(self.gross_weight)
            self.tare_weight = quantize_weight(self.tare_weight)
        else:
            self.qty = quantize_currency(self.qty)

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
    Maps to offer_lines.csv: bill_id, offer_type, offer_ref, line_no, discount_amount
    """
    bill_id: str = ""
    offer_type: str = ""  # 'MULTIBUY', 'CATEGORY', 'MEMBER', 'COUPON', 'THRESHOLD', 'POINTS'
    offer_ref: str = ""   # e.g. 'MB-01', 'FRESH', 'MEMBER', 'SAVE10', 'THRESHOLD', 'POINTS'
    line_no: Optional[int] = None
    discount_amount: Decimal = Decimal('0.00')
    description: str = ""


@dataclass
class Coupon:
    """
    Coupon details applied to a bill.
    """
    code: str
    coupon_type: str  # 'PERCENT' / 'PCT' or 'FIXED'
    value: Decimal
    max_discount: Optional[Decimal] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


@dataclass
class Bill:
    """
    Full customer billing transaction.
    """
    bill_id: str
    timestamp: datetime  # open_ts
    close_ts: Optional[datetime] = None
    till_id: str = "TILL-01"
    member_id: Optional[str] = None
    payment_mode: str = "CASH"
    lines: List[BillLine] = field(default_factory=list)
    offer_lines: List[OfferLine] = field(default_factory=list)
    coupon: Optional[Coupon] = None
    points_requested: int = 0
    points_redeemed: int = 0
    loyalty_burn_amount: Decimal = Decimal('0.00')
    loyalty_points_earned: int = 0  # Earned pending points

    gross_total: Decimal = Decimal('0.00')
    item_offer_total: Decimal = Decimal('0.00')
    subtotal: Decimal = Decimal('0.00')
    coupon_discount: Decimal = Decimal('0.00')
    threshold_discount: Decimal = Decimal('0.00')
    total_discount: Decimal = Decimal('0.00')
    subtotal_taxable: Decimal = Decimal('0.00')
    gst_by_slab: Dict[Decimal, Dict[str, Decimal]] = field(default_factory=dict)
    total_gst: Decimal = Decimal('0.00')
    grand_total: Decimal = Decimal('0.00')
    is_finalized: bool = False

    # Multi-buy group metadata for return clawback reversal (BR-13)
    multibuy_groups: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReturnLine:
    """
    Line item inside a return note.
    """
    barcode: str
    sku: str
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
    Maps to return_notes.csv: return_id, original_bill_id, sku, qty, status, refund_amount, multibuy_clawback, reason
    """
    return_id: str
    original_bill_id: str
    timestamp: datetime
    till_id: str = "TILL-01"
    sku: str = ""
    qty: Decimal = Decimal('0')
    status: str = "ACCEPTED"  # ACCEPTED or REJECTED
    refund_amount: Decimal = Decimal('0.00')
    multibuy_clawback: Decimal = Decimal('0.00')
    reason: str = ""
    lines: List[ReturnLine] = field(default_factory=list)
    total_refund: Decimal = Decimal('0.00')


@dataclass
class LoyaltyAccount:
    """
    Customer loyalty balance and transaction history.
    """
    member_id: str
    name: str = ""
    mobile: str = ""
    points_balance: int = 0
    pending_points: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TillZReport:
    """
    End-of-day till reconciliation report.
    Maps to z_report.csv: till_id, business_date, bills_count, gross_sales, total_discounts, gst_total, net_sales, returns_count, refunds_total, cash, upi, card
    """
    till_id: str
    business_date: date
    timestamp: datetime
    bills_count: int = 0
    gross_sales: Decimal = Decimal('0.00')
    total_discounts: Decimal = Decimal('0.00')
    gst_total: Decimal = Decimal('0.00')
    net_sales: Decimal = Decimal('0.00')
    returns_count: int = 0
    refunds_total: Decimal = Decimal('0.00')
    cash: Decimal = Decimal('0.00')
    upi: Decimal = Decimal('0.00')
    card: Decimal = Decimal('0.00')
    
    # Internal breakdown
    total_bills: int = 0
    total_returns: int = 0
    net_taxable_sales: Decimal = Decimal('0.00')
    gst_by_slab: Dict[Decimal, Dict[str, Decimal]] = field(default_factory=dict)
    post_gst_sales: Decimal = Decimal('0.00')
    net_revenue: Decimal = Decimal('0.00')
    points_earned: int = 0
    points_redeemed: int = 0
    points_burned_value: Decimal = Decimal('0.00')
