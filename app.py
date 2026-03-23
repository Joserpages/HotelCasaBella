from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hotel_casa_bella.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")


# ==========================================================
# ✅ CONFIG HOTEL (SIN EXCEL)
# ==========================================================
EXTRA_PERSON_FEE = 50.0  # Q50 por noche

# Individuales que SÍ permiten persona extra (+Q50) -> max 2
INDIVIDUAL_EXTRA_ALLOWED = {
    "Habitación 201", "Habitación 202", "Habitación 203",
    "Habitación 301", "Habitación 302", "Habitación 303",
    "Habitación 401", "Habitación 402", "Habitación 403",
}
# A208 / B308 NO están aquí => NO permiten extra (se quedan en 1)

# Precios por habitación (ya sacado del Excel)
ROOM_PRICE_BY_NAME: dict[str, float] = {
    # Individual Delux Q300
    "Habitación 201": 300.0,
    "Habitación 202": 300.0,
    "Habitación 203": 300.0,
    "Habitación 301": 300.0,
    "Habitación 302": 300.0,
    "Habitación 303": 300.0,
    "Habitación 401": 300.0,
    "Habitación 402": 300.0,
    "Habitación 403": 300.0,

    # Individual Simple Q200
    "Habitación 208": 200.0,
    "Habitación 308": 200.0,

    # Triples Q550
    "Habitación 204": 550.0,
    "Habitación 304": 550.0,

    # Dobles Q450
    "Habitación 205": 450.0,
    "Habitación 206": 450.0,
    "Habitación 305": 450.0,
    "Habitación 306": 450.0,
    "Habitación 404": 450.0,
    "Habitación 405": 450.0,

    # Premium VIP Q500
    "Habitación 207": 500.0,
    "Habitación 307": 500.0,
    "Habitación 407": 500.0,

    # VIP Personal Q400
    "VIP Personal 1": 400.0,
    "VIP Personal 2": 400.0,

    # Presidencial Q650 (V203)
    "VIP Personal 3": 650.0,

    # Suite Presidencial Q650 (si tu “Suite” es otra habitación distinta)
    "Suite Presidencial": 650.0,
}

# Categorías por habitación
ROOM_CATEGORY_BY_NAME: dict[str, str] = {
    # Individual Simple
    "Habitación 208": "Individual Simple",
    "Habitación 308": "Individual Simple",

    # Individual Delux
    "Habitación 201": "Individual Delux",
    "Habitación 202": "Individual Delux",
    "Habitación 203": "Individual Delux",
    "Habitación 301": "Individual Delux",
    "Habitación 302": "Individual Delux",
    "Habitación 303": "Individual Delux",
    "Habitación 401": "Individual Delux",
    "Habitación 402": "Individual Delux",
    "Habitación 403": "Individual Delux",

    # Dobles
    "Habitación 205": "Dobles",
    "Habitación 206": "Dobles",
    "Habitación 305": "Dobles",
    "Habitación 306": "Dobles",
    "Habitación 404": "Dobles",
    "Habitación 405": "Dobles",

    # Triples
    "Habitación 204": "Triples",
    "Habitación 304": "Triples",

    # Premium VIP
    "Habitación 207": "Premium VIP",
    "Habitación 307": "Premium VIP",
    "Habitación 407": "Premium VIP",

    # VIP Personal
    "VIP Personal 1": "VIP Personal",
    "VIP Personal 2": "VIP Personal",

    # Presidencial
    "VIP Personal 3": "Presidencial",
    "Suite Presidencial": "Presidencial",
}

# Capacidad base por habitación (según tu Excel)
ROOM_CAPACITY_BY_NAME: dict[str, int] = {
    # Individual Simple (max 1)
    "Habitación 208": 1,
    "Habitación 308": 1,

    # Individual Delux (base 1, pero permite extra -> en validación se acepta 2 con checkbox)
    "Habitación 201": 1,
    "Habitación 202": 1,
    "Habitación 203": 1,
    "Habitación 301": 1,
    "Habitación 302": 1,
    "Habitación 303": 1,
    "Habitación 401": 1,
    "Habitación 402": 1,
    "Habitación 403": 1,

    # Dobles (max 3)
    "Habitación 205": 3,
    "Habitación 206": 3,
    "Habitación 305": 3,
    "Habitación 306": 3,
    "Habitación 404": 3,
    "Habitación 405": 3,

    # Triples (max 4)
    "Habitación 204": 4,
    "Habitación 304": 4,

    # Premium VIP (max 2)
    "Habitación 207": 2,
    "Habitación 307": 2,
    "Habitación 407": 2,

    # VIP Personal (max 1)
    "VIP Personal 1": 1,
    "VIP Personal 2": 1,

    # Presidencial / Suite Presidencial (max 2)
    "VIP Personal 3": 2,
    "Suite Presidencial": 2,
}

# Lista oficial de rooms que deben mostrarse (para ocultar “fantasmas” como 406)
OFFICIAL_ROOM_NAMES = set(ROOM_PRICE_BY_NAME.keys()) | {"Sala 408"}  # sala la podés mantener oculta por capacity=0


def apply_room_updates() -> dict[str, int]:
    """
    ✅ Actualiza BD existente (no borra):
    - Renombra Casa 1/2/3 -> VIP Personal 1/2/3
    - Renombra Suite -> Suite Presidencial
    - Ajusta category, capacity, price_per_night según diccionarios
    """
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

            # renombrar si aplica
            new_name = rename_map.get(name, name)
            if new_name != name:
                conn.execute("UPDATE rooms SET name = ? WHERE id = ?", (new_name, rid))
                name = new_name
                renamed += 1

            # precio
            if name in ROOM_PRICE_BY_NAME:
                conn.execute(
                    "UPDATE rooms SET price_per_night = ? WHERE id = ?",
                    (float(ROOM_PRICE_BY_NAME[name]), rid),
                )
                updated += 1

            # categoría
            if name in ROOM_CATEGORY_BY_NAME:
                conn.execute(
                    "UPDATE rooms SET category = ? WHERE id = ?",
                    (ROOM_CATEGORY_BY_NAME[name], rid),
                )

            # capacidad
            if name in ROOM_CAPACITY_BY_NAME:
                conn.execute(
                    "UPDATE rooms SET capacity = ? WHERE id = ?",
                    (int(ROOM_CAPACITY_BY_NAME[name]), rid),
                )

        conn.commit()

    return {"updated": updated, "renamed": renamed}


def hide_non_official_rooms() -> int:
    """
    ✅ Oculta (capacity=0) habitaciones que quedaron del seed viejo
    y NO existen en tu lista oficial (ej: Habitación 406).
    """
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


def ensure_reservations_alert_column() -> None:
    """
    Agrega la columna admin_alert_dismissed si no existe.
    0 = alerta pendiente
    1 = alerta quitada por admin/recepción
    """
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


# =========================
# DB helpers
# =========================
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

        # Seed admin
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@casabella.com")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "Admin123*")

        exists = conn.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        if exists is None:
            conn.execute(
                """
                INSERT INTO users (full_name, email, password_hash, role)
                VALUES (?, ?, ?, 'admin')
                """,
                ("Administrador", admin_email, generate_password_hash(admin_pass)),
            )
            conn.commit()


# =========================
# Auth helpers
# =========================
def current_user() -> Optional[sqlite3.Row]:
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

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
@app.context_processor
def inject_user():
    return {"current_user": current_user()}


F = TypeVar("F", bound=Callable[..., Any])


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not session.get("user_id"):
            flash("Debes iniciar sesión.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped  # type: ignore


def admin_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user = current_user()
        if user is None:
            flash("Debes iniciar sesión.", "error")
            return redirect(url_for("login"))
        if user["role"] != "admin":
            flash("No tienes permisos para acceder aquí.", "error")
            return redirect(url_for("my_reservations"))
        return view(*args, **kwargs)
    return wrapped  # type: ignore


# =========================
# HOME
# =========================
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


# =========================
# Auth routes
# =========================
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

        if user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("my_reservations"))

    return render_template("login.html")


@app.get("/logout")
def logout() -> str:
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("login"))


# =========================
# Reservas helpers
# =========================
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

    # Persona extra SOLO para individuales permitidas
    if room_name in INDIVIDUAL_EXTRA_ALLOWED:
        max_allowed = base_capacity + 1  # base 1 => permite 2
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

    # Disponibilidad
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

    return {
        "total_rooms": total_rooms,
        "active_reservations": active_reservations,
        "occupancy": occupancy,
        "upcoming_checkins": upcoming_checkins,
    }


# =========================
# Admin routes
# =========================
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


# =========================
# Client routes
# =========================
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


if __name__ == "__main__":
    if not DB_PATH.exists():
        init_db()

    ensure_reservations_alert_column()

    res = apply_room_updates()
    print(f"[ROOMS] actualizadas: {res['updated']} | renombres: {res['renamed']}")

    hidden = hide_non_official_rooms()
    print(f"[ROOMS] ocultadas (no oficiales): {hidden}")

    app.run(host="0.0.0.0", port=5000, debug=True)