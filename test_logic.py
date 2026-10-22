import os, tempfile, unittest
from datetime import datetime, timedelta
from database import Database
from services import Services, ServiceError, DuplicateResourceError, BookingError, AuthError


def next_weekday_at(hour, days_ahead=1):
    d = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


class Tests(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mktemp(suffix=".db")
        self.s = Services(Database(self.path))
        self.lect = self.s.auth.login("lecturer1", "lecturer123")
        self.cid = {c.name: c.id for c in self.s.registry.campuses.values()}

    def tearDown(self):
        self.s.db.conn.close(); os.remove(self.path)

    def res(self, campus, n=0):
        return self.s.registry.resources[self.cid[campus]][n]

    def test_auth(self):
        with self.assertRaises(AuthError): self.s.auth.login("lecturer1", "wrong")
        self.s.auth.register_lecturer("New Person", "newp", "secret1", "secret1")
        self.assertEqual(self.s.auth.login("newp", "secret1").ROLE, "lecturer")
        with self.assertRaises(AuthError): self.s.auth.register_lecturer("X", "newp", "secret1", "secret1")
        self.assertEqual(self.s.auth.login("admin_dbn", "admin123").campus_id, self.cid["Durban"])

    def test_booking_and_overlap(self):
        r, start = self.res("Johannesburg"), next_weekday_at(10)
        self.s.bookings.create(self.lect, r.id, start, 60)
        with self.assertRaises(BookingError): self.s.bookings.create(self.lect, r.id, start + timedelta(minutes=30), 60)
        self.s.bookings.create(self.lect, r.id, start + timedelta(minutes=60), 60)  # back-to-back is fine

    def test_policies_differ(self):
        start = next_weekday_at(10)
        jhb, dbn = self.res("Johannesburg"), self.res("Durban")
        self.s.bookings.create(self.lect, jhb.id, start, 180)
        with self.assertRaises(BookingError): self.s.bookings.create(self.lect, dbn.id, start, 180)   # >120
        with self.assertRaises(BookingError): self.s.bookings.create(self.lect, dbn.id, start, 120)   # lab cap 90
        with self.assertRaises(BookingError): self.s.bookings.create(self.lect, jhb.id, start.replace(hour=5), 60)
        sat = start + timedelta(days=(5 - start.weekday()) % 7 or 7)
        with self.assertRaises(BookingError): self.s.bookings.create(self.lect, dbn.id, sat, 60)
        with self.assertRaises(BookingError): self.s.bookings.create(self.lect, jhb.id, datetime.now() - timedelta(days=1), 60)

    def test_duplicate_resource(self):
        self.s.resources.add(self.cid["Durban"], "dbn-x-1", "Extra Room", "Seminar Room")
        with self.assertRaises(DuplicateResourceError):
            self.s.resources.add(self.cid["Cape Town"], "DBN-X-1", "Other", "Seminar Room")

    def test_cancel_and_remove(self):
        r, start = self.res("Cape Town", 1), next_weekday_at(9, 2)
        self.s.bookings.create(self.lect, r.id, start, 60)
        with self.assertRaises(ServiceError): self.s.resources.remove(r.id)
        bid = self.s.bookings.list_bookings(user_id=self.lect.id)[0]["id"]
        self.s.bookings.cancel(self.lect, bid)
        self.assertEqual(self.s.bookings.list_bookings(user_id=self.lect.id)[0]["state"], "Cancelled")
        self.s.resources.remove(r.id)
        self.assertNotIn(r.id, [x.id for x in self.s.registry.resources[self.cid["Cape Town"]]])

    def test_availability_and_reports(self):
        r, start = self.res("Johannesburg", 2), next_weekday_at(14)
        self.s.bookings.create(self.lect, r.id, start, 60)
        info = self.s.bookings.availability(self.cid["Johannesburg"], (start, 30))
        self.assertEqual({i["resource"].id: i["slot"] for i in info}[r.id], "Taken")
        rows = self.s.reports.compare_campuses()
        self.assertEqual(len(rows), 3)
        self.assertGreater(rows[0]["total"], 0)
        rep = self.s.reports.campus_report(self.cid["Durban"])
        self.assertEqual(len(rep["by_weekday"]), 7)

    def test_persistence(self):
        self.s.auth.register_lecturer("Keep Me", "keepme", "secret1", "secret1")
        s2 = Services(Database(self.path))
        self.assertEqual(s2.auth.login("keepme", "secret1").full_name, "Keep Me")

    def test_permissions(self):
        op = self.s.auth.login("operator", "operator123")
        self.assertFalse(op.can("book")); self.assertTrue(op.can("compare_campuses"))
        with self.assertRaises(BookingError): self.s.bookings.create(op, self.res("Johannesburg").id, next_weekday_at(10), 60)

if __name__ == "__main__":
    unittest.main(verbosity=1)
