from dataclasses import dataclass
from policies import get_policy

class User:
    ROLE = "user"
    LABEL = "User"

    def __init__(self, user_id, username, full_name, campus_id=None):
        self._id = user_id
        self._username = username
        self._full_name = full_name
        self._campus_id = campus_id

    id = property(lambda self: self._id)
    username = property(lambda self: self._username)
    full_name = property(lambda self: self._full_name)
    campus_id = property(lambda self: self._campus_id)

    def permissions(self):
        return set()

    def can(self, permission):
        return permission in self.permissions()

    def allowed_campus_ids(self, all_ids):
        return list(all_ids)

    def __str__(self):
        return f"{self._full_name} ({self.LABEL})"


class Lecturer(User):
    ROLE = "lecturer"
    LABEL = "Lecturer"

    def permissions(self):
        return {"book", "cancel_own_booking", "view_own_bookings"}


class CampusAdministrator(User):
    ROLE = "admin"
    LABEL = "Campus Administrator"

    def permissions(self):
        return {"manage_resources", "view_campus_bookings", "view_campus_reports"}

    def allowed_campus_ids(self, all_ids):
        return [self._campus_id]  # administrators are tied to one campus


class SystemOperator(User):
    ROLE = "operator"
    LABEL = "System Operator"

    def permissions(self):
        return {"view_all_bookings", "view_all_resources", "view_campus_reports", "compare_campuses"}


ROLE_CLASSES = {c.ROLE: c for c in (Lecturer, CampusAdministrator, SystemOperator)}


def user_from_row(row):
    return ROLE_CLASSES[row["role"]](row["id"], row["username"], row["full_name"], row["campus_id"])

@dataclass
class Campus:
    id: int
    name: str
    policy_key: str

    @property
    def policy(self):
        return get_policy(self.policy_key)

@dataclass
class Resource:
    id: int
    code: str
    name: str
    type: str
    campus_id: int
