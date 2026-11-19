"""
Comprehensive Unit Test Suite for Supermarket POS Billing Engine.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)

Covers:
  - All 13 Business Rules: BR-01 to BR-13
  - All 8 Explicit Required Edge Cases
  - Operational Commands: OVERRIDE_QTY, VOID, Till Z-Report Reconciliation
"""

import unittest
from datetime import datetime, date, time
from decimal import Decimal

from src.models import (
    Product,
    Bill,
    ReturnNote,
    TillZReport,
    quantize_currency,
    quantize_weight,
)
from src.engine import POSEngine


class TestPOSBillingEngine(unittest.TestCase):

    def setUp(self):
        """Set up a test catalog and engine instance before each test."""
        self.catalog = {
            # Standard grocery items
            "P100": Product(
                barcode="P100",
                name="Basmati Rice 1kg",
                mrp=Decimal("120.00"),
                selling_price=Decimal("100.00"),
                member_price=Decimal("90.00"),
                gst_rate=Decimal("5.0"),
                unit="PC",
                category="GROCERY",
            ),
            "P101": Product(
                barcode="P101",
                name="Cooking Oil 1L",
                mrp=Decimal("200.00"),
                selling_price=Decimal("180.00"),
                member_price=Decimal("170.00"),
                gst_rate=Decimal("12.0"),
                unit="PC",
                category="GROCERY",
            ),
            # Weighed items
            "W200": Product(
                barcode="W200",
                name="Fresh Apples",
                mrp=Decimal("150.00"),
                selling_price=Decimal("120.00"),
                member_price=Decimal("110.00"),
                gst_rate=Decimal("5.0"),
                unit="KG",
                category="FRESH",
                tare_weight=Decimal("0.050"),
            ),
            "W201": Product(
                barcode="W201",
                name="Fresh Tomatoes",
                mrp=Decimal("50.00"),
                selling_price=Decimal("40.00"),
                member_price=Decimal("35.00"),
                gst_rate=Decimal("0.0"),
                unit="KG",
                category="FRESH",
                tare_weight=Decimal("0.020"),
            ),
            # Multi-buy items (Offer group B2G1_CHOC)
            "M301": Product(
                barcode="M301",
                name="Dark Chocolate 100g",
                mrp=Decimal("100.00"),
                selling_price=Decimal("100.00"),
                member_price=Decimal("95.00"),
                gst_rate=Decimal("18.0"),
                unit="PC",
                category="SNACKS",
                offer_group="B2G1_CHOC",
            ),
            "M302": Product(
                barcode="M302",
                name="Milk Chocolate 80g",
                mrp=Decimal("80.00"),
                selling_price=Decimal("80.00"),
                member_price=Decimal("75.00"),
                gst_rate=Decimal("18.0"),
                unit="PC",
                category="SNACKS",
                offer_group="B2G1_CHOC",
            ),
            "M303": Product(
                barcode="M303",
                name="White Chocolate 60g",
                mrp=Decimal("60.00"),
                selling_price=Decimal("60.00"),
                member_price=Decimal("55.00"),
                gst_rate=Decimal("18.0"),
                unit="PC",
                category="SNACKS",
                offer_group="B2G1_CHOC",
            ),
            "M304": Product(
                barcode="M304",
                name="Almond Chocolate 40g",
                mrp=Decimal("40.00"),
                selling_price=Decimal("40.00"),
                member_price=Decimal("38.00"),
                gst_rate=Decimal("18.0"),
                unit="PC",
                category="SNACKS",
                offer_group="B2G1_CHOC",
            ),
            # Packaged Fresh item for evening clearance
            "F400": Product(
                barcode="F400",
                name="Organic Spinach Pack",
                mrp=Decimal("50.00"),
                selling_price=Decimal("50.00"),
                member_price=Decimal("45.00"),
                gst_rate=Decimal("0.0"),
                unit="PC",
                category="FRESH",
            ),
            # Excluded from loyalty earn
            "T500": Product(
                barcode="T500",
                name="Cigarettes Pack",
                mrp=Decimal("300.00"),
                selling_price=Decimal("300.00"),
                member_price=Decimal("300.00"),
                gst_rate=Decimal("18.0"),
                unit="PC",
                category="TOBACCO",
            ),
            "L501": Product(
                barcode="L501",
                name="Red Wine 750ml",
                mrp=Decimal("800.00"),
                selling_price=Decimal("800.00"),
                member_price=Decimal("800.00"),
                gst_rate=Decimal("18.0"),
                unit="PC",
                category="LIQUOR",
            ),
            # High-value items for threshold tests
            "H600": Product(
                barcode="H600",
                name="Smartphone 5G",
                mrp=Decimal("15000.00"),
                selling_price=Decimal("14000.00"),
                member_price=Decimal("13500.00"),
                gst_rate=Decimal("18.0"),
                unit="PC",
                category="ELECTRONICS",
            ),
        }
        self.engine = POSEngine(catalog=self.catalog)
        self.engine.register_loyalty_account("MEM001", name="Aditi Anshu", points_balance=500)
        self.engine.register_loyalty_account("MEM002", name="Aditi Chaudhary", points_balance=100)

    # =========================================================================
    # BUSINESS RULES UNIT TESTS (BR-01 TO BR-13)
    # =========================================================================

    def test_br01_weighed_items_tare_subtraction(self):
        """BR-01: Net weight = gross_weight - tare_weight. Priced per kg to 3 decimals."""
        self.engine.start_bill("B-01", datetime(2026, 11, 15, 10, 0))
        # Gross = 1.050 kg, tare = 0.050 kg -> Net = 1.000 kg. Price = Rs 120.00/kg
        line = self.engine.weigh_item("W200", gross_weight=Decimal("1.050"))
        self.assertEqual(line.net_weight, Decimal("1.000"))
        self.assertEqual(line.gross_total, Decimal("120.00"))

        bill = self.engine.checkout()
        self.assertEqual(bill.gross_total, Decimal("120.00"))

    def test_br02_mrp_ceiling_enforcement(self):
        """BR-02: No item may ever be billed above its MRP."""
        # Create product with selling price > MRP
        prod = Product(
            barcode="OVER_MRP",
            name="Over MRP Item",
            mrp=Decimal("50.00"),
            selling_price=Decimal("65.00"),
            member_price=Decimal("70.00"),
            gst_rate=Decimal("5.0"),
            unit="PC",
            category="GROCERY",
        )
        self.engine.register_product(prod)
        self.engine.start_bill("B-02", datetime(2026, 11, 15, 10, 0))
        line = self.engine.scan_item("OVER_MRP", qty=Decimal("2"))
        self.assertEqual(line.unit_price, Decimal("50.00"))
        self.assertEqual(line.gross_total, Decimal("100.00"))
        bill = self.engine.checkout()
        self.assertEqual(bill.gross_total, Decimal("100.00"))

    def test_br03_multibuy_buy2_get1_free(self):
        """BR-03: Multi-Buy Buy 2 Get 1 Free on tagged SKUs/offer group."""
        self.engine.start_bill("B-03", datetime(2026, 11, 15, 12, 0))
        # Scan 3 chocolates: 100, 80, 60
        self.engine.scan_item("M301", qty=Decimal("1"))  # 100
        self.engine.scan_item("M302", qty=Decimal("1"))  # 80
        self.engine.scan_item("M303", qty=Decimal("1"))  # 60
        bill = self.engine.checkout()

        # The cheapest unit (60) should be 100% free
        self.assertEqual(bill.gross_total, Decimal("240.00"))
        # Multibuy discount should be Rs 60.00
        self.assertEqual(bill.total_discount, Decimal("60.00"))
        self.assertEqual(bill.subtotal_taxable, Decimal("180.00"))

    def test_br04_category_discount_evening_clearance(self):
        """BR-04: 10% off FRESH category scanned at or after 20:00."""
        # 1. Scanned at 20:30 (evening clearance active)
        self.engine.start_bill("B-04A", datetime(2026, 11, 15, 20, 30))
        self.engine.scan_item("F400", qty=Decimal("2"))  # 2 * 50 = 100.00
        bill = self.engine.checkout()
        # 10% discount on 100.00 = 10.00
        self.assertEqual(bill.total_discount, Decimal("10.00"))
        self.assertEqual(bill.subtotal_taxable, Decimal("90.00"))

        # 2. Scanned at 14:00 (clearance inactive)
        self.engine.start_bill("B-04B", datetime(2026, 11, 15, 14, 0))
        self.engine.scan_item("F400", qty=Decimal("2"))
        bill_day = self.engine.checkout()
        self.assertEqual(bill_day.total_discount, Decimal("0.00"))

    def test_br05_offer_precedence_exclusion(self):
        """BR-05: Strict precedence: units consumed by multi-buy excluded from member pricing."""
        self.engine.start_bill("B-05", datetime(2026, 11, 15, 12, 0), member_id="MEM001")
        # Scan 3 chocolates forming a complete group of 3 (M301: 100, M302: 80, M303: 60)
        self.engine.scan_item("M301", qty=Decimal("1"))
        self.engine.scan_item("M302", qty=Decimal("1"))
        self.engine.scan_item("M303", qty=Decimal("1"))
        bill = self.engine.checkout()

        # All 3 units consumed by multi-buy (60 is free, 100 & 80 are paid parts of the triple)
        # Therefore, none of them receive member pricing
        self.assertEqual(bill.lines[0].member_discount, Decimal("0.00"))
        self.assertEqual(bill.lines[1].member_discount, Decimal("0.00"))
        self.assertEqual(bill.lines[2].member_discount, Decimal("0.00"))
        self.assertEqual(bill.total_discount, Decimal("60.00"))

    def test_br06_member_pricing_on_unconsumed_items(self):
        """BR-06: Loyalty members get member_price on tagged SKUs."""
        self.engine.start_bill("B-06", datetime(2026, 11, 15, 12, 0), member_id="MEM001")
        # P100 SP is 100.00, MP is 90.00 (savings = 10.00 per unit)
        self.engine.scan_item("P100", qty=Decimal("2"))
        bill = self.engine.checkout()
        self.assertEqual(bill.lines[0].member_discount, Decimal("20.00"))
        self.assertEqual(bill.subtotal_taxable, Decimal("180.00"))

    def test_br07_coupon_percentage_and_fixed(self):
        """BR-07: Coupon (Max 1 per bill, PCT capped at 200, FIXED valid if subtotal >= 3*value)."""
        # PCT Coupon capped at 200
        self.engine.start_bill("B-07A", datetime(2026, 11, 15, 12, 0))
        # High value item: 14000.00
        self.engine.scan_item("H600", qty=Decimal("1"))
        # 10% of 14000 is 1400, but capped at 200.00
        self.engine.apply_coupon("SAVE10", "PCT", Decimal("10"))
        bill_pct = self.engine.checkout()
        self.assertEqual(bill_pct.lines[0].coupon_discount, Decimal("200.00"))

        # FIXED Coupon rejected if subtotal < 3 * value
        self.engine.start_bill("B-07B", datetime(2026, 11, 15, 12, 0))
        self.engine.scan_item("P100", qty=Decimal("1"))  # 100.00
        # FIXED 50 requires subtotal >= 150.00; subtotal is 100.00 -> rejected
        self.engine.apply_coupon("FLAT50", "FIXED", Decimal("50.00"))
        bill_fixed = self.engine.checkout()
        self.assertEqual(bill_fixed.lines[0].coupon_discount, Decimal("0.00"))

        # FIXED Coupon accepted if subtotal >= 3 * value
        self.engine.start_bill("B-07C", datetime(2026, 11, 15, 12, 0))
        self.engine.scan_item("P100", qty=Decimal("2"))  # 200.00 >= 150.00
        self.engine.apply_coupon("FLAT50", "FIXED", Decimal("50.00"))
        bill_fixed_ok = self.engine.checkout()
        self.assertEqual(bill_fixed_ok.lines[0].coupon_discount, Decimal("50.00"))

    def test_br08_bill_threshold_discount(self):
        """BR-08: Subtotal after coupon >= 5000 -> 300 off, >= 2000 -> 100 off."""
        # Test >= 5000
        self.engine.start_bill("B-08A", datetime(2026, 11, 15, 12, 0))
        self.engine.scan_item("H600", qty=Decimal("1"))  # 14000.00
        bill_5000 = self.engine.checkout()
        self.assertEqual(bill_5000.lines[0].threshold_discount, Decimal("300.00"))

        # Test between 2000 and 5000
        self.engine.start_bill("B-08B", datetime(2026, 11, 15, 12, 0))
        self.engine.scan_item("P101", qty=Decimal("15"))  # 15 * 180 = 2700.00
        bill_2000 = self.engine.checkout()
        self.assertEqual(bill_2000.lines[0].threshold_discount, Decimal("100.00"))

    def test_br09_gst_rate_slab_grouping_and_rounding(self):
        """BR-09: GST computed per item taxable value and rounded per rate slab."""
        self.engine.start_bill("B-09", datetime(2026, 11, 15, 12, 0))
        # 5% slab item: P100 (100.00)
        self.engine.scan_item("P100", qty=Decimal("1"))
        # 12% slab item: P101 (180.00)
        self.engine.scan_item("P101", qty=Decimal("1"))
        bill = self.engine.checkout()

        # Slab 5%: taxable 100.00, GST = 5.00 (CGST 2.50, SGST 2.50)
        # Slab 12%: taxable 180.00, GST = 21.60 (CGST 10.80, SGST 10.80)
        self.assertIn(Decimal("5.0"), bill.gst_by_slab)
        self.assertIn(Decimal("12.0"), bill.gst_by_slab)
        self.assertEqual(bill.gst_by_slab[Decimal("5.0")]["total_gst"], Decimal("5.00"))
        self.assertEqual(bill.gst_by_slab[Decimal("12.0")]["total_gst"], Decimal("21.60"))
        self.assertEqual(bill.total_gst, Decimal("26.60"))
        self.assertEqual(bill.grand_total, Decimal("306.60"))

    def test_br10_loyalty_earn_and_exclusions(self):
        """BR-10: 1 point per Rs 100 post-GST excluding TOBACCO and LIQUOR."""
        self.engine.start_bill("B-10", datetime(2026, 11, 15, 12, 0), member_id="MEM001")
        # Eligible item: P100 (MP = 90.00, 2 units = 180.00 + 5% GST = 189.00) -> 1 point
        self.engine.scan_item("P100", qty=Decimal("2"))
        # Ineligible items: TOBACCO (300 + 18% GST = 354) and LIQUOR (800 + 18% GST = 944)
        # Total ineligible = 1298.00 (which would give 12 points if eligible)
        self.engine.scan_item("T500", qty=Decimal("1"))
        self.engine.scan_item("L501", qty=Decimal("1"))
        bill = self.engine.checkout()

        # Only P100 (post-GST 189.00) qualifies -> int(189.00 // 100) = 1 point
        self.assertEqual(bill.loyalty_points_earned, 1)

    def test_br11_loyalty_burn_rules(self):
        """BR-11: 1 pt = Rs 0.25, 100 multiples, 20% cap, applied before GST."""
        self.engine.start_bill("B-11", datetime(2026, 11, 15, 12, 0), member_id="MEM001")
        # Subtotal: 5 * 180 = 900.00 (post-threshold). 20% cap = 180.00.
        # 100 points = Rs 25.00. Max points = floor(180 / 25) * 100 = 700 pts.
        # Member has 500 points available in account.
        self.engine.scan_item("P101", qty=Decimal("5"))
        self.engine.redeem_points(200)  # 200 pts = Rs 50.00 <= Rs 180.00 cap
        bill = self.engine.checkout()

        self.assertEqual(bill.points_redeemed, 200)
        self.assertEqual(bill.loyalty_burn_amount, Decimal("50.00"))
        # Account balance was 500, now should be 300
        self.assertEqual(self.engine.loyalty_accounts["MEM001"].points_balance, 300)

    def test_br12_returns_and_window(self):
        """BR-12: Returns within 7 days against original bill, weighed items non-returnable."""
        self.engine.start_bill("B-12", datetime(2026, 11, 1, 10, 0))
        self.engine.scan_item("P100", qty=Decimal("2"))
        self.engine.weigh_item("W200", gross_weight=Decimal("1.050"))
        bill = self.engine.checkout()

        # 1. Attempt returning weighed item -> rejected
        rejected_weighed = self.engine.process_return(
            return_id="R-1",
            original_bill_id="B-12",
            timestamp=datetime(2026, 11, 3, 10, 0),
            return_items={"W200": Decimal("1")},
        )
        self.assertEqual(rejected_weighed.status, "REJECTED")

        # 2. Return packaged item within 7 days -> successful
        ret = self.engine.process_return(
            return_id="R-2",
            original_bill_id="B-12",
            timestamp=datetime(2026, 11, 5, 10, 0),
            return_items={"P100": Decimal("1")},
        )
        self.assertEqual(ret.lines[0].qty, Decimal("1"))
        self.assertGreater(ret.total_refund, Decimal("0.00"))

    def test_br13_multibuy_return_reversal(self):
        """BR-13: Returning paid item breaks active group of 3 while free item kept -> deduct free item value."""
        self.engine.start_bill("B-13", datetime(2026, 11, 1, 10, 0))
        self.engine.scan_item("M301", qty=Decimal("1"))  # 100 (paid)
        self.engine.scan_item("M302", qty=Decimal("1"))  # 80 (paid)
        self.engine.scan_item("M303", qty=Decimal("1"))  # 60 (free)
        bill = self.engine.checkout()

        # Customer returns M301 (paid item, 100).
        # Free item M303 (value 60) was kept.
        # Multi-buy group is broken: 60.00 must be deducted from refund!
        ret = self.engine.process_return(
            return_id="R-13",
            original_bill_id="B-13",
            timestamp=datetime(2026, 11, 3, 10, 0),
            return_items={"M301": Decimal("1")},
        )
        # Check that reversal deduction was applied
        self.assertEqual(ret.lines[0].multibuy_reversal_deduction, Decimal("60.00"))

    # =========================================================================
    # THE 8 EXPLICIT REQUIRED EDGE CASES
    # =========================================================================

    def test_edge_case_1_net_weight_boundary(self):
        """Edge Case 1: Net weight of exactly 0.005 kg (accepted) vs 0.004 kg (rejected)."""
        # W200 tare is 0.050 kg
        self.engine.start_bill("EC-01", datetime(2026, 11, 15, 10, 0))

        # 1. Gross = 0.055 kg -> Net = 0.005 kg (exactly minimum) -> Accepted
        line_ok = self.engine.weigh_item("W200", gross_weight=Decimal("0.055"))
        self.assertEqual(line_ok.net_weight, Decimal("0.005"))

        # 2. Gross = 0.054 kg -> Net = 0.004 kg -> Rejected (ValueError)
        with self.assertRaises(ValueError):
            self.engine.weigh_item("W200", gross_weight=Decimal("0.054"))

    def test_edge_case_2_member_price_above_mrp(self):
        """Edge Case 2: Member price above MRP (capped at MRP)."""
        # Create item where member_price > mrp
        prod = Product(
            barcode="EC02_PROD",
            name="Capped Member Item",
            mrp=Decimal("100.00"),
            selling_price=Decimal("110.00"),  # > MRP
            member_price=Decimal("120.00"),   # > MRP
            gst_rate=Decimal("5.0"),
            unit="PC",
            category="GROCERY",
        )
        self.engine.register_product(prod)
        self.engine.start_bill("EC-02", datetime(2026, 11, 15, 10, 0), member_id="MEM001")
        line = self.engine.scan_item("EC02_PROD", qty=Decimal("1"))
        # Unit price is capped at MRP = 100.00
        self.assertEqual(line.unit_price, Decimal("100.00"))
        bill = self.engine.checkout()
        self.assertEqual(bill.gross_total, Decimal("100.00"))
        # Effective member price cannot exceed MRP
        self.assertEqual(prod.effective_member_price, Decimal("100.00"))

    def test_edge_case_3_four_items_different_prices_multibuy(self):
        """Edge Case 3: Four items of different prices (100, 80, 60, 40) in one multi-buy group.
        60 is free; 40 is outside group of 3 and paid at full price.
        """
        self.engine.start_bill("EC-03", datetime(2026, 11, 15, 10, 0))
        self.engine.scan_item("M301", qty=Decimal("1"))  # 100
        self.engine.scan_item("M302", qty=Decimal("1"))  # 80
        self.engine.scan_item("M303", qty=Decimal("1"))  # 60
        self.engine.scan_item("M304", qty=Decimal("1"))  # 40
        bill = self.engine.checkout()

        # Total gross = 100 + 80 + 60 + 40 = 280.00
        self.assertEqual(bill.gross_total, Decimal("280.00"))
        # In the group of 3 (100, 80, 60), 60 is the cheapest and free
        # 40 is outside the group and receives no multi-buy discount
        self.assertEqual(bill.lines[2].multibuy_discount, Decimal("60.00"))  # M303
        self.assertEqual(bill.lines[3].multibuy_discount, Decimal("0.00"))   # M304
        self.assertEqual(bill.total_discount, Decimal("60.00"))

    def test_edge_case_4_evening_clearance_exactly_20_00(self):
        """Edge Case 4: Evening clearance scan of FRESH item at exactly 20:00 (receives 10% discount)."""
        # Exactly 20:00:00
        self.engine.start_bill("EC-04A", datetime(2026, 11, 15, 20, 0, 0))
        self.engine.scan_item("F400", qty=Decimal("1"), timestamp=datetime(2026, 11, 15, 20, 0, 0))
        bill_2000 = self.engine.checkout()
        # Item price 50.00 -> 10% discount = 5.00
        self.assertEqual(bill_2000.lines[0].category_discount, Decimal("5.00"))

        # One second before at 19:59:59 -> No clearance discount
        self.engine.start_bill("EC-04B", datetime(2026, 11, 15, 19, 59, 59))
        self.engine.scan_item("F400", qty=Decimal("1"), timestamp=datetime(2026, 11, 15, 19, 59, 59))
        bill_1959 = self.engine.checkout()
        self.assertEqual(bill_1959.lines[0].category_discount, Decimal("0.00"))

    def test_edge_case_5_subtotal_exactly_2000_threshold(self):
        """Edge Case 5: Subtotal of exactly Rs 2,000.00 after coupon (triggers Rs 100.00 threshold discount)."""
        # Create item priced at 2000.00
        prod = Product(
            barcode="EXACT_2000",
            name="Exact 2000 Item",
            mrp=Decimal("2000.00"),
            selling_price=Decimal("2000.00"),
            member_price=Decimal("2000.00"),
            gst_rate=Decimal("12.0"),
            unit="PC",
            category="GROCERY",
        )
        self.engine.register_product(prod)
        self.engine.start_bill("EC-05", datetime(2026, 11, 15, 10, 0))
        self.engine.scan_item("EXACT_2000", qty=Decimal("1"))
        bill = self.engine.checkout()

        # Exactly 2000.00 triggers Rs 100.00 threshold discount
        self.assertEqual(bill.lines[0].threshold_discount, Decimal("100.00"))
        self.assertEqual(bill.subtotal_taxable, Decimal("1900.00"))

    def test_edge_case_6_loyalty_burn_20_percent_cap_blocked(self):
        """Edge Case 6: Redemption of 100 points (Rs 25) on a Rs 100.00 bill (exceeds 20% cap of Rs 20.00, so blocked/0 redeemed)."""
        self.engine.start_bill("EC-06", datetime(2026, 11, 15, 10, 0), member_id="MEM001")
        # P100 is 100.00
        self.engine.scan_item("P100", qty=Decimal("1"))
        # Request 100 points (value Rs 25.00). 20% cap of 100.00 is Rs 20.00.
        # Since even 100 points exceeds Rs 20.00, 0 points redeemed (blocked).
        self.engine.redeem_points(100)
        bill = self.engine.checkout()

        self.assertEqual(bill.points_redeemed, 0)
        self.assertEqual(bill.loyalty_burn_amount, Decimal("0.00"))

    def test_edge_case_7_return_free_item_multibuy(self):
        """Edge Case 7: Return of the free item in a multi-buy group (refund = Rs 0.00)."""
        self.engine.start_bill("EC-07", datetime(2026, 11, 1, 10, 0))
        self.engine.scan_item("M301", qty=Decimal("1"))  # 100
        self.engine.scan_item("M302", qty=Decimal("1"))  # 80
        self.engine.scan_item("M303", qty=Decimal("1"))  # 60 (Free item)
        self.engine.checkout()

        # Return M303 (the free item)
        ret = self.engine.process_return(
            return_id="RET-FREE",
            original_bill_id="EC-07",
            timestamp=datetime(2026, 11, 3, 10, 0),
            return_items={"M303": Decimal("1")},
        )
        self.assertEqual(ret.lines[0].net_refund, Decimal("0.00"))
        self.assertEqual(ret.total_refund, Decimal("0.00"))

    def test_edge_case_8_return_day_7_closing_vs_day_8(self):
        """Edge Case 8: Return on Day 7 at store closing (23:59:59 on Day +7 -> accepted; 00:00:00 on Day +8 -> rejected)."""
        # Bill on 2026-11-01 at 10:00:00
        self.engine.start_bill("EC-08", datetime(2026, 11, 1, 10, 0, 0))
        self.engine.scan_item("P100", qty=Decimal("1"))
        self.engine.checkout()

        # Day +7 is 2026-11-08.
        # 1. Day +7 at 23:59:59 -> Accepted
        ret_accepted = self.engine.process_return(
            return_id="RET-DAY7-OK",
            original_bill_id="EC-08",
            timestamp=datetime(2026, 11, 8, 23, 59, 59),
            return_items={"P100": Decimal("1")},
        )
        self.assertGreater(ret_accepted.total_refund, Decimal("0.00"))

        # Create another bill to test rejection on Day +8
        self.engine.start_bill("EC-08-REJ", datetime(2026, 11, 1, 10, 0, 0))
        self.engine.scan_item("P100", qty=Decimal("1"))
        self.engine.checkout()

        # 2. Day +8 at 00:00:00 -> Rejected (ValueError)
        rejected_day8 = self.engine.process_return(
            return_id="RET-DAY8-FAIL",
            original_bill_id="EC-08-REJ",
            timestamp=datetime(2026, 11, 9, 0, 0, 0),
            return_items={"P100": Decimal("1")},
        )
        self.assertEqual(rejected_day8.status, "REJECTED")

    # =========================================================================
    # OPERATIONAL FEATURES: OVERRIDE_QTY, VOID, TILL Z-REPORT
    # =========================================================================

    def test_override_qty_and_void(self):
        """Test OVERRIDE_QTY and VOID command operations."""
        self.engine.start_bill("B-OPS", datetime(2026, 11, 15, 10, 0))
        self.engine.scan_item("P100", qty=Decimal("1"))
        self.engine.scan_item("P101", qty=Decimal("1"))

        # Override quantity of P100 from 1 to 4
        self.engine.override_qty("P100", new_qty=Decimal("4"))
        self.assertEqual(self.engine.current_bill.lines[0].qty, Decimal("4"))
        self.assertEqual(self.engine.current_bill.lines[0].gross_total, Decimal("400.00"))

        # Void P101
        self.engine.void_item("P101")
        self.assertEqual(len(self.engine.current_bill.lines), 1)

        bill = self.engine.checkout()
        self.assertEqual(bill.gross_total, Decimal("400.00"))

    def test_till_z_report_reconciliation(self):
        """Test Till Z-Report consolidation across bills and returns for a business date."""
        # Bill 1
        self.engine.start_bill("ZB-01", datetime(2026, 11, 15, 10, 0))
        self.engine.scan_item("P100", qty=Decimal("2"))  # 200.00 + 5% GST = 210.00
        self.engine.checkout()

        # Bill 2 on same day
        self.engine.start_bill("ZB-02", datetime(2026, 11, 15, 14, 0))
        self.engine.scan_item("P101", qty=Decimal("1"))  # 180.00 + 12% GST = 201.60
        self.engine.checkout()

        # Process return on same day from Bill 1
        ret = self.engine.process_return(
            return_id="ZR-01",
            original_bill_id="ZB-01",
            timestamp=datetime(2026, 11, 15, 16, 0),
            return_items={"P100": Decimal("1")},
        )

        zrep = self.engine.generate_z_report(date(2026, 11, 15))
        self.assertEqual(zrep.total_bills, 2)
        self.assertEqual(zrep.total_returns, 1)
        self.assertEqual(zrep.total_refunds, ret.total_refund)
        self.assertEqual(zrep.net_revenue, zrep.post_gst_sales - ret.total_refund)


if __name__ == "__main__":
    unittest.main()
