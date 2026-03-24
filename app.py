from __future__ import annotations

import calendar
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hotel_casa_bella.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")


# ==========================================================
# CONFIG HOTEL
# ==========================================================
EXTRA_PERSON_FEE = 50.0  # Q50 por noche

INDIVIDUAL_EXTRA_ALLOWED = {
    "Habitación 201", "Habitación 202", "Habitación 203",
    "Habitación 301", "Habitación 302", "Habitación 303",
    "Habitación 401", "Habitación 402", "Habitación 403",
}

ROOM_PRICE_BY_NAME: dict[str, float] = {
    "Habitación 201": 300.0,
    "Habitación 202": 300.0,
    "Habitación 203": 300.0,
    "Habitación 301": 300.0,
    "Habitación 302": 300.0,
    "Habitación 303": 300.0,
    "Habitación 401": 300.0,
    "Habitación 402": 300.0,
    "Habitación 403": 300.0,

    "Habitación 208": 200.0,
    "Habitación 308": 200.0,

    "Habitación 204": 550.0,
    "Habitación 304": 550.0,

    "Habitación 205": 450.0,
    "Habitación 206": 450.0,
    "Habitación 305": 450.0,
    "Habitación 306": 450.0,
    "Habitación 404": 450.0,
    "Habitación 405": 450.0,

    "Habitación 207": 500.0,
    "Habitación 307": 500.0,
    "Habitación 407": 500.0,

    "VIP Personal 1": 400.0,
    "VIP Personal 2": 400.0,

    "VIP Personal 3": 650.0,
    "Suite Presidencial": 650.0,
}

ROOM_CATEGORY_BY_NAME: dict[str, str] = {
    "Habitación 208": "Individual Simple",
    "Habitación 308": "Individual Simple",

    "Habitación 201": "Individual Delux",
    "Habitación 202": "Individual Delux",
    "Habitación 203": "Individual Delux",
    "Habitación 301": "Individual Delux",
    "Habitación 302": "Individual Delux",
    "Habitación 303": "Individual Delux",
    "Habitación 401": "Individual Delux",
    "Habitación 402": "Individual Delux",
    "Habitación 403": "Individual Delux",

    "Habitación 205": "Dobles",
    "Habitación 206": "Dobles",
    "Habitación 305": "Dobles",
    "Habitación 306": "Dobles",
    "Habitación 404": "Dobles",
    "Habitación 405": "Dobles",

    "Habitación 204": "Triples",
    "Habitación 304": "Triples",

    "Habitación 207": "Premium VIP",
    "Habitación 307": "Premium VIP",
    "Habitación 407": "Premium VIP",

    "VIP Personal 1": "VIP Personal",
    "VIP Personal 2": "VIP Personal",

    "VIP Personal 3": "Presidencial",
    "Suite Presidencial": "Presidencial",
}

ROOM_CAPACITY_BY_NAME: dict[str, int] = {
    "Habitación 208": 1,
    "Habitación 308": 1,

    "Habitación 201": 1,
    "Habitación 202": 1,
    "Habitación 203": 1,
    "Habitación 301": 1,
    "Habitación 302": 1,
    "Habitación 303": 1,
    "Habitación 401": 1,
    "Habitación 402": 1,
    "Habitación 403": 1,

    "Habitación 205": 3,
    "Habitación 206": 3,
    "Habitación 305": 3,
    "Habitación 306": 3,
    "Habitación 404": 3,
    "Habitación 405": 3,

    "Habitación 204": 4,
    "Habitación 304": 4,

    "Habitación 207": 2,
    "Habitación 307": 2,
    "Habitación 407": 2,

    "VIP Personal 1": 1,
    "VIP Personal 2": 1,

    "VIP Personal 3": 2,
    "Suite Presidencial": 2,
}

OFFICIAL_ROOM_NAMES = set(ROOM_PRICE_BY_NAME.keys()) | {"Sala 408"}

F = TypeVar("F", bound=Callable[..., Any])


# ==========================================================
# ROOM HELPERS
# ==========================================================
def apply_room_updates() -> dict[str, int]:
    if not DB_PATH.exists():
        return {"updated": 0, "renamed": 0}

    renamed = 0
    updated = 0

    rename_map = {
        "Casa 1": "VIP Personal 1",
        "Casa 2": "VIP Personal 2",
        "Casa 3": "VIP Personal 3",
        "Suite": "Suite Presidencial",
    }

    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rooms = conn.execute("SELECT id, name FROM rooms").fetchall()

        for r in rooms:
            rid = r["id"]
            name = r["name"]

            new_name = rename_map.get(name, name)
            if new_name != name:
                conn.execute("UPDATE rooms SET name = ? WHERE id = ?", (new_name, rid))
                name = new_name
                renamed += 1

            if name in ROOM_PRICE_BY_NAME:
                conn.execute(
                    "UPDATE rooms SET price_per_night = ? WHERE id = ?",
                    (float(ROOM_PRICE_BY_NAME[name]), rid),
                )
                updated += 1

            if name in ROOM_CATEGORY_BY_NAME:
                conn.execute(
                    "UPDATE rooms SET category = ? WHERE id = ?",
                    (ROOM_CATEGORY_BY_NAME[name], rid),
                )

            if name in ROOM_CAPACITY_BY_NAME:
                conn.execute(
                    "UPDATE rooms SET capacity = ? WHERE id = ?",
                    (int(ROOM_CAPACITY_BY_NAME[name]), rid),
                )

        conn.commit()

    return {"updated": updated, "renamed": renamed}


def hide_non_official_rooms() -> int:
    if not DB_PATH.exists():
        return 0

    hidden = 0
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, name FROM rooms").fetchall()

        for r in rows:
            rid = r["id"]
            name = r["name"]
            if name not in OFFICIAL_ROOM_NAMES:
                conn.execute("UPDATE rooms SET capacity = 0 WHERE id = ?", (rid,))
                hidden += 1

        conn.commit()

    return hidden


# ==========================================================
# DB MIGRATIONS
# ==========================================================
def ensure_reservations_alert_column() -> None:
    if not DB_PATH.exists():
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cols = conn.execute("PRAGMA table_info(reservations)").fetchall()
        col_names = {c["name"] for c in cols}

        if "admin_alert_dismissed" not in col_names:
            conn.execute(
                """
                ALTER TABLE reservations
                ADD COLUMN admin_alert_dismissed INTEGER NOT NULL DEFAULT 0
                """
            )
            conn.commit()


def migrate_users_table_for_superadmin() -> None:
    if not DB_PATH.exists():
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row

        create_sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()

        if not create_sql_row or not create_sql_row["sql"]:
            return

        create_sql = create_sql_row["sql"].lower()

        if "superadmin" in create_sql:
            return

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN TRANSACTION")

        try:
            conn.execute("ALTER TABLE users RENAME TO users_old")

            conn.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'client'
                        CHECK (role IN ('client', 'admin', 'superadmin')),
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )

            old_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(users_old)").fetchall()
            }

            if "created_at" in old_cols:
                conn.execute(
                    """
                    INSERT INTO users (id, full_name, email, password_hash, role, created_at)
                    SELECT id, full_name, email, password_hash, role, created_at
                    FROM users_old
                    """
                )
            else:
                conn.execute(
                    """
                    INSERT INTO users (id, full_name, email, password_hash, role)
                    SELECT id, full_name, email, password_hash, role
                    FROM users_old
                    """
                )

            conn.execute("DROP TABLE users_old")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")


def ensure_role_indexes_and_superadmin() -> None:
    if not DB_PATH.exists():
        return

    migrate_users_table_for_superadmin()

    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reservations_created_at ON reservations(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reservations_status ON reservations(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reservations_user_id ON reservations(user_id)")

        superadmin_email = os.environ.get("SUPERADMIN_EMAIL", "superadmin@casabella.com")
        superadmin_pass = os.environ.get("SUPERADMIN_PASSWORD", "SuperAdmin123*")

        exists = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (superadmin_email,),
        ).fetchone()

        if exists is None:
            conn.execute(
                """
                INSERT INTO users (full_name, email, password_hash, role)
                VALUES (?, ?, ?, 'superadmin')
                """,
                ("Super Administrador", superadmin_email, generate_password_hash(superadmin_pass)),
            )

        admin_email = os.environ.get("ADMIN_EMAIL", "admin@casabella.com")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "Admin123*")

        exists_admin = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (admin_email,),
        ).fetchone()

        if exists_admin is None:
            conn.execute(
                """
                INSERT INTO users (full_name, email, password_hash, role)
                VALUES (?, ?, ?, 'admin')
                """,
                ("Administrador", admin_email, generate_password_hash(admin_pass)),
            )

        conn.commit()


# ==========================================================
# DB HELPERS
# ==========================================================
def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    schema_path = BASE_DIR / "schema.sql"
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        with open(schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()


# ==========================================================
# AUTH HELPERS
# ==========================================================
def current_user() -> Optional[sqlite3.Row]:
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def user_has_role(user: Optional[sqlite3.Row], *allowed_roles: str) -> bool:
    if user is None:
        return False

    role = user["role"]
    hierarchy = {
        "client": 1,
        "admin": 2,
        "superadmin": 3,
    }
    user_level = hierarchy.get(role, 0)
    return any(user_level >= hierarchy.get(r, 999) for r in allowed_roles)


def get_pending_admin_alerts(db: sqlite3.Connection):
    return db.execute(
        """
        SELECT r.*, rm.name AS room_name, u.full_name AS user_name
        FROM reservations r
        JOIN rooms rm ON rm.id = r.room_id
        JOIN users u ON u.id = r.user_id
        WHERE r.admin_alert_dismissed = 0
          AND r.status != 'checked_out'
        ORDER BY r.created_at DESC
        """
    ).fetchall()


def reservation_total_for_template(reservation_row: sqlite3.Row) -> float:
    return calculate_reservation_total(reservation_row)


@app.context_processor
def inject_user():
    user = current_user()
    return {
        "current_user": user,
        "is_admin": user_has_role(user, "admin"),
        "is_superadmin": user_has_role(user, "superadmin"),
        "reservation_total_for_template": reservation_total_for_template,
    }


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not session.get("user_id"):
            flash("Debes iniciar sesión.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped  # type: ignore


def role_required(*roles: str):
    def decorator(view: F) -> F:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            user = current_user()
            if user is None:
                flash("Debes iniciar sesión.", "error")
                return redirect(url_for("login"))
            if not user_has_role(user, *roles):
                flash("No tienes permisos para acceder aquí.", "error")
                return redirect(url_for("my_reservations"))
            return view(*args, **kwargs)
        return wrapped  # type: ignore
    return decorator


admin_required = role_required("admin")
superadmin_required = role_required("superadmin")


# ==========================================================
# HOME
# ==========================================================
@app.get("/")
def index() -> str:
    db = get_db()

    featured_rooms = db.execute(
        """
        SELECT id, name, category, price_per_night, capacity
        FROM rooms
        WHERE capacity > 0
        ORDER BY price_per_night DESC, name ASC
        LIMIT 6
        """
    ).fetchall()

    return render_template("index.html", featured_rooms=featured_rooms)


@app.get("/book")
def book_now() -> str:
    if session.get("user_id"):
        return redirect(url_for("new_reservation"))
    return redirect(url_for("login"))


# ==========================================================
# AUTH ROUTES
# ==========================================================
@app.route("/register", methods=["GET", "POST"])
def register() -> str:
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not full_name or not email or not password:
            flash("Completa todos los campos.", "error")
            return render_template("register.html")

        db = get_db()
        exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if exists is not None:
            flash("Ese correo ya está registrado. Inicia sesión.", "error")
            return redirect(url_for("login"))

        db.execute(
            """
            INSERT INTO users (full_name, email, password_hash, role)
            VALUES (?, ?, ?, 'client')
            """,
            (full_name, email, generate_password_hash(password)),
        )
        db.commit()
        flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Correo o contraseña incorrectos.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        flash("Sesión iniciada.", "success")

        if user["role"] == "superadmin":
            return redirect(url_for("superadmin_dashboard"))
        if user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("my_reservations"))

    return render_template("login.html")


@app.get("/logout")
def logout() -> str:
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("login"))


# ==========================================================
# RESERVAS HELPERS
# ==========================================================
@dataclass
class ReservationData:
    guest_name: str
    email: str
    phone: str
    room_id: int
    check_in: date
    check_out: date
    guests: int
    extra_person: bool
    special_requests: str


def parse_reservation_form(form: Any) -> ReservationData:
    check_in = datetime.strptime(form["check_in"], "%Y-%m-%d").date()
    check_out = datetime.strptime(form["check_out"], "%Y-%m-%d").date()
    extra_person = (form.get("extra_person") == "1")

    return ReservationData(
        guest_name=(form.get("guest_name") or "").strip(),
        email=(form.get("email") or "").strip().lower(),
        phone=(form.get("phone") or "").strip(),
        room_id=int(form["room_id"]),
        check_in=check_in,
        check_out=check_out,
        guests=int(form["guests"]),
        extra_person=extra_person,
        special_requests=(form.get("special_requests") or "").strip(),
    )


def validate_reservation(data: ReservationData, db: sqlite3.Connection) -> list[str]:
    errors: list[str] = []

    if not data.guest_name:
        errors.append("El nombre del huésped es obligatorio.")
    if data.check_in < date.today():
        errors.append("La fecha de llegada no puede ser anterior a hoy.")
    if data.check_out <= data.check_in:
        errors.append("La fecha de salida debe ser posterior a la fecha de llegada.")
    if data.guests < 1:
        errors.append("Debe registrar al menos 1 huésped.")

    room = db.execute("SELECT * FROM rooms WHERE id = ?", (data.room_id,)).fetchone()
    if room is None:
        errors.append("La habitación seleccionada no existe.")
        return errors

    room_name = room["name"]
    base_capacity = int(room["capacity"])

    if room_name in INDIVIDUAL_EXTRA_ALLOWED:
        max_allowed = base_capacity + 1
        if data.guests == 2 and not data.extra_person:
            errors.append("Si van 2 personas en habitación Individual, debes marcar 'Persona extra (+Q50)'.")
        if data.extra_person and data.guests != 2:
            errors.append("La opción 'Persona extra' solo aplica cuando van 2 personas.")
        if data.guests > max_allowed:
            errors.append(f"{room_name} permite máximo {max_allowed} huéspedes (con persona extra).")
    else:
        if data.extra_person:
            errors.append("Esta habitación no permite 'persona extra'.")
        if data.guests > base_capacity:
            errors.append(f"{room_name} permite máximo {base_capacity} huéspedes.")

    overlapping = db.execute(
        """
        SELECT id
        FROM reservations
        WHERE room_id = ?
          AND status IN ('confirmed', 'checked_in')
          AND NOT (check_out <= ? OR check_in >= ?)
        LIMIT 1
        """,
        (data.room_id, data.check_in.isoformat(), data.check_out.isoformat()),
    ).fetchone()
    if overlapping is not None:
        errors.append("La habitación no está disponible para ese rango de fechas.")

    return errors


def reservation_stats(db: sqlite3.Connection) -> dict[str, Any]:
    today = date.today().isoformat()
    total_rooms = db.execute("SELECT COUNT(*) AS count FROM rooms WHERE capacity > 0").fetchone()["count"]
    active_reservations = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM reservations
        WHERE status IN ('confirmed', 'checked_in')
          AND check_out > ?
        """,
        (today,),
    ).fetchone()["count"]
    occupancy = round((active_reservations / total_rooms) * 100, 1) if total_rooms else 0

    upcoming_checkins = db.execute(
        """
        SELECT r.*, rm.name AS room_name
        FROM reservations r
        JOIN rooms rm ON rm.id = r.room_id
        WHERE r.check_in >= ?
        ORDER BY r.check_in ASC
        LIMIT 5
        """,
        (today,),
    ).fetchall()

    total_users = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    total_clients = db.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'client'").fetchone()["count"]
    total_admins = db.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'admin'").fetchone()["count"]
    total_superadmins = db.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'superadmin'").fetchone()["count"]

    return {
        "total_rooms": total_rooms,
        "active_reservations": active_reservations,
        "occupancy": occupancy,
        "upcoming_checkins": upcoming_checkins,
        "total_users": total_users,
        "total_clients": total_clients,
        "total_admins": total_admins,
        "total_superadmins": total_superadmins,
    }


def parse_month_param(month_str: str | None) -> tuple[date, date, str]:
    if month_str:
        start = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
    else:
        today = date.today()
        start = today.replace(day=1)

    last_day = calendar.monthrange(start.year, start.month)[1]
    end = start.replace(day=last_day) + timedelta(days=1)
    label = start.strftime("%Y-%m")
    return start, end, label


def reservation_has_extra_person(reservation_row: sqlite3.Row) -> bool:
    special = (reservation_row["special_requests"] or "").lower()
    return "persona extra" in special


def calculate_reservation_total(reservation_row: sqlite3.Row) -> float:
    check_in = datetime.strptime(reservation_row["check_in"], "%Y-%m-%d").date()
    check_out = datetime.strptime(reservation_row["check_out"], "%Y-%m-%d").date()
    nights = max((check_out - check_in).days, 1)
    base = float(reservation_row["price_per_night"]) * nights
    extra = EXTRA_PERSON_FEE * nights if reservation_has_extra_person(reservation_row) else 0.0
    return round(base + extra, 2)


def get_monthly_movements(db: sqlite3.Connection, start: date, end: date):
    return db.execute(
        """
        SELECT
            r.*,
            rm.name AS room_name,
            rm.category AS room_category,
            rm.price_per_night AS price_per_night,
            u.full_name AS user_name,
            u.email AS user_email,
            u.role AS user_role
        FROM reservations r
        JOIN rooms rm ON rm.id = r.room_id
        JOIN users u ON u.id = r.user_id
        WHERE date(r.created_at) >= date(?)
          AND date(r.created_at) < date(?)
        ORDER BY r.created_at DESC
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()


def build_monthly_excel(movements, month_label: str):
    wb = Workbook()

    ws = wb.active
    ws.title = "Movimientos"

    headers = [
        "ID Reservación", "Fecha creación", "Usuario", "Correo usuario", "Rol usuario",
        "Huésped", "Correo huésped", "Teléfono", "Habitación", "Categoría",
        "Check in", "Check out", "Noches", "Huéspedes", "Persona extra",
        "Precio por noche", "Estado", "Total", "Solicitudes especiales",
    ]
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)

    for col_idx, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    total_ingresos = 0.0
    status_counter = {"confirmed": 0, "checked_in": 0, "checked_out": 0, "cancelled": 0}
    room_counter: dict[str, int] = {}

    for mv in movements:
        check_in_d = datetime.strptime(mv["check_in"], "%Y-%m-%d").date()
        check_out_d = datetime.strptime(mv["check_out"], "%Y-%m-%d").date()
        nights = max((check_out_d - check_in_d).days, 1)
        has_extra = reservation_has_extra_person(mv)
        total = calculate_reservation_total(mv)

        total_ingresos += total
        status_counter[mv["status"]] = status_counter.get(mv["status"], 0) + 1
        room_counter[mv["room_name"]] = room_counter.get(mv["room_name"], 0) + 1

        ws.append([
            mv["id"],
            mv["created_at"],
            mv["user_name"],
            mv["user_email"],
            mv["user_role"],
            mv["guest_name"],
            mv["email"],
            mv["phone"],
            mv["room_name"],
            mv["room_category"],
            mv["check_in"],
            mv["check_out"],
            nights,
            mv["guests"],
            "Sí" if has_extra else "No",
            float(mv["price_per_night"]),
            mv["status"],
            total,
            mv["special_requests"],
        ])

    for row in ws.iter_rows(min_row=2, min_col=16, max_col=18):
        row[0].number_format = 'Q #,##0.00'
        row[2].number_format = 'Q #,##0.00'

    widths = {
        "A": 14, "B": 20, "C": 24, "D": 28, "E": 14, "F": 22, "G": 26, "H": 18,
        "I": 22, "J": 18, "K": 12, "L": 12, "M": 10, "N": 10, "O": 14, "P": 14,
        "Q": 14, "R": 14, "S": 35,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    summary = wb.create_sheet("Resumen")
    summary["A1"] = f"Resumen mensual - {month_label}"
    summary["A1"].font = Font(size=14, bold=True)

    summary["A3"] = "Total movimientos"
    summary["B3"] = len(movements)

    summary["A4"] = "Ingresos estimados"
    summary["B4"] = total_ingresos
    summary["B4"].number_format = 'Q #,##0.00'

    summary["A6"] = "Estados"
    summary["A6"].font = Font(bold=True)

    summary["A7"] = "Confirmadas"
    summary["B7"] = status_counter.get("confirmed", 0)
    summary["A8"] = "Check in"
    summary["B8"] = status_counter.get("checked_in", 0)
    summary["A9"] = "Check out"
    summary["B9"] = status_counter.get("checked_out", 0)
    summary["A10"] = "Canceladas"
    summary["B10"] = status_counter.get("cancelled", 0)

    summary["D6"] = "Habitaciones con más movimiento"
    summary["D6"].font = Font(bold=True)

    row_idx = 7
    for room_name, qty in sorted(room_counter.items(), key=lambda x: x[1], reverse=True)[:10]:
        summary[f"D{row_idx}"] = room_name
        summary[f"E{row_idx}"] = qty
        row_idx += 1

    summary.column_dimensions["A"].width = 24
    summary.column_dimensions["B"].width = 16
    summary.column_dimensions["D"].width = 28
    summary.column_dimensions["E"].width = 14

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


# ==========================================================
# ADMIN ROUTES
# ==========================================================
@app.route("/admin")
@admin_required
def admin_dashboard() -> str:
    db = get_db()
    stats = reservation_stats(db)

    pending_alerts = get_pending_admin_alerts(db)
    has_pending_alerts = len(pending_alerts) > 0

    return render_template(
        "dashboard.html",
        stats=stats,
        pending_alerts=pending_alerts,
        has_pending_alerts=has_pending_alerts,
    )


@app.route("/admin/reservations")
@admin_required
def admin_reservations() -> str:
    db = get_db()
    status = request.args.get("status", "active")

    if status == "checked_out":
        query = """
            SELECT r.*, rm.name AS room_name, u.full_name AS user_name
            FROM reservations r
            JOIN rooms rm ON rm.id = r.room_id
            JOIN users u ON u.id = r.user_id
            WHERE r.status = 'checked_out'
            ORDER BY r.created_at DESC
        """
        reservations = db.execute(query).fetchall()

    elif status == "all":
        query = """
            SELECT r.*, rm.name AS room_name, u.full_name AS user_name
            FROM reservations r
            JOIN rooms rm ON rm.id = r.room_id
            JOIN users u ON u.id = r.user_id
            ORDER BY
                CASE WHEN r.admin_alert_dismissed = 0 THEN 0 ELSE 1 END,
                r.created_at DESC
        """
        reservations = db.execute(query).fetchall()

    else:
        query = """
            SELECT r.*, rm.name AS room_name, u.full_name AS user_name
            FROM reservations r
            JOIN rooms rm ON rm.id = r.room_id
            JOIN users u ON u.id = r.user_id
            WHERE r.status != 'checked_out'
            ORDER BY
                CASE WHEN r.admin_alert_dismissed = 0 THEN 0 ELSE 1 END,
                r.created_at DESC
        """
        reservations = db.execute(query).fetchall()

    pending_alerts = get_pending_admin_alerts(db)
    has_pending_alerts = len(pending_alerts) > 0

    return render_template(
        "reservations_admin.html",
        reservations=reservations,
        selected_status=status,
        pending_alerts=pending_alerts,
        has_pending_alerts=has_pending_alerts,
    )


@app.post("/admin/reservations/<int:reservation_id>/status")
@admin_required
def admin_update_reservation_status(reservation_id: int) -> str:
    db = get_db()
    status = request.form.get("status", "")
    if status not in {"confirmed", "checked_in", "checked_out", "cancelled"}:
        flash("Estado inválido.", "error")
        return redirect(url_for("admin_reservations"))

    if status in {"checked_out", "cancelled"}:
        db.execute(
            """
            UPDATE reservations
            SET status = ?, admin_alert_dismissed = 1
            WHERE id = ?
            """,
            (status, reservation_id),
        )
    else:
        db.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )

    db.commit()
    flash("Estado de reservación actualizado.", "success")
    return redirect(url_for("admin_reservations"))


@app.post("/admin/reservations/<int:reservation_id>/dismiss-alert")
@admin_required
def dismiss_reservation_alert(reservation_id: int) -> str:
    db = get_db()
    db.execute(
        "UPDATE reservations SET admin_alert_dismissed = 1 WHERE id = ?",
        (reservation_id,),
    )
    db.commit()
    flash("Alarma de reservación desactivada.", "success")
    return redirect(url_for("admin_reservations"))


# ==========================================================
# SUPERADMIN ROUTES
# ==========================================================
@app.route("/superadmin")
@superadmin_required
def superadmin_dashboard() -> str:
    db = get_db()
    stats = reservation_stats(db)
    start, end, month_label = parse_month_param(request.args.get("month"))
    movements = get_monthly_movements(db, start, end)

    total_ingresos = sum(calculate_reservation_total(mv) for mv in movements)
    pending_alerts = get_pending_admin_alerts(db)
    has_pending_alerts = len(pending_alerts) > 0

    top_rooms: dict[str, int] = {}
    status_counter = {"confirmed": 0, "checked_in": 0, "checked_out": 0, "cancelled": 0}
    ingresos_por_dia: dict[str, float] = {}

    for mv in movements:
        top_rooms[mv["room_name"]] = top_rooms.get(mv["room_name"], 0) + 1
        status_counter[mv["status"]] = status_counter.get(mv["status"], 0) + 1

        fecha = str(mv["created_at"])[:10]
        ingresos_por_dia[fecha] = ingresos_por_dia.get(fecha, 0.0) + calculate_reservation_total(mv)

    top_rooms_sorted = sorted(top_rooms.items(), key=lambda x: x[1], reverse=True)[:6]
    ingresos_por_dia_sorted = sorted(ingresos_por_dia.items(), key=lambda x: x[0])

    return render_template(
        "superadmin_dashboard.html",
        stats=stats,
        month_label=month_label,
        monthly_movements=movements,
        monthly_income=total_ingresos,
        top_rooms=top_rooms_sorted,
        pending_alerts=pending_alerts,
        has_pending_alerts=has_pending_alerts,
        status_counter=status_counter,
        ingresos_por_dia=ingresos_por_dia_sorted,
    )


@app.route("/superadmin/users", methods=["GET", "POST"])
@superadmin_required
def superadmin_users() -> str:
    db = get_db()

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "client").strip()

        if role not in {"client", "admin", "superadmin"}:
            flash("Rol inválido.", "error")
            return redirect(url_for("superadmin_users"))

        if not full_name or not email or not password:
            flash("Debes completar nombre, correo y contraseña.", "error")
            return redirect(url_for("superadmin_users"))

        exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if exists:
            flash("Ese correo ya existe.", "error")
            return redirect(url_for("superadmin_users"))

        db.execute(
            """
            INSERT INTO users (full_name, email, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (full_name, email, generate_password_hash(password), role),
        )
        db.commit()
        flash("Usuario creado correctamente.", "success")
        return redirect(url_for("superadmin_users"))

    q = (request.args.get("q") or "").strip().lower()
    role_filter = (request.args.get("role") or "").strip()

    sql = """
        SELECT u.*,
               COUNT(r.id) AS total_reservations
        FROM users u
        LEFT JOIN reservations r ON r.user_id = u.id
        WHERE 1=1
    """
    params: list[Any] = []

    if q:
        sql += " AND (LOWER(u.full_name) LIKE ? OR LOWER(u.email) LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])

    if role_filter in {"client", "admin", "superadmin"}:
        sql += " AND u.role = ?"
        params.append(role_filter)

    sql += " GROUP BY u.id ORDER BY u.created_at DESC"

    users = db.execute(sql, params).fetchall()

    return render_template(
        "superadmin_users.html",
        users=users,
        q=q,
        role_filter=role_filter,
    )


@app.post("/superadmin/users/<int:user_id>/role")
@superadmin_required
def superadmin_update_user_role(user_id: int) -> str:
    db = get_db()
    new_role = (request.form.get("role") or "").strip()

    if new_role not in {"client", "admin", "superadmin"}:
        flash("Rol inválido.", "error")
        return redirect(url_for("superadmin_users"))

    current = current_user()
    target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("superadmin_users"))

    if current and current["id"] == user_id and new_role != "superadmin":
        flash("No puedes quitarte tu propio rol de superadmin.", "error")
        return redirect(url_for("superadmin_users"))

    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    db.commit()
    flash("Rol actualizado correctamente.", "success")
    return redirect(url_for("superadmin_users"))


@app.post("/superadmin/users/<int:user_id>/reset-password")
@superadmin_required
def superadmin_reset_password(user_id: int) -> str:
    db = get_db()
    new_password = request.form.get("new_password") or ""

    if len(new_password) < 6:
        flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
        return redirect(url_for("superadmin_users"))

    target = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("superadmin_users"))

    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id),
    )
    db.commit()
    flash("Contraseña restablecida correctamente.", "success")
    return redirect(url_for("superadmin_users"))


@app.post("/superadmin/users/<int:user_id>/delete")
@superadmin_required
def superadmin_delete_user(user_id: int) -> str:
    db = get_db()
    current = current_user()

    target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("superadmin_users"))

    if current and current["id"] == user_id:
        flash("No puedes eliminar tu propio usuario.", "error")
        return redirect(url_for("superadmin_users"))

    reservations_count = db.execute(
        "SELECT COUNT(*) AS count FROM reservations WHERE user_id = ?",
        (user_id,),
    ).fetchone()["count"]

    if reservations_count > 0:
        flash("No puedes eliminar este usuario porque tiene reservaciones asociadas. Mejor cámbiale el rol.", "error")
        return redirect(url_for("superadmin_users"))

    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("Usuario eliminado correctamente.", "success")
    return redirect(url_for("superadmin_users"))


@app.get("/superadmin/export/monthly-report")
@superadmin_required
def superadmin_export_monthly_report():
    db = get_db()
    start, end, month_label = parse_month_param(request.args.get("month"))
    movements = get_monthly_movements(db, start, end)

    excel_file = build_monthly_excel(movements, month_label)
    filename = f"movimiento_mensual_{month_label}.xlsx"

    return send_file(
        excel_file,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ==========================================================
# CLIENT ROUTES
# ==========================================================
@app.route("/reservations/new", methods=["GET", "POST"])
@login_required
def new_reservation() -> str:
    db = get_db()

    rooms = db.execute(
        """
        SELECT id, name, category, price_per_night, capacity
        FROM rooms
        WHERE capacity > 0
        ORDER BY category, name
        """
    ).fetchall()

    rooms_meta = [
        {
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "price": float(r["price_per_night"]),
            "capacity": int(r["capacity"]),
            "extraAllowed": (r["name"] in INDIVIDUAL_EXTRA_ALLOWED),
        }
        for r in rooms
    ]

    categories = sorted({rm["category"] for rm in rooms_meta if rm.get("category")})

    if request.method == "POST":
        try:
            reservation = parse_reservation_form(request.form)
        except (KeyError, ValueError):
            flash("Hay campos inválidos o incompletos en el formulario.", "error")
            return render_template(
                "reservation_form.html",
                rooms_meta=rooms_meta,
                categories=categories,
                extra_fee=EXTRA_PERSON_FEE,
            )

        errors = validate_reservation(reservation, db)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "reservation_form.html",
                rooms_meta=rooms_meta,
                categories=categories,
                extra_fee=EXTRA_PERSON_FEE,
            )

        special = reservation.special_requests
        if reservation.extra_person:
            extra_line = f"[Persona extra: +Q{EXTRA_PERSON_FEE:.2f} por noche]"
            special = (special + "\n" + extra_line).strip() if special else extra_line

        db.execute(
            """
            INSERT INTO reservations
                (user_id, guest_name, email, phone, room_id, check_in, check_out, guests, special_requests, status, admin_alert_dismissed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 0)
            """,
            (
                session["user_id"],
                reservation.guest_name,
                reservation.email,
                reservation.phone,
                reservation.room_id,
                reservation.check_in.isoformat(),
                reservation.check_out.isoformat(),
                reservation.guests,
                special,
            ),
        )
        db.commit()
        flash("Reservación registrada exitosamente.", "success")
        return redirect(url_for("my_reservations"))

    return render_template(
        "reservation_form.html",
        rooms_meta=rooms_meta,
        categories=categories,
        extra_fee=EXTRA_PERSON_FEE,
    )


@app.route("/my-reservations", endpoint="my_reservations")
@login_required
def my_reservations() -> str:
    user = current_user()
    assert user is not None

    db = get_db()
    reservations = db.execute(
        """
        SELECT r.*, rm.name AS room_name
        FROM reservations r
        JOIN rooms rm ON rm.id = r.room_id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC
        """,
        (user["id"],),
    ).fetchall()

    return render_template("my_reservations.html", reservations=reservations)


@app.route("/rooms")
def rooms() -> str:
    db = get_db()
    room_list = db.execute(
        "SELECT * FROM rooms WHERE capacity > 0 ORDER BY category, name"
    ).fetchall()
    return render_template("rooms.html", rooms=room_list)


# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    if not DB_PATH.exists():
        init_db()

    ensure_reservations_alert_column()
    ensure_role_indexes_and_superadmin()

    res = apply_room_updates()
    print(f"[ROOMS] actualizadas: {res['updated']} | renombres: {res['renamed']}")

    hidden = hide_non_official_rooms()
    print(f"[ROOMS] ocultadas (no oficiales): {hidden}")

    app.run(host="0.0.0.0", port=5000, debug=True)