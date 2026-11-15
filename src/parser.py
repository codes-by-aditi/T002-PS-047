"""
Parser for Product Master catalog (CSV/JSON) and Scan Command files.
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)
Standard Library Only.
"""

import csv
import json
from datetime import datetime, date, time
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .models import Product, ScanEvent, quantize_currency, quantize_weight


def parse_timestamp(ts_str: str, default_date: Optional[date] = None) -> datetime:
    """
    Parse a timestamp string in various standard ISO and POS formats.
    Supports:
      - 2026-11-15T20:15:00
      - 2026-11-15 20:15:00
      - 2026-11-15T20:15:00+05:30
      - 2026-11-15
      - 20:15:00 / 20:15 (attached to default_date or current date)
    """
    ts_str = ts_str.strip()
    # Try ISO format
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        pass

    # Try date only
    try:
        d = datetime.strptime(ts_str, "%Y-%m-%d").date()
        return datetime.combine(d, time.min)
    except ValueError:
        pass

    # Try time only
    for t_fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(ts_str, t_fmt).time()
            base_date = default_date if default_date else date.today()
            return datetime.combine(base_date, t)
        except ValueError:
            pass

    raise ValueError(f"Unable to parse timestamp string: {ts_str}")


def normalize_gst_rate(raw_val: Union[str, float, int, Decimal]) -> Decimal:
    """
    Normalize GST rate to slab percentage (0, 5, 12, 18).
    Handles '5%', '5', '0.05', '18.0', etc.
    """
    if isinstance(raw_val, str):
        raw_val = raw_val.strip().rstrip('%')
    d_val = Decimal(str(raw_val))
    if Decimal('0.00') < d_val <= Decimal('1.00'):
        # e.g., 0.05 -> 5.0, 0.18 -> 18.0
        d_val = d_val * Decimal('100')
    return quantize_currency(d_val)


def load_products_csv(file_path: Union[str, Path]) -> Dict[str, Product]:
    """
    Load product catalog from a CSV file.
    Expected header: barcode, name, mrp, selling_price, member_price, gst_rate, unit, category, tare_weight, offer_group
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Product catalog CSV not found: {file_path}")

    products: Dict[str, Product] = {}
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_idx, row in enumerate(reader, start=2):
            clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
            barcode = clean_row.get("barcode")
            if not barcode:
                continue

            name = clean_row.get("name", f"Item-{barcode}")
            mrp = Decimal(clean_row.get("mrp", "0.00"))
            selling_price = Decimal(clean_row.get("selling_price", str(mrp)))
            member_price = Decimal(clean_row.get("member_price") or "0.00")
            gst_rate = normalize_gst_rate(clean_row.get("gst_rate", "0"))
            unit = clean_row.get("unit", "PC").upper()
            category = clean_row.get("category", "GROCERY").upper()
            tare_weight = Decimal(clean_row.get("tare_weight") or "0.000")
            offer_group = clean_row.get("offer_group", "")

            prod = Product(
                barcode=barcode,
                name=name,
                mrp=mrp,
                selling_price=selling_price,
                member_price=member_price,
                gst_rate=gst_rate,
                unit=unit,
                category=category,
                tare_weight=tare_weight,
                offer_group=offer_group,
            )
            products[barcode] = prod

    return products


def load_products_json(file_path: Union[str, Path]) -> Dict[str, Product]:
    """
    Load product catalog from a JSON file.
    Expects a list of product objects or a dict keyed by barcode.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Product catalog JSON not found: {file_path}")

    products: Dict[str, Product] = {}
    with open(path, mode="r", encoding="utf-8") as f:
        data = json.load(f)

    items = data if isinstance(data, list) else data.values()
    for item in items:
        barcode = str(item["barcode"]).strip()
        name = str(item.get("name", f"Item-{barcode}")).strip()
        mrp = Decimal(str(item.get("mrp", "0.00")))
        selling_price = Decimal(str(item.get("selling_price", mrp)))
        member_price = Decimal(str(item.get("member_price", "0.00")))
        gst_rate = normalize_gst_rate(item.get("gst_rate", "0"))
        unit = str(item.get("unit", "PC")).strip().upper()
        category = str(item.get("category", "GROCERY")).strip().upper()
        tare_weight = Decimal(str(item.get("tare_weight", "0.000")))
        offer_group = str(item.get("offer_group", "")).strip()

        prod = Product(
            barcode=barcode,
            name=name,
            mrp=mrp,
            selling_price=selling_price,
            member_price=member_price,
            gst_rate=gst_rate,
            unit=unit,
            category=category,
            tare_weight=tare_weight,
            offer_group=offer_group,
        )
        products[barcode] = prod

    return products


def load_products(file_path: Union[str, Path]) -> Dict[str, Product]:
    """
    Automatically detect file extension and load products catalog.
    """
    p = Path(file_path)
    if p.suffix.lower() == ".json":
        return load_products_json(p)
    return load_products_csv(p)


def parse_command_line(line: str, current_bill_timestamp: Optional[datetime] = None) -> Optional[ScanEvent]:
    """
    Parse a single line of command file into a ScanEvent object.
    Ignores blank lines and comments starting with '#'.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    tokens = line.split()
    cmd = tokens[0].upper()

    if cmd == "START_BILL":
        # START_BILL <bill_id> <timestamp> [member_id]
        if len(tokens) < 3:
            raise ValueError(f"START_BILL requires at least <bill_id> and <timestamp>: {line}")
        bill_id = tokens[1]
        ts = parse_timestamp(tokens[2])
        member_id = tokens[3] if len(tokens) >= 4 else None
        return ScanEvent(
            event_type="START_BILL",
            bill_id=bill_id,
            timestamp=ts,
            member_id=member_id,
        )

    elif cmd == "SCAN":
        # SCAN <barcode> [qty] [timestamp]
        if len(tokens) < 2:
            raise ValueError(f"SCAN requires at least <barcode>: {line}")
        barcode = tokens[1]
        qty = Decimal("1")
        ts = current_bill_timestamp

        if len(tokens) >= 3:
            # Check if token 2 is a quantity or timestamp
            token2 = tokens[2]
            if "T" in token2 or ":" in token2 or "-" in token2:
                ts = parse_timestamp(token2, default_date=current_bill_timestamp.date() if current_bill_timestamp else None)
            else:
                qty = Decimal(token2)

        if len(tokens) >= 4:
            ts = parse_timestamp(tokens[3], default_date=current_bill_timestamp.date() if current_bill_timestamp else None)

        return ScanEvent(
            event_type="SCAN",
            barcode=barcode,
            qty=qty,
            timestamp=ts,
        )

    elif cmd == "WEIGH":
        # WEIGH <barcode> <gross_weight> [timestamp]
        if len(tokens) < 3:
            raise ValueError(f"WEIGH requires <barcode> and <gross_weight>: {line}")
        barcode = tokens[1]
        gross_weight = Decimal(tokens[2])
        ts = current_bill_timestamp
        if len(tokens) >= 4:
            ts = parse_timestamp(tokens[3], default_date=current_bill_timestamp.date() if current_bill_timestamp else None)

        return ScanEvent(
            event_type="WEIGH",
            barcode=barcode,
            gross_weight=gross_weight,
            timestamp=ts,
        )

    elif cmd == "OVERRIDE_QTY":
        # OVERRIDE_QTY <line_no_or_barcode> <new_qty>
        if len(tokens) < 3:
            raise ValueError(f"OVERRIDE_QTY requires <line_no_or_barcode> and <new_qty>: {line}")
        target = tokens[1]
        new_qty = Decimal(tokens[2])
        return ScanEvent(
            event_type="OVERRIDE_QTY",
            line_no_or_barcode=target,
            new_qty=new_qty,
        )

    elif cmd == "VOID":
        # VOID <line_no_or_barcode>
        if len(tokens) < 2:
            raise ValueError(f"VOID requires <line_no_or_barcode>: {line}")
        target = tokens[1]
        return ScanEvent(
            event_type="VOID",
            line_no_or_barcode=target,
        )

    elif cmd == "APPLY_COUPON":
        # APPLY_COUPON <coupon_code> <PCT|FIXED> <value>
        if len(tokens) < 4:
            raise ValueError(f"APPLY_COUPON requires <coupon_code>, <PCT|FIXED>, and <value>: {line}")
        coupon_code = tokens[1]
        coupon_type = tokens[2].upper()
        if coupon_type not in ("PCT", "FIXED"):
            raise ValueError(f"Invalid coupon type: {coupon_type}, expected PCT or FIXED")
        coupon_value = Decimal(tokens[3])
        return ScanEvent(
            event_type="APPLY_COUPON",
            coupon_code=coupon_code,
            coupon_type=coupon_type,
            coupon_value=coupon_value,
        )

    elif cmd == "REDEEM_POINTS":
        # REDEEM_POINTS <points>
        if len(tokens) < 2:
            raise ValueError(f"REDEEM_POINTS requires <points>: {line}")
        points = int(tokens[1])
        return ScanEvent(
            event_type="REDEEM_POINTS",
            points=points,
        )

    elif cmd == "CHECKOUT":
        # CHECKOUT
        return ScanEvent(event_type="CHECKOUT")

    elif cmd == "RETURN":
        # RETURN <return_id> <original_bill_id> <timestamp> <barcode:qty,...>
        if len(tokens) < 5:
            raise ValueError(f"RETURN requires <return_id> <original_bill_id> <timestamp> <barcode:qty,...>: {line}")
        return_id = tokens[1]
        orig_bill_id = tokens[2]
        ts = parse_timestamp(tokens[3])
        item_pairs = tokens[4].split(",")
        items_dict: Dict[str, Decimal] = {}
        for pair in item_pairs:
            pair = pair.strip()
            if not pair:
                continue
            if ":" not in pair:
                raise ValueError(f"Invalid return item pair format '{pair}', expected barcode:qty")
            b_code, b_qty = pair.split(":", 1)
            items_dict[b_code.strip()] = Decimal(b_qty.strip())

        return ScanEvent(
            event_type="RETURN",
            return_id=return_id,
            original_bill_id=orig_bill_id,
            timestamp=ts,
            return_items=items_dict,
        )

    elif cmd == "Z_REPORT":
        # Z_REPORT <date>
        if len(tokens) < 2:
            raise ValueError(f"Z_REPORT requires <date>: {line}")
        d = datetime.strptime(tokens[1], "%Y-%m-%d").date()
        return ScanEvent(
            event_type="Z_REPORT",
            report_date=d,
        )

    else:
        raise ValueError(f"Unrecognized POS command: '{cmd}' in line: {line}")


def parse_command_file(file_path: Union[str, Path]) -> List[ScanEvent]:
    """
    Parse an entire command file into a sequence of ScanEvent objects.
    Tracks current bill timestamp context to populate scan timestamps when omitted.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Command file not found: {file_path}")

    events: List[ScanEvent] = []
    current_bill_ts: Optional[datetime] = None

    with open(path, mode="r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                event = parse_command_line(line, current_bill_timestamp=current_bill_ts)
                if event:
                    if event.event_type == "START_BILL":
                        current_bill_ts = event.timestamp
                    elif event.event_type == "CHECKOUT":
                        current_bill_ts = None
                    events.append(event)
            except Exception as e:
                raise ValueError(f"Error on line {line_num} ('{line}'): {e}") from e

    return events
