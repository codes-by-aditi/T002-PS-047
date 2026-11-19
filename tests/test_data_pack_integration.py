"""Integration checks against the supplied PS-047 sample data pack."""
import unittest
from pathlib import Path

from src.engine import POSEngine
from src.parser import (
    load_products, load_coupons_csv, load_members_csv,
    load_store_parameters_csv, load_offers_csv, parse_command_file,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


class TestSuppliedDataPack(unittest.TestCase):
    def test_full_event_stream_and_required_artifacts(self):
        engine = POSEngine(
            catalog=load_products(DATA / "products.csv"),
            coupons=load_coupons_csv(DATA / "coupons.csv"),
            members=load_members_csv(DATA / "members.csv"),
            store_parameters=load_store_parameters_csv(DATA / "store_parameters.csv"),
            offers=load_offers_csv(DATA / "offers.csv"),
        )
        events = parse_command_file(DATA / "commands.txt")
        self.assertEqual(len(events), 499)
        for event in events:
            try:
                engine.execute_event(event)
            except ValueError:
                # Invalid weighed scans are rejected and must not create a bill line.
                if event.event_type != "SCAN_WEIGHED":
                    raise
        self.assertEqual(len(engine.bills), 50)
        self.assertEqual(len(engine.returns), 10)
        self.assertEqual(len(engine.z_reports), 6)
        statuses = {r.return_id: r.status for r in engine.returns}
        self.assertEqual(statuses["RET-001"], "REJECTED")
        self.assertEqual(statuses["RET-005"], "ACCEPTED")
        self.assertEqual(statuses["RET-010"], "REJECTED")
        ret006 = next(r for r in engine.returns if r.return_id == "RET-006")
        self.assertEqual(ret006.multibuy_clawback, ret006.multibuy_clawback.__class__("60.00"))
        self.assertEqual(ret006.refund_amount, ret006.refund_amount.__class__("39.12"))


if __name__ == "__main__":
    unittest.main()
