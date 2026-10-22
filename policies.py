from datetime import datetime, timedelta

class BookingPolicy:
    key = "base"
    name = "Base"
    max_minutes = 180
    open_hour = 8
    close_hour = 18
    weekdays_only = False
    max_advance_days = 30
    type_caps = {}

    def cap_for(self, resource_type):
        return self.type_caps.get(resource_type, self.max_minutes)

    def describe(self):
        days = "Mon-Fri only" if self.weekdays_only else "any day"
        text = (f"{self.name} policy: max {self.max_minutes // 60}h {self.max_minutes % 60:02d}m per session; "
                f"{self.open_hour:02d}:00-{self.close_hour:02d}:00; {days}; "
                f"book up to {self.max_advance_days} days ahead")
        for rtype, cap in self.type_caps.items():
            text += f"; {rtype} capped at {cap} min"
        return text

    def validate(self, start, end, resource_type, now=None):
        """Return a list of rule violations (empty list = booking allowed)."""
        now = now or datetime.now()
        errors = []
        minutes = int((end - start).total_seconds() // 60)
        if start < now:
            errors.append("Bookings cannot start in the past.")
        if end.date() != start.date():
            errors.append("A booking must finish on the day it starts.")
        if minutes > self.cap_for(resource_type):
            errors.append(f"Maximum duration for a {resource_type} is {self.cap_for(resource_type)} minutes "
                          f"on this campus.")
        if start.hour < self.open_hour or (end.date() == start.date() and
                                           (end.hour, end.minute) > (self.close_hour, 0)):
            errors.append(f"Bookings are only allowed between {self.open_hour:02d}:00 and "
                          f"{self.close_hour:02d}:00.")
        if self.weekdays_only and start.weekday() >= 5:
            errors.append("This campus only accepts bookings on weekdays.")
        if start > now + timedelta(days=self.max_advance_days):
            errors.append(f"Bookings may only be made up to {self.max_advance_days} days in advance.")
        return errors

class StandardPolicy(BookingPolicy):
    key, name = "standard", "Standard"

class StrictPolicy(BookingPolicy):
    key, name = "strict", "Strict"
    max_minutes = 120
    close_hour = 16
    weekdays_only = True
    max_advance_days = 14
    type_caps = {"Computer Laboratory": 90}   # labs are shared: priority to more classes

class FlexiblePolicy(BookingPolicy):
    key, name = "flexible", "Flexible"
    max_minutes = 240
    open_hour = 7
    close_hour = 20
    max_advance_days = 60

POLICY_REGISTRY = {p.key: p for p in (StandardPolicy(), StrictPolicy(), FlexiblePolicy())}

def get_policy(key):
    return POLICY_REGISTRY.get(key, POLICY_REGISTRY["standard"])
