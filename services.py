from datetime import datetime, timedelta
from database import FMT, hash_password
from models import ROLE_CLASSES, Campus, Resource, user_from_row


RESOURCE_TYPES = ["Computer Laboratory", "Multimedia Projector", "Seminar Room", "Presentation Equipment"]
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


class ServiceError(Exception):
    """Any user-facing error; the GUI shows str(e) in a message box."""


class AuthError(ServiceError):
    pass

class DuplicateResourceError(ServiceError):
    pass

class BookingError(ServiceError):
    pass

# ---------------------------------------------------------------- registry
class CampusRegistry:
    def __init__(self, db):
        self.db = db
        self.reload()

    def reload(self):
        self.campuses = {r["id"]: Campus(r["id"], r["name"], r["policy_key"])
                         for r in self.db.query("SELECT * FROM campuses ORDER BY id")}               # dict
        self.resources = {cid: [] for cid in self.campuses}                                          # dict of lists
        for r in self.db.query("SELECT * FROM resources WHERE active=1 ORDER BY code"):
            self.resources[r["campus_id"]].append(
                Resource(r["id"], r["code"], r["name"], r["type"], r["campus_id"]))
        self.codes = {r["code"] for r in self.db.query("SELECT code FROM resources")}               # set

    def find_resource(self, resource_id):
        for lst in self.resources.values():
            for res in lst:
                if res.id == resource_id:
                    return res
        return None


# -------------------------------------------------------------------- auth
class AuthService:
    def __init__(self, db):
        self.db = db

    def register_lecturer(self, full_name, username, password, confirm):
        full_name, username = full_name.strip(), username.strip().lower()
        if not full_name or not username or not password:
            raise AuthError("All fields are required.")
        if len(username) < 3:
            raise AuthError("Username must be at least 3 characters.")
        if len(password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        if password != confirm:
            raise AuthError("Passwords do not match.")
        if self.db.query("SELECT 1 FROM users WHERE username=?", (username,)):
            raise AuthError("That username is already taken.")
        h, s = hash_password(password)
        self.db.execute("INSERT INTO users (username,full_name,role,password_hash,salt) VALUES (?,?,?,?,?)",
                        (username, full_name, "lecturer", h, s))

    def login(self, username, password, role=None):
        """Check credentials. If a role is given, the account must belong to that role."""
        rows = self.db.query("SELECT * FROM users WHERE username=?", (username.strip().lower(),))
        if not rows or hash_password(password, rows[0]["salt"])[0] != rows[0]["password_hash"]:
            raise AuthError("Invalid username or password.")
        user = user_from_row(rows[0])
        if role and user.ROLE != role:
            raise AuthError(f"This account is not a {ROLE_CLASSES[role].LABEL} account. "
                            f"Please choose the correct role.")
        return user


# --------------------------------------------------------------- resources
class ResourceService:
    def __init__(self, db, registry):
        self.db, self.registry = db, registry

    @staticmethod
    def _clean(code, name, rtype):
        code, name = code.strip().upper(), name.strip()
        if not code or not name:
            raise ServiceError("Resource code and name are required.")
        if rtype not in RESOURCE_TYPES:
            raise ServiceError("Please choose a valid resource type.")
        return code, name

    def add(self, campus_id, code, name, rtype):
        code, name = self._clean(code, name, rtype)
        if code in self.registry.codes:
            raise DuplicateResourceError(f"A resource with code '{code}' already exists.")
        self.db.execute("INSERT INTO resources (code,name,type,campus_id) VALUES (?,?,?,?)",
                        (code, name, rtype, campus_id))
        self.registry.reload()

    def update(self, resource_id, name, rtype):
        if not name.strip() or rtype not in RESOURCE_TYPES:
            raise ServiceError("A name and a valid type are required.")
        self.db.execute("UPDATE resources SET name=?, type=? WHERE id=?", (name.strip(), rtype, resource_id))
        self.registry.reload()

    def remove(self, resource_id):
        future = self.db.query("SELECT 1 FROM bookings WHERE resource_id=? AND status='active' AND end_time>?",
                               (resource_id, datetime.now().strftime(FMT)))
        if future:
            raise ServiceError("This resource has upcoming bookings. Cancel them before removing it.")
        # Soft delete keeps historical bookings and reports intact.
        self.db.execute("UPDATE resources SET active=0 WHERE id=?", (resource_id,))
        self.registry.reload()


# ---------------------------------------------------------------- bookings
class BookingService:
    def __init__(self, db, registry):
        self.db, self.registry = db, registry

    def _overlaps(self, resource_id, start, end):
        return bool(self.db.query(
            "SELECT 1 FROM bookings WHERE resource_id=? AND status='active' AND start_time<? AND end_time>?",
            (resource_id, end.strftime(FMT), start.strftime(FMT))))

    def create(self, user, resource_id, start, minutes, purpose=""):
        if not user.can("book"):
            raise BookingError("Your role is not allowed to create bookings.")
        if minutes <= 0:
            raise BookingError("Duration must be greater than zero.")
        res = self.registry.find_resource(resource_id)
        if res is None:
            raise BookingError("That resource is not available.")
        campus = self.registry.campuses[res.campus_id]
        end = start + timedelta(minutes=minutes)
        errors = campus.policy.validate(start, end, res.type)
        if errors:
            raise BookingError("Booking rejected by the campus policy:\n- " + "\n- ".join(errors))
        if self._overlaps(res.id, start, end):
            raise BookingError("This resource is already booked for an overlapping time.")
        self.db.execute(
            "INSERT INTO bookings (resource_id,user_id,campus_id,start_time,end_time,duration_min,purpose,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (res.id, user.id, campus.id, start.strftime(FMT), end.strftime(FMT), minutes,
             purpose.strip(), datetime.now().strftime(FMT)))

    def cancel(self, user, booking_id):
        rows = self.db.query("SELECT * FROM bookings WHERE id=?", (booking_id,))
        if not rows or rows[0]["user_id"] != user.id:
            raise BookingError("Booking not found.")
        b = rows[0]
        if b["status"] != "active":
            raise BookingError("This booking is already cancelled.")
        if b["start_time"] <= datetime.now().strftime(FMT):
            raise BookingError("Only future bookings can be cancelled.")
        self.db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))

    def list_bookings(self, user_id=None, campus_id=None):
        sql = ("SELECT b.id, c.name AS campus, r.code, r.name AS resource, u.full_name AS lecturer, "
               "b.start_time, b.end_time, b.duration_min, b.status, b.purpose "
               "FROM bookings b JOIN resources r ON r.id=b.resource_id JOIN campuses c ON c.id=b.campus_id "
               "JOIN users u ON u.id=b.user_id WHERE 1=1")
        params = []
        if user_id is not None:
            sql += " AND b.user_id=?"
            params.append(user_id)
        if campus_id is not None:
            sql += " AND b.campus_id=?"
            params.append(campus_id)
        return [dict(r, state=self.state_of(r)) for r in self.db.query(sql + " ORDER BY b.start_time DESC", params)]

    @staticmethod
    def state_of(row):
        now = datetime.now().strftime(FMT)
        if row["status"] == "cancelled":
            return "Cancelled"
        if row["end_time"] <= now:
            return "Completed"
        return "In progress" if row["start_time"] <= now else "Upcoming"

    def availability(self, campus_id, slot=None):
        """Real-time status per resource; optionally also for a (start, minutes) slot."""
        now = datetime.now().strftime(FMT)
        out = []
        for res in self.registry.resources.get(campus_id, []):
            cur = self.db.query("SELECT end_time FROM bookings WHERE resource_id=? AND status='active' "
                                "AND start_time<=? AND end_time>?", (res.id, now, now))
            info = {"resource": res, "now": f"Booked until {cur[0]['end_time'][11:]}" if cur else "Available",
                    "slot": ""}
            if slot:
                start, minutes = slot
                info["slot"] = "Taken" if self._overlaps(res.id, start, start + timedelta(minutes=minutes)) else "Free"
            out.append(info)
        return out


# ----------------------------------------------------------------- reports
class ReportService:
    def __init__(self, db, registry):
        self.db, self.registry = db, registry

    def campus_report(self, campus_id):
        s = self.db.query("SELECT COUNT(*) n, COALESCE(AVG(duration_min),0) a, COALESCE(SUM(duration_min),0) m "
                          "FROM bookings WHERE campus_id=? AND status='active'", (campus_id,))[0]
        cancelled = self.db.query("SELECT COUNT(*) n FROM bookings WHERE campus_id=? AND status='cancelled'",
                                  (campus_id,))[0]["n"]
        top = self.db.query("SELECT r.code, r.name, COUNT(*) n FROM bookings b JOIN resources r ON r.id=b.resource_id "
                            "WHERE b.campus_id=? AND b.status='active' GROUP BY r.id ORDER BY n DESC, r.code LIMIT 5",
                            (campus_id,))
        wd = {r["d"]: r["n"] for r in self.db.query(
            "SELECT CAST(strftime('%w', start_time) AS INTEGER) d, COUNT(*) n FROM bookings "
            "WHERE campus_id=? AND status='active' GROUP BY d", (campus_id,))}
        return {"total": s["n"], "avg_minutes": s["a"], "booked_hours": s["m"] / 60, "cancelled": cancelled,
                "top": [(r["code"], r["name"], r["n"]) for r in top],
                "by_weekday": [(WEEKDAYS[i], wd.get(i, 0)) for i in range(7)],
                "resource_count": len(self.registry.resources.get(campus_id, []))}

    def compare_campuses(self):
        rows = []
        for cid, campus in self.registry.campuses.items():
            rep = self.campus_report(cid)
            rows.append({"campus": campus.name, "policy": campus.policy.name, "resources": rep["resource_count"],
                         "total": rep["total"], "avg_minutes": rep["avg_minutes"],
                         "booked_hours": rep["booked_hours"], "cancelled": rep["cancelled"],
                         "per_resource": rep["total"] / rep["resource_count"] if rep["resource_count"] else 0,
                         "top": rep["top"][0][1] if rep["top"] else "-",
                         "max_minutes": campus.policy.max_minutes})
        return rows


class Services:
    def __init__(self, db):
        self.db = db
        self.registry = CampusRegistry(db)
        self.auth = AuthService(db)
        self.resources = ResourceService(db, self.registry)
        self.bookings = BookingService(db, self.registry)
        self.reports = ReportService(db, self.registry)
