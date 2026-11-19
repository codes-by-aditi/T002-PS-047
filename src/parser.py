"""
Parser for Product Master catalog (CSV/JSON), aux metadata (Coupons, Members, Offers, Parameters),
and Scan Command files (both pipe-delimited evaluation format and space-delimited format).
Capstone Project PS-047 (Team IDT002: Aditi Anshu & Aditi Chaudhary)
Standard Library Only.
"""

import csv
import json
from datetime import datetime, date, time
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

from .models import (
    Product,
    Coupon,
    LoyaltyAccount,
    ScanEvent,
    quantize_currency,
    quantize_weight,
)


def parse_timestamp(ts_str: str, default_date: Optional[date] = None) -> datetime:
    """
    Parse a timestamp string in standard ISO, POS, or evaluation formats (YYYY-MM-DD HH:MM:SS).
    """
    ts_str = ts_str.strip()
    
    # Try 'YYYY-MM-DD HH:MM:SS'
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts_str, fmt)
            if fmt == "%Y-%m-%d":
                return datetime.combine(dt.date(), time.min)
            return dt
        except ValueError:
            pass

    # Try ISO fromisoformat
    try:
        return datetime.fromisoformat(ts_str)
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

    raise ValueError(f"Unable to parse timestamp string: '{ts_str}'")


def normalize_gst_rate(raw_val: Union[str, float, int, Decimal]) -> Decimal:
    """
    Normalize GST rate to slab percentage (0, 5, 12, 18).
    Handles '5%', '5', '0.05', '18.0', etc.
    """
    if raw_val is None or str(raw_val).strip() == "":
        return Decimal('0')
    if isinstance(raw_val, str):
        raw_val = raw_val.strip().rstrip('%')
    d_val = Decimal(str(raw_val))
    if Decimal('0.00') < d_val <= Decimal('1.00'):
        d_val = d_val * Decimal('100')
    return quantize_currency(d_val)


def load_products_csv(file_path: Union[str, Path]) -> Dict[str, Product]:
    """
    Load product catalog from a CSV file.
    Supports:
      - Evaluation schema: sku, barcode, product_name, category, unit, mrp, selling_price, member_price, gst_rate, tare_kg, multibuy_group
      - Legacy schema: barcode, name, mrp, selling_price, member_price, gst_rate, unit, category, tare_weight, offer_group
    Indexed by barcode.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Product catalog CSV not found: {file_path}")

    products: Dict[str, Product] = {}
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
            barcode = clean_row.get("barcode")
            if not barcode:
                continue

            sku = clean_row.get("sku", "")
            name = clean_row.get("product_name") or clean_row.get("name") or f"Item-{barcode}"
            mrp = Decimal(clean_row.get("mrp") or "0.00")
            selling_price = Decimal(clean_row.get("selling_price") or str(mrp))
            member_price = Decimal(clean_row.get("member_price") or "0.00")
            gst_rate = normalize_gst_rate(clean_row.get("gst_rate", "0"))
            unit = (clean_row.get("unit") or "PIECE").upper()
            category = (clean_row.get("category") or "GROCERY").upper()
            tare_kg = Decimal(clean_row.get("tare_kg") or clean_row.get("tare_weight") or "0.000")
            offer_group = clean_row.get("multibuy_group") or clean_row.get("offer_group") or ""

            prod = Product(
                barcode=barcode,
                name=name,
                mrp=mrp,
                selling_price=selling_price,
                member_price=member_price,
                gst_rate=gst_rate,
                unit=unit,
                category=category,
                tare_weight=tare_kg,
                offer_group=offer_group,
                sku=sku,
            )
            products[barcode] = prod

    return products


def load_products_json(file_path: Union[str, Path]) -> Dict[str, Product]:
    """Load product catalog from a JSON file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Product catalog JSON not found: {file_path}")

    products: Dict[str, Product] = {}
    with open(path, mode="r", encoding="utf-8") as f:
        data = json.load(f)

    items = data if isinstance(data, list) else data.values()
    for item in items:
        barcode = str(item["barcode"]).strip()
        sku = str(item.get("sku", "")).strip()
        name = str(item.get("product_name") or item.get("name", f"Item-{barcode}")).strip()
        mrp = Decimal(str(item.get("mrp", "0.00")))
        selling_price = Decimal(str(item.get("selling_price", mrp)))
        member_price = Decimal(str(item.get("member_price", "0.00")))
        gst_rate = normalize_gst_rate(item.get("gst_rate", "0"))
        unit = str(item.get("unit", "PIECE")).strip().upper()
        category = str(item.get("category", "GROCERY")).strip().upper()
        tare_kg = Decimal(str(item.get("tare_kg") or item.get("tare_weight", "0.000")))
        offer_group = str(item.get("multibuy_group") or item.get("offer_group", "")).strip()

        prod = Product(
            barcode=barcode,
            name=name,
            mrp=mrp,
            selling_price=selling_price,
            member_price=member_price,
            gst_rate=gst_rate,
            unit=unit,
            category=category,
            tare_weight=tare_kg,
            offer_group=offer_group,
            sku=sku,
        )
        products[barcode] = prod

    return products


def load_products(file_path: Union[str, Path]) -> Dict[str, Product]:
    """Automatically detect file extension and load products catalog."""
    p = Path(file_path)
    if p.suffix.lower() == ".json":
        return load_products_json(p)
    return load_products_csv(p)


def load_coupons_csv(file_path: Union[str, Path]) -> Dict[str, Coupon]:
    """
    Load coupons from coupons.csv.
    coupon_code, coupon_type, value, max_discount, valid_from, valid_to
    """
    path = Path(file_path)
    if not path.is_file():
        return {}

    coupons: Dict[str, Coupon] = {}
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("coupon_code", "").strip()
            if not code:
                continue
            c_type = (row.get("coupon_type") or "PERCENT").strip().upper()
            # Normalize PERCENT -> PCT
            if c_type == "PERCENT":
                c_type = "PCT"
            val = Decimal(row.get("value", "0").strip())
            max_disc_str = row.get("max_discount", "").strip()
            max_disc = Decimal(max_disc_str) if max_disc_str else None

            v_from_str = row.get("valid_from", "").strip()
            v_to_str = row.get("valid_to", "").strip()
            v_from = datetime.strptime(v_from_str, "%Y-%m-%d").date() if v_from_str else None
            v_to = datetime.strptime(v_to_str, "%Y-%m-%d").date() if v_to_str else None

            coupons[code] = Coupon(
                code=code,
                coupon_type=c_type,
                value=val,
                max_discount=max_disc,
                valid_from=v_from,
                valid_to=v_to,
            )
    return coupons


def load_members_csv(file_path: Union[str, Path]) -> Dict[str, LoyaltyAccount]:
    """
    Load loyalty members from members.csv.
    member_id, member_name, mobile, join_date, opening_points
    """
    path = Path(file_path)
    if not path.is_file():
        return {}

    members: Dict[str, LoyaltyAccount] = {}
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = row.get("member_id", "").strip()
            if not mid:
                continue
            name = row.get("member_name", "").strip()
            mobile = row.get("mobile", "").strip()
            opening_pts = int(row.get("opening_points", "0").strip() or 0)
            members[mid] = LoyaltyAccount(
                member_id=mid,
                name=name,
                mobile=mobile,
                points_balance=opening_pts,
            )
    return members



def load_offers_csv(file_path: Union[str, Path]) -> Dict[str, Dict[str, Any]]:
    """Load multi-buy offer definitions keyed by offer_group."""
    path = Path(file_path)
    if not path.is_file():
        return {}
    offers: Dict[str, Dict[str, Any]] = {}
    with path.open(mode="r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            group = (row.get("offer_group") or "").strip()
            if not group:
                continue
            offers[group] = {
                "description": (row.get("description") or "").strip(),
                "buy_qty": int(row.get("buy_qty") or 2),
                "free_qty": int(row.get("free_qty") or 1),
                "max_free_per_bill": int(row.get("max_free_per_bill") or 3),
                "valid_from": date.fromisoformat(row["valid_from"]) if row.get("valid_from") else None,
                "valid_to": date.fromisoformat(row["valid_to"]) if row.get("valid_to") else None,
            }
    return offers

def load_store_parameters_csv(file_path: Union[str, Path]) -> Dict[str, str]:
    """Load key-value settings from store_parameters.csv."""
    path = Path(file_path)
    if not path.is_file():
        return {}

    params: Dict[str, str] = {}
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            p = row.get("param", "").strip()
            v = row.get("value", "").strip()
            if p:
                params[p] = v
    return params


def parse_command_line(line: str, current_bill_timestamp: Optional[datetime] = None) -> Optional[ScanEvent]:
    """
    Parse a single line of command file into a ScanEvent object.
    Supports BOTH pipe-delimited format (Evaluation pack) AND space-delimited format (Legacy).
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Detect pipe delimiter
    if "|" in line:
        parts = [p.strip() for p in line.split("|")]
        cmd = parts[0].upper()

        if cmd == "OPEN_BILL":
            # OPEN_BILL|timestamp|bill_id|till_id|member_id
            ts = parse_timestamp(parts[1])
            bill_id = parts[2]
            till_id = parts[3] if len(parts) > 3 and parts[3] else "TILL-01"
            member_id = parts[4] if len(parts) > 4 and parts[4] else None
            return ScanEvent(
                event_type="OPEN_BILL",
                timestamp=ts,
                bill_id=bill_id,
                till_id=till_id,
                member_id=member_id,
            )

        elif cmd == "SCAN":
            # SCAN|timestamp|bill_id|barcode|qty
            ts = parse_timestamp(parts[1])
            bill_id = parts[2]
            barcode = parts[3]
            qty = Decimal(parts[4]) if len(parts) > 4 and parts[4] else Decimal("1")
            return ScanEvent(
                event_type="SCAN",
                timestamp=ts,
                bill_id=bill_id,
                barcode=barcode,
                qty=qty,
            )

        elif cmd == "SCAN_WEIGHED":
            # SCAN_WEIGHED|timestamp|bill_id|barcode|gross_kg
            ts = parse_timestamp(parts[1])
            bill_id = parts[2]
            barcode = parts[3]
            gross_weight = Decimal(parts[4])
            return ScanEvent(
                event_type="SCAN_WEIGHED",
                timestamp=ts,
                bill_id=bill_id,
                barcode=barcode,
                gross_weight=gross_weight,
            )

        elif cmd == "QTY_OVERRIDE":
            # QTY_OVERRIDE|timestamp|bill_id|line_no|new_qty
            ts = parse_timestamp(parts[1])
            bill_id = parts[2]
            line_no = int(parts[3])
            new_qty = Decimal(parts[4])
            return ScanEvent(
                event_type="QTY_OVERRIDE",
                timestamp=ts,
                bill_id=bill_id,
                line_no=line_no,
                line_no_or_barcode=str(line_no),
                new_qty=new_qty,
            )

        elif cmd == "VOID":
            # VOID|timestamp|bill_id|line_no
            ts = parse_timestamp(parts[1])
            bill_id = parts[2]
            line_no = int(parts[3])
            return ScanEvent(
                event_type="VOID",
                timestamp=ts,
                bill_id=bill_id,
                line_no=line_no,
                line_no_or_barcode=str(line_no),
            )

        elif cmd == "APPLY_COUPON":
            # APPLY_COUPON|timestamp|bill_id|coupon_code
            ts = parse_timestamp(parts[1])
            bill_id = parts[2]
            coupon_code = parts[3]
            return ScanEvent(
                event_type="APPLY_COUPON",
                timestamp=ts,
                bill_id=bill_id,
                coupon_code=coupon_code,
            )

        elif cmd == "REDEEM_POINTS":
            # REDEEM_POINTS|timestamp|bill_id|points
            ts = parse_timestamp(parts[1])
            bill_id = parts[2]
            points = int(parts[3])
            return ScanEvent(
                event_type="REDEEM_POINTS",
                timestamp=ts,
                bill_id=bill_id,
                points=points,
            )

        elif cmd == "CLOSE_BILL":
            # CLOSE_BILL|timestamp|bill_id|payment_mode
            ts = parse_timestamp(parts[1])
            bill_id = parts[2]
            payment_mode = parts[3].upper() if len(parts) > 3 and parts[3] else "CASH"
            return ScanEvent(
                event_type="CLOSE_BILL",
                timestamp=ts,
                bill_id=bill_id,
                payment_mode=payment_mode,
            )

        elif cmd == "RETURN":
            # RETURN|timestamp|return_id|till_id|original_bill_id|barcode|qty
            ts = parse_timestamp(parts[1])
            return_id = parts[2]
            till_id = parts[3]
            original_bill_id = parts[4]
            barcode = parts[5]
            qty = Decimal(parts[6]) if len(parts) > 6 else Decimal("1")
            return ScanEvent(
                event_type="RETURN",
                timestamp=ts,
                return_id=return_id,
                till_id=till_id,
                original_bill_id=original_bill_id,
                barcode=barcode,
                qty=qty,
                return_items={barcode: qty},
            )

        elif cmd == "Z_REPORT":
            # Z_REPORT|timestamp|till_id|business_date
            ts = parse_timestamp(parts[1])
            till_id = parts[2]
            b_date = datetime.strptime(parts[3], "%Y-%m-%d").date()
            return ScanEvent(
                event_type="Z_REPORT",
                timestamp=ts,
                till_id=till_id,
                report_date=b_date,
            )

        else:
            raise ValueError(f"Unrecognized pipe POS command '{cmd}' in line: {line}")

    # Fallback to space-delimited legacy format
    tokens = line.split()
    cmd = tokens[0].upper()

    if cmd in ("START_BILL", "OPEN_BILL"):
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
        if len(tokens) < 2:
            raise ValueError(f"SCAN requires at least <barcode>: {line}")
        barcode = tokens[1]
        qty = Decimal("1")
        ts = current_bill_timestamp

        if len(tokens) >= 3:
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

    elif cmd in ("WEIGH", "SCAN_WEIGHED"):
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

    elif cmd in ("OVERRIDE_QTY", "QTY_OVERRIDE"):
        if len(tokens) < 3:
            raise ValueError(f"OVERRIDE_QTY requires <line_no_or_barcode> and <new_qty>: {line}")
        target = tokens[1]
        new_qty = Decimal(tokens[2])
        line_no = int(target) if target.isdigit() else None
        return ScanEvent(
            event_type="OVERRIDE_QTY",
            line_no_or_barcode=target,
            line_no=line_no,
            new_qty=new_qty,
        )

    elif cmd == "VOID":
        if len(tokens) < 2:
            raise ValueError(f"VOID requires <line_no_or_barcode>: {line}")
        target = tokens[1]
        line_no = int(target) if target.isdigit() else None
        return ScanEvent(
            event_type="VOID",
            line_no_or_barcode=target,
            line_no=line_no,
        )

    elif cmd == "APPLY_COUPON":
        if len(tokens) == 2:
            return ScanEvent(
                event_type="APPLY_COUPON",
                coupon_code=tokens[1],
            )
        elif len(tokens) >= 4:
            coupon_code = tokens[1]
            coupon_type = tokens[2].upper()
            coupon_value = Decimal(tokens[3])
            return ScanEvent(
                event_type="APPLY_COUPON",
                coupon_code=coupon_code,
                coupon_type=coupon_type,
                coupon_value=coupon_value,
            )
        else:
            raise ValueError(f"Invalid APPLY_COUPON syntax: {line}")

    elif cmd == "REDEEM_POINTS":
        if len(tokens) < 2:
            raise ValueError(f"REDEEM_POINTS requires <points>: {line}")
        points = int(tokens[1])
        return ScanEvent(
            event_type="REDEEM_POINTS",
            points=points,
        )

    elif cmd in ("CHECKOUT", "CLOSE_BILL"):
        payment_mode = tokens[1].upper() if len(tokens) >= 2 else "CASH"
        return ScanEvent(event_type="CHECKOUT", payment_mode=payment_mode)

    elif cmd == "RETURN":
        if len(tokens) < 5:
            raise ValueError(f"RETURN requires <return_id> <original_bill_id> <timestamp> <barcode:qty,...>: {line}")
        return_id = tokens[1]
        orig_bill_id = tokens[2]
        ts = parse_timestamp(tokens[3])
        item_pairs = tokens[4].split(",")
        items_dict: Dict[str, Decimal] = {}
        first_bcode = ""
        first_qty = Decimal('1')
        for pair in item_pairs:
            pair = pair.strip()
            if not pair:
                continue
            if ":" in pair:
                b_code, b_qty = pair.split(":", 1)
                items_dict[b_code.strip()] = Decimal(b_qty.strip())
                if not first_bcode:
                    first_bcode = b_code.strip()
                    first_qty = Decimal(b_qty.strip())
            else:
                items_dict[pair] = Decimal('1')
                if not first_bcode:
                    first_bcode = pair

        return ScanEvent(
            event_type="RETURN",
            return_id=return_id,
            original_bill_id=orig_bill_id,
            timestamp=ts,
            return_items=items_dict,
            barcode=first_bcode,
            qty=first_qty,
        )

    elif cmd == "Z_REPORT":
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
    """Parse an entire command file into a list of ScanEvent objects."""
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
                    if event.event_type in ("START_BILL", "OPEN_BILL"):
                        current_bill_ts = event.timestamp
                    elif event.event_type in ("CHECKOUT", "CLOSE_BILL"):
                        current_bill_ts = None
                    events.append(event)
            except Exception as e:
                raise ValueError(f"Error on line {line_num} ('{line}'): {e}") from e

    return events
