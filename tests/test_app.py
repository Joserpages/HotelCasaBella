import tempfile
import unittest
from pathlib import Path

from app import ReservationSystem


class ReservationSystemTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.system = ReservationSystem(Path(self.temp_db.name))

    def test_create_and_list_reservation(self):
        reservation_id = self.system.create_reservation(
            guest_name="Ana Pérez",
            email="ana@example.com",
            room_type="Suite",
            check_in="2026-03-01",
            check_out="2026-03-05",
            guests=2,
            notes="Vista al mar",
        )

        self.assertGreater(reservation_id, 0)
        reservations = self.system.list_reservations()
        self.assertEqual(len(reservations), 1)
        self.assertEqual(reservations[0].guest_name, "Ana Pérez")

    def test_invalid_dates_raise_error(self):
        with self.assertRaises(ValueError):
            self.system.create_reservation(
                guest_name="Ana Pérez",
                email="ana@example.com",
                room_type="Suite",
                check_in="2026-03-05",
                check_out="2026-03-01",
                guests=2,
            )


if __name__ == "__main__":
    unittest.main()
