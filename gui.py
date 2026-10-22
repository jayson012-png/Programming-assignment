
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from services import RESOURCE_TYPES, ServiceError

DATE_FMT = "%Y-%m-%d"
TIMES = [f"{h:02d}:{m:02d}" for h in range(6, 21) for m in (0, 30)]
DURATIONS = [str(m) for m in range(30, 241, 30)]

# ------------------------------------------------------------------ helpers
def make_tree(parent, columns, widths, height=10):
    """Treeview with a vertical scrollbar. Returns (container_frame, tree)."""
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
    for col, w in zip(columns, widths):
        tree.heading(col, text=col)
        tree.column(col, width=w, anchor="w")
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tree.tag_configure("bad", foreground="#b00020")
    tree.tag_configure("good", foreground="#1b7a3d")
    return frame, tree


def fill_tree(tree, rows):
    """rows: list of (iid, values, tag)."""
    tree.delete(*tree.get_children())
    for iid, values, tag in rows:
        tree.insert("", "end", iid=str(iid), values=values, tags=(tag,) if tag else ())


def draw_bars(canvas, data, title):
    """Minimal bar chart on a Canvas. data = [(label, value), ...]."""
    canvas.update_idletasks()
    w, h = max(canvas.winfo_width(), 300), max(canvas.winfo_height(), 180)
    canvas.delete("all")
    canvas.create_text(w / 2, 12, text=title, font=("Segoe UI", 10, "bold"))
    if not data:
        canvas.create_text(w / 2, h / 2, text="No data yet")
        return
    top = max(v for _, v in data) or 1
    slot = (w - 40) / len(data)
    for i, (label, value) in enumerate(data):
        x0 = 20 + i * slot + slot * 0.15
        x1 = 20 + (i + 1) * slot - slot * 0.15
        bar_h = (h - 70) * value / top
        canvas.create_rectangle(x0, h - 35 - bar_h, x1, h - 35, fill="#3b6fb6", outline="")
        canvas.create_text((x0 + x1) / 2, h - 35 - bar_h - 8, text=f"{value:g}", font=("Segoe UI", 8))
        canvas.create_text((x0 + x1) / 2, h - 20, text=label[:12], font=("Segoe UI", 8))


def fmt_minutes(m):
    return f"{int(m // 60)}h {int(m % 60):02d}m"


# ------------------------------------------------------------------- login
class LoginFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=30)
        self.app = app
        ttk.Label(self, text="Smart Campus Resource Booking System", font=("Segoe UI", 18, "bold")).pack(pady=(10, 2))
        ttk.Label(self, text="Richfield Graduate Institution").pack(pady=(0, 15))
        nb = ttk.Notebook(self)
        nb.pack()
        login, reg = ttk.Frame(nb, padding=20), ttk.Frame(nb, padding=20)
        nb.add(login, text="Log in")
        nb.add(reg, text="Register (Lecturer)")

        # Role options: the person chooses how they are logging in
        self.role = tk.StringVar(value="lecturer")
        ttk.Label(login, text="Log in as").grid(row=0, column=0, sticky="ne", pady=5, padx=5)
        roles = ttk.Frame(login)
        roles.grid(row=0, column=1, sticky="w", pady=5)
        for value, text in (("lecturer", "Lecturer"), ("admin", "Administrator"),
                            ("operator", "System Operator")):
            ttk.Radiobutton(roles, text=text, value=value, variable=self.role).pack(anchor="w")

        self.user, self.pw = tk.StringVar(), tk.StringVar()
        for r, (lbl, var, show) in enumerate((("Username", self.user, ""), ("Password", self.pw, "*")), start=1):
            ttk.Label(login, text=lbl).grid(row=r, column=0, sticky="e", pady=5, padx=5)
            e = ttk.Entry(login, textvariable=var, show=show, width=28)
            e.grid(row=r, column=1, pady=5)
            e.bind("<Return>", lambda _e: self.do_login())
        ttk.Button(login, text="Log in", command=self.do_login).grid(row=3, column=1, sticky="e", pady=10)

        self.rvars = [tk.StringVar() for _ in range(4)]
        for r, (lbl, var) in enumerate(zip(("Full name", "Username", "Password", "Confirm password"), self.rvars)):
            ttk.Label(reg, text=lbl).grid(row=r, column=0, sticky="e", pady=5, padx=5)
            ttk.Entry(reg, textvariable=var, show="*" if "ass" in lbl else "", width=28).grid(row=r, column=1)
        ttk.Button(reg, text="Create account", command=self.do_register).grid(row=4, column=1, sticky="e", pady=10)

    def do_login(self):
        try:
            self.app.user = self.app.svc.auth.login(self.user.get(), self.pw.get(), self.role.get())
        except ServiceError as e:
            messagebox.showerror("Login failed", str(e))
            return
        self.app.show_campus_select()

    def do_register(self):
        try:
            self.app.svc.auth.register_lecturer(*[v.get() for v in self.rvars])
        except ServiceError as e:
            messagebox.showerror("Registration failed", str(e))
            return
        messagebox.showinfo("Registered", "Account created. You can now log in.")
        self.user.set(self.rvars[1].get().strip().lower())
        for v in self.rvars:
            v.set("")


# ----------------------------------------------------------- campus select
class CampusFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=30)
        self.app = app
        reg = app.svc.registry
        self.ids = app.user.allowed_campus_ids(reg.campuses.keys())
        ttk.Label(self, text=f"Welcome, {app.user}", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self, text="Select the campus you want to work with:").pack(anchor="w", pady=(15, 5))
        self.lb = tk.Listbox(self, height=6, font=("Segoe UI", 12), exportselection=False)
        for cid in self.ids:
            self.lb.insert("end", reg.campuses[cid].name)
        self.lb.pack(anchor="w", fill="x")
        self.lb.bind("<<ListboxSelect>>", self.show_policy)
        self.policy = ttk.Label(self, wraplength=600, foreground="#444", justify="left")
        self.policy.pack(anchor="w", pady=10)
        row = ttk.Frame(self)
        row.pack(anchor="w")
        ttk.Button(row, text="Continue", command=self.go).pack(side="left")
        ttk.Button(row, text="Log out", command=app.logout).pack(side="left", padx=8)
        self.lb.selection_set(0)
        self.show_policy()

    def selected(self):
        sel = self.lb.curselection()
        return self.app.svc.registry.campuses[self.ids[sel[0]]] if sel else None

    def show_policy(self, _e=None):
        c = self.selected()
        self.policy.config(text=c.policy.describe() if c else "")

    def go(self):
        campus = self.selected()
        if campus:
            self.app.campus = campus
            self.app.show_dashboard()


# --------------------------------------------------------------- dashboard
class Dashboard(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        user, campus = app.user, app.campus
        head = tk.Frame(self, bg="#1f3b63", padx=12, pady=8)
        head.pack(fill="x")
        tk.Label(head, text=f"{user}", bg="#1f3b63", fg="white", font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(head, text=f"   |   Active campus: {campus.name}", bg="#1f3b63", fg="#ffd966",
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(head, text="Log out", command=app.logout).pack(side="right")
        if len(user.allowed_campus_ids(app.svc.registry.campuses.keys())) > 1:
            ttk.Button(head, text="Switch campus", command=app.show_campus_select).pack(side="right", padx=6)
        tk.Label(self, text="Policy in effect: " + campus.policy.describe(), bg="#eaf1fb", anchor="w",
                 wraplength=1000, justify="left", padx=12, pady=4).pack(fill="x")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs = []
        if user.can("book"):
            self.add_tab(BookTab, "Resources & Booking")
            self.add_tab(MyBookingsTab, "My Bookings")
        if user.can("manage_resources"):
            self.add_tab(AdminResourcesTab, "Manage Resources")
        if user.can("view_campus_bookings"):
            self.add_tab(BookingsTab, "Campus Bookings", all_campuses=False)
        if user.can("view_all_bookings"):
            self.add_tab(BookingsTab, "All Bookings", all_campuses=True)
        if user.can("view_all_resources"):
            self.add_tab(AllResourcesTab, "All Resources")
        if user.can("view_campus_reports"):
            self.add_tab(ReportTab, "Campus Report & Usage")
        if user.can("compare_campuses"):
            self.add_tab(ComparisonTab, "Cross-Campus Comparison")
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self.refresh_current())
        self.refresh_current()

    def add_tab(self, cls, title, **kw):
        tab = cls(self.nb, self.app, **kw)
        self.nb.add(tab, text=title)
        self.tabs.append(tab)

    def refresh_current(self):
        idx = self.nb.index(self.nb.select())
        self.tabs[idx].refresh()


# ----------------------------------------------------------- lecturer tabs
class BookTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        left = ttk.LabelFrame(self, text="Resources on this campus (real-time availability)", padding=6)
        left.pack(side="left", fill="both", expand=True)
        frame, self.tree = make_tree(left, ("Code", "Resource", "Type", "Status now", "Selected slot"),
                                     (120, 160, 150, 130, 100))
        frame.pack(fill="both", expand=True)

        form = ttk.LabelFrame(self, text="New booking", padding=10)
        form.pack(side="right", fill="y", padx=(8, 0))
        self.date = tk.StringVar(value=datetime.now().strftime(DATE_FMT))
        self.start, self.dur, self.purpose = tk.StringVar(value="09:00"), tk.StringVar(value="60"), tk.StringVar()
        rows = (("Date (YYYY-MM-DD)", ttk.Entry(form, textvariable=self.date, width=18)),
                ("Start time", ttk.Combobox(form, textvariable=self.start, values=TIMES, width=15, state="readonly")),
                ("Duration (min)", ttk.Combobox(form, textvariable=self.dur, values=DURATIONS, width=15)),
                ("Purpose", ttk.Entry(form, textvariable=self.purpose, width=18)))
        for r, (lbl, widget) in enumerate(rows):
            ttk.Label(form, text=lbl).grid(row=r, column=0, sticky="w", pady=4)
            widget.grid(row=r, column=1, pady=4, padx=4)
        ttk.Button(form, text="Check availability", command=self.refresh).grid(row=4, column=0, columnspan=2,
                                                                               sticky="ew", pady=(10, 2))
        ttk.Button(form, text="Book selected resource", command=self.book).grid(row=5, column=0, columnspan=2,
                                                                                sticky="ew")
        ttk.Label(form, text="Select a resource in the list,\nthen choose date, time and duration.",
                  foreground="#555").grid(row=6, column=0, columnspan=2, pady=8)

    def parse_slot(self):
        try:
            start = datetime.strptime(f"{self.date.get().strip()} {self.start.get()}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise ServiceError("Enter the date as YYYY-MM-DD (e.g. 2026-11-03).")
        try:
            minutes = int(self.dur.get())
        except ValueError:
            raise ServiceError("Duration must be a whole number of minutes.")
        return start, minutes

    def refresh(self):
        try:
            slot = self.parse_slot()
        except ServiceError:
            slot = None
        rows = []
        for info in self.app.svc.bookings.availability(self.app.campus.id, slot):
            r = info["resource"]
            tag = "bad" if info["slot"] == "Taken" or info["now"] != "Available" else "good"
            rows.append((r.id, (r.code, r.name, r.type, info["now"], info["slot"] or "-"), tag))
        sel = self.tree.selection()
        fill_tree(self.tree, rows)
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])

    def book(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No resource", "Please select a resource first.")
            return
        try:
            start, minutes = self.parse_slot()
            self.app.svc.bookings.create(self.app.user, int(sel[0]), start, minutes, self.purpose.get())
        except ServiceError as e:
            messagebox.showerror("Booking not made", str(e))
            return
        messagebox.showinfo("Booked", f"Booking confirmed for {start:%Y-%m-%d %H:%M} ({minutes} min).")
        self.purpose.set("")
        self.refresh()


class MyBookingsTab(ttk.Frame):
    COLS = ("ID", "Campus", "Resource", "Start", "End", "Mins", "Status")
    WIDTHS = (40, 100, 200, 130, 130, 50, 90)

    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        top = ttk.LabelFrame(self, text="Active bookings (current and upcoming)", padding=6)
        top.pack(fill="both", expand=True)
        f1, self.active = make_tree(top, self.COLS, self.WIDTHS, height=6)
        f1.pack(fill="both", expand=True)
        ttk.Button(top, text="Cancel selected (future only)", command=self.cancel).pack(anchor="e", pady=4)
        bottom = ttk.LabelFrame(self, text="Booking history (past and cancelled)", padding=6)
        bottom.pack(fill="both", expand=True, pady=(8, 0))
        f2, self.history = make_tree(bottom, self.COLS, self.WIDTHS, height=6)
        f2.pack(fill="both", expand=True)

    def refresh(self):
        rows = self.app.svc.bookings.list_bookings(user_id=self.app.user.id)
        make = lambda b: (b["id"], (b["id"], b["campus"], f"{b['code']} - {b['resource']}", b["start_time"],
                                    b["end_time"], b["duration_min"], b["state"]), None)
        fill_tree(self.active, [make(b) for b in reversed(rows) if b["state"] in ("Upcoming", "In progress")])
        fill_tree(self.history, [make(b) for b in rows if b["state"] in ("Completed", "Cancelled")])

    def cancel(self):
        sel = self.active.selection()
        if not sel:
            messagebox.showwarning("No booking", "Select an active booking to cancel.")
            return
        if not messagebox.askyesno("Cancel booking", "Cancel this booking?"):
            return
        try:
            self.app.svc.bookings.cancel(self.app.user, int(sel[0]))
        except ServiceError as e:
            messagebox.showerror("Cannot cancel", str(e))
        self.refresh()


# --------------------------------------------------------------- admin tabs
class AdminResourcesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        left = ttk.LabelFrame(self, text="Resources and live availability", padding=6)
        left.pack(side="left", fill="both", expand=True)
        frame, self.tree = make_tree(left, ("Code", "Name", "Type", "Status now"), (120, 180, 160, 130))
        frame.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.LabelFrame(self, text="Add / update / remove", padding=10)
        form.pack(side="right", fill="y", padx=(8, 0))
        self.code, self.name, self.rtype = tk.StringVar(), tk.StringVar(), tk.StringVar(value=RESOURCE_TYPES[0])
        self.code_entry = ttk.Entry(form, textvariable=self.code, width=22)
        for r, (lbl, w) in enumerate((("Unique code", self.code_entry),
                                      ("Name", ttk.Entry(form, textvariable=self.name, width=22)),
                                      ("Type", ttk.Combobox(form, textvariable=self.rtype, values=RESOURCE_TYPES,
                                                            width=19, state="readonly")))):
            ttk.Label(form, text=lbl).grid(row=r, column=0, sticky="w", pady=4)
            w.grid(row=r, column=1, pady=4, padx=4)
        for r, (txt, cmd) in enumerate((("Add new resource", self.add), ("Update selected", self.update),
                                        ("Remove selected", self.remove), ("Clear form", self.clear)), start=3):
            ttk.Button(form, text=txt, command=cmd).grid(row=r, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Label(form, text="Codes are unique across all campuses\n(e.g. JHB-LAB-03). A code cannot be\nchanged once created.",
                  foreground="#555").grid(row=7, column=0, columnspan=2, pady=8)

    def refresh(self):
        rows = [(i["resource"].id, (i["resource"].code, i["resource"].name, i["resource"].type, i["now"]),
                 "good" if i["now"] == "Available" else "bad")
                for i in self.app.svc.bookings.availability(self.app.campus.id)]
        fill_tree(self.tree, rows)

    def on_select(self, _e=None):
        sel = self.tree.selection()
        if sel:
            code, name, rtype, _ = self.tree.item(sel[0], "values")
            self.code.set(code)
            self.name.set(name)
            self.rtype.set(rtype)

    def clear(self):
        self.code.set("")
        self.name.set("")
        self.tree.selection_set(())

    def _run(self, fn, *args):
        try:
            fn(*args)
        except ServiceError as e:
            messagebox.showerror("Not saved", str(e))
            return False
        self.refresh()
        return True

    def add(self):
        if self._run(self.app.svc.resources.add, self.app.campus.id, self.code.get(), self.name.get(), self.rtype.get()):
            self.clear()

    def update(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No resource", "Select a resource to update.")
            return
        self._run(self.app.svc.resources.update, int(sel[0]), self.name.get(), self.rtype.get())

    def remove(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No resource", "Select a resource to remove.")
        elif messagebox.askyesno("Remove", "Remove this resource? Past bookings are kept for reporting."):
            if self._run(self.app.svc.resources.remove, int(sel[0])):
                self.clear()


class BookingsTab(ttk.Frame):
    def __init__(self, parent, app, all_campuses):
        super().__init__(parent, padding=8)
        self.app, self.all = app, all_campuses
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        self.filter = tk.StringVar(value="All campuses")
        if all_campuses:
            ttk.Label(bar, text="Campus:").pack(side="left")
            names = ["All campuses"] + [c.name for c in app.svc.registry.campuses.values()]
            cb = ttk.Combobox(bar, textvariable=self.filter, values=names, state="readonly", width=20)
            cb.pack(side="left", padx=6)
            cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left", padx=6)
        self.count = ttk.Label(bar)
        self.count.pack(side="right")
        frame, self.tree = make_tree(self, ("ID", "Campus", "Resource", "Lecturer", "Start", "End", "Mins", "Status"),
                                     (40, 100, 190, 140, 130, 130, 50, 90), height=16)
        frame.pack(fill="both", expand=True)

    def refresh(self):
        cid = None if self.all else self.app.campus.id
        rows = self.app.svc.bookings.list_bookings(campus_id=cid)
        if self.all and self.filter.get() != "All campuses":
            rows = [b for b in rows if b["campus"] == self.filter.get()]
        fill_tree(self.tree, [(b["id"], (b["id"], b["campus"], f"{b['code']} - {b['resource']}", b["lecturer"],
                                         b["start_time"], b["end_time"], b["duration_min"], b["state"]),
                               "bad" if b["state"] == "Cancelled" else None) for b in rows])
        self.count.config(text=f"{len(rows)} booking(s)")


class ReportTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self.text = tk.Text(self, height=11, wrap="word", font=("Consolas", 10), state="disabled", bg="#f7f7f7")
        self.text.pack(fill="x")
        charts = ttk.Frame(self)
        charts.pack(fill="both", expand=True, pady=(8, 0))
        self.c1 = tk.Canvas(charts, height=230, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.c2 = tk.Canvas(charts, height=230, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.c1.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.c2.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.c1.bind("<Configure>", lambda _e: self.refresh())

    def refresh(self):
        rep = self.app.svc.reports.campus_report(self.app.campus.id)
        lines = [f"CAMPUS REPORT - {self.app.campus.name}", "-" * 50,
                 f"Total bookings (active/completed): {rep['total']}",
                 f"Cancelled bookings               : {rep['cancelled']}",
                 f"Average booking duration         : {fmt_minutes(rep['avg_minutes'])}",
                 f"Total booked time                : {rep['booked_hours']:.1f} hours "
                 f"across {rep['resource_count']} resources", "", "Most frequently used resources:"]
        lines += [f"  {i}. {code} {name}: {n} booking(s)" for i, (code, name, n) in enumerate(rep["top"], 1)] \
            or ["  (no bookings yet)"]
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "\n".join(lines))
        self.text.config(state="disabled")
        draw_bars(self.c1, [(code, n) for code, _, n in rep["top"]], "Most used resources (bookings)")
        draw_bars(self.c2, rep["by_weekday"], "Usage trend: bookings by weekday")


# ------------------------------------------------------------ operator tabs
class AllResourcesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        frame, self.tree = make_tree(self, ("Campus", "Code", "Name", "Type", "Status now"),
                                     (110, 130, 200, 160, 140), height=18)
        frame.pack(fill="both", expand=True)

    def refresh(self):
        rows = []
        for cid, campus in self.app.svc.registry.campuses.items():
            for i in self.app.svc.bookings.availability(cid):
                r = i["resource"]
                rows.append((r.id, (campus.name, r.code, r.name, r.type, i["now"]),
                             "good" if i["now"] == "Available" else "bad"))
        fill_tree(self.tree, rows)


class ComparisonTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        cols = ("Campus", "Policy", "Max session", "Resources", "Bookings", "Avg duration", "Booked hrs",
                "Bookings/resource", "Cancelled", "Top resource")
        frame, self.tree = make_tree(self, cols, (95, 70, 80, 70, 70, 90, 80, 110, 70, 170), height=4)
        frame.pack(fill="x")
        self.text = tk.Text(self, height=6, wrap="word", state="disabled", bg="#f7f7f7")
        self.text.pack(fill="x", pady=8)
        charts = ttk.Frame(self)
        charts.pack(fill="both", expand=True)
        self.c1 = tk.Canvas(charts, height=220, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.c2 = tk.Canvas(charts, height=220, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.c1.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.c2.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.c1.bind("<Configure>", lambda _e: self.refresh())

    def refresh(self):
        rows = self.app.svc.reports.compare_campuses()
        fill_tree(self.tree, [(i, (r["campus"], r["policy"], f"{r['max_minutes']} min", r["resources"], r["total"],
                                   fmt_minutes(r["avg_minutes"]), f"{r['booked_hours']:.1f}",
                                   f"{r['per_resource']:.1f}", r["cancelled"], r["top"]), None)
                              for i, r in enumerate(rows)])
        notes = ["INSIGHTS - effect of campus-specific rules:"]
        if rows and any(r["total"] for r in rows):
            busiest = max(rows, key=lambda r: r["total"])
            longest = max(rows, key=lambda r: r["avg_minutes"])
            dense = max(rows, key=lambda r: r["per_resource"])
            notes += [f"- Most bookings overall: {busiest['campus']} ({busiest['total']}).",
                      f"- Longest average session: {longest['campus']} ({fmt_minutes(longest['avg_minutes'])}) "
                      f"under its {longest['policy']} policy (cap {longest['max_minutes']} min).",
                      f"- Highest utilisation per resource: {dense['campus']} ({dense['per_resource']:.1f} bookings each)."]
            for r in rows:
                if r["avg_minutes"] and r["max_minutes"]:
                    notes.append(f"- {r['campus']}: average session uses "
                                 f"{100 * r['avg_minutes'] / r['max_minutes']:.0f}% of the allowed maximum.")
        else:
            notes.append("- No booking data yet.")
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "\n".join(notes))
        self.text.config(state="disabled")
        draw_bars(self.c1, [(r["campus"], r["total"]) for r in rows], "Bookings per campus")
        draw_bars(self.c2, [(r["campus"], round(r["booked_hours"], 1)) for r in rows], "Booked hours per campus")


# ---------------------------------------------------------------------- app
class App(tk.Tk):
    def __init__(self, services):
        super().__init__()
        self.title("Smart Campus Resource Booking System")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.svc = services
        self.user = self.campus = self.current = None
        ttk.Style(self).theme_use("clam")
        self.show_login()
        self.after(30000, self._auto_refresh)

    def _swap(self, cls):
        if self.current is not None:
            self.current.destroy()
        self.current = cls(self, self)
        self.current.pack(fill="both", expand=True)

    def show_login(self):
        self._swap(LoginFrame)

    def show_campus_select(self):
        self._swap(CampusFrame)

    def show_dashboard(self):
        self._swap(Dashboard)

    def logout(self):
        self.user = self.campus = None
        self.show_login()

    def _auto_refresh(self):
        """Keep the 'real-time' availability current while a dashboard is open."""
        if isinstance(self.current, Dashboard):
            self.current.refresh_current()
        self.after(30000, self._auto_refresh)
