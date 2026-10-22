"""database.py - SQLite persistence layer.

Creates the schema, seeds the campuses/accounts on first run and hashes passwords.
No business rules live here (see services.py and policies.py).
"""
import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus_booking.db")
FMT = "%Y-%m-%d %H:%M"  # ISO-like format: strings sort chronologically

SCHEMA = """
CREATE TABLE IF NOT EXISTS campuses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    policy_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('lecturer','admin','operator')),
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    campus_id     INTEGER REFERENCES campuses(id)
);
CREATE TABLE IF NOT EXISTS resources (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    code      TEXT NOT NULL UNIQUE,              -- unique identifier, blocks duplicates
    name      TEXT NOT NULL,
    type      TEXT NOT NULL,
    campus_id INTEGER NOT NULL REFERENCES campuses(id),
    active    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS bookings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id  INTEGER NOT NULL REFERENCES resources(id),
    user_id      INTEGER NOT NULL REFERENCES users(id),
    campus_id    INTEGER NOT NULL REFERENCES campuses(id),
    start_time   TEXT NOT NULL,
    end_time     TEXT NOT NULL,
    duration_min INTEGER NOT NULL,
    purpose      TEXT,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled')),
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_booking_resource ON bookings(resource_id, start_time, end_time);
"""


def hash_password(password, salt=None):
    """Salted PBKDF2 hash. Returns (hash_hex, salt_hex)."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return digest.hex(), salt


class Database:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._seed_if_empty()

    def execute(self, sql, params=()):
        """Run a write statement inside a transaction; returns the cursor."""
        with self.conn:
            return self.conn.execute(sql, params)

    def query(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------------ seed
    # (campus name, policy key, resource code prefix, admin username, admin display name)
    CAMPUS_SEED = [("Johannesburg", "standard", "JHB", "admin_jhb", "Johannesburg Admin"),
                   ("Durban", "strict", "DBN", "admin_dbn", "Durban Admin"),
                   ("Cape Town", "flexible", "CPT", "admin_cpt", "Cape Town Admin")]
    RESOURCE_TEMPLATE = [("LAB-01", "Computer Lab 1", "Computer Laboratory"),
                         ("LAB-02", "Computer Lab 2", "Computer Laboratory"),
                         ("PRJ-01", "Multimedia Projector A", "Multimedia Projector"),
                         ("SEM-01", "Seminar Room 1", "Seminar Room"),
                         ("PRS-01", "Presentation Kit A", "Presentation Equipment")]

    def _add_user(self, username, full, role, pw, campus=None):
        h, s = hash_password(pw)
        self.execute("INSERT INTO users (username,full_name,role,password_hash,salt,campus_id) "
                     "VALUES (?,?,?,?,?,?)", (username, full, role, h, s, campus))

    def _seed_if_empty(self):
        """Create any missing campus (with resources and an admin). Safe to run on every start-up,
        so campuses added later appear in an existing database too."""
        first_run = not self.query("SELECT 1 FROM users LIMIT 1")
        for name, policy, prefix, admin_user, admin_name in self.CAMPUS_SEED:
            if self.query("SELECT 1 FROM campuses WHERE name=?", (name,)):
                continue
            cur = self.execute("INSERT INTO campuses (name, policy_key) VALUES (?,?)", (name, policy))
            campus_id = cur.lastrowid
            for code, rname, rtype in self.RESOURCE_TEMPLATE:
                self.execute("INSERT INTO resources (code,name,type,campus_id) VALUES (?,?,?,?)",
                             (f"{prefix}-{code}", rname, rtype, campus_id))
            if not self.query("SELECT 1 FROM users WHERE username=?", (admin_user,)):
                self._add_user(admin_user, admin_name, "admin", "admin123", campus_id)
        if first_run:
            self._add_user("operator", "System Operator", "operator", "operator123")
            self._add_user("lecturer1", "Demo Lecturer", "lecturer", "lecturer123")
            cid = {r["name"]: r["id"] for r in self.query("SELECT id, name FROM campuses")}
            self._seed_demo_bookings(cid)

    def _seed_demo_bookings(self, cid):
        """A few past bookings so the reports have something to show on first run."""
        uid = self.query("SELECT id FROM users WHERE username='lecturer1'")[0]["id"]
        day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        n = 0
        for back in range(1, 15):
            d = day - timedelta(days=back)
            if d.weekday() >= 5:
                continue
            for campus, hour, mins in (("Johannesburg", 9, 120), ("Durban", 10, 60), ("Cape Town", 8, 180)):
                if (back + hour) % 3 == 0:
                    continue
                res = self.query("SELECT id FROM resources WHERE campus_id=? ORDER BY id LIMIT 1 OFFSET ?",
                                 (cid[campus], n % 5))
                n += 1
                start = d.replace(hour=hour)
                end = start + timedelta(minutes=mins)
                self.execute(
                    "INSERT INTO bookings (resource_id,user_id,campus_id,start_time,end_time,duration_min,"
                    "purpose,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (res[0]["id"], uid, cid[campus], start.strftime(FMT), end.strftime(FMT), mins,
                     "Demo lecture", datetime.now().strftime(FMT)))
