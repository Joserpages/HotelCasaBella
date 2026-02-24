from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, flash, g, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hotel_casa_bella.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")


@dataclass
class ReservationData:
    guest_name: str
    email: str
    phone: str
    room_id: int
    check_in: date
    check_out: date
    guests: int
    special_requests: str


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
        with open(schema_path, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())
        conn.commit()

    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        room_count = conn.execute("SELECT COUNT(*) AS count FROM rooms").fetchone()["count"]
        if room_count == 0:
            rooms = [
                ("Suite Presidencial", "Suite", 350.0, 4, "Vista panorámica y jacuzzi privado"),
                ("Deluxe 101", "Deluxe", 220.0, 3, "Balcón al jardín interior"),
                ("Deluxe 102", "Deluxe", 220.0, 3, "Espacio ideal para descanso ejecutivo"),
                ("Estándar 201", "Estándar", 140.0, 2, "Habitación confortable con desayuno incluido"),
                ("Familiar 301", "Familiar", 280.0, 5, "Perfecta para familias grandes"),
            ]
            conn.executemany(
                """
                INSERT INTO rooms (name, category, price_per_night, capacity, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                rooms,
            )
            conn.commit()


def parse_reservation_form(form: dict[str, str]) -> ReservationData:
    check_in = datetime.strptime(form["check_in"], "%Y-%m-%d").date()
    check_out = datetime.strptime(form["check_out"], "%Y-%m-%d").date()
    return ReservationData(
        guest_name=form["guest_name"].strip(),
        email=form["email"].strip().lower(),
        phone=form["phone"].strip(),
        room_id=int(form["room_id"]),
        check_in=check_in,
        check_out=check_out,
        guests=int(form["guests"]),
        special_requests=form.get("special_requests", "").strip(),
    )


def validate_reservation(data: ReservationData, db: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    if not data.guest_name:
        errors.append("El nombre del huésped es obligatorio.")
    if data.check_in < date.today():
        errors.append("La fecha de llegada no puede ser anterior a hoy.")
    if data.check_out <= data.check_in:
        errors.append("La fecha de salida debe ser posterior a la fecha de llegada.")

    room = db.execute("SELECT * FROM rooms WHERE id = ?", (data.room_id,)).fetchone()
    if room is None:
        errors.append("La habitación seleccionada no existe.")
    else:
        if data.guests < 1:
            errors.append("Debe registrar al menos 1 huésped.")
        if data.guests > room["capacity"]:
            errors.append(
                f"La habitación {room['name']} permite máximo {room['capacity']} huéspedes."
            )

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
    total_rooms = db.execute("SELECT COUNT(*) AS count FROM rooms").fetchone()["count"]
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


@app.route("/")
def dashboard() -> str:
    db = get_db()
    stats = reservation_stats(db)
    return render_template("dashboard.html", stats=stats)


@app.route("/rooms")
def rooms() -> str:
    db = get_db()
    room_list = db.execute("SELECT * FROM rooms ORDER BY price_per_night DESC").fetchall()
    return render_template("rooms.html", rooms=room_list)


@app.route("/reservations")
def list_reservations() -> str:
    db = get_db()
    status = request.args.get("status", "all")
    query = """
        SELECT r.*, rm.name AS room_name
        FROM reservations r
        JOIN rooms rm ON rm.id = r.room_id
    """
    params: tuple[Any, ...] = ()
    if status != "all":
        query += " WHERE r.status = ?"
        params = (status,)
    query += " ORDER BY r.created_at DESC"
    reservations = db.execute(query, params).fetchall()
    return render_template("reservations.html", reservations=reservations, selected_status=status)


@app.route("/reservations/new", methods=["GET", "POST"])
def new_reservation() -> str:
    db = get_db()
    rooms_available = db.execute("SELECT * FROM rooms ORDER BY name").fetchall()

    if request.method == "POST":
        try:
            reservation = parse_reservation_form(request.form)
        except (KeyError, ValueError):
            flash("Hay campos inválidos o incompletos en el formulario.", "error")
            return render_template("reservation_form.html", rooms=rooms_available)

        errors = validate_reservation(reservation, db)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("reservation_form.html", rooms=rooms_available)

        db.execute(
            """
            INSERT INTO reservations
                (guest_name, email, phone, room_id, check_in, check_out, guests, special_requests, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')
            """,
            (
                reservation.guest_name,
                reservation.email,
                reservation.phone,
                reservation.room_id,
                reservation.check_in.isoformat(),
                reservation.check_out.isoformat(),
                reservation.guests,
                reservation.special_requests,
            ),
        )
        db.commit()
        flash("Reservación registrada exitosamente.", "success")
        return redirect(url_for("list_reservations"))

    return render_template("reservation_form.html", rooms=rooms_available)


@app.post("/reservations/<int:reservation_id>/status")
def update_reservation_status(reservation_id: int) -> str:
    db = get_db()
    status = request.form.get("status", "")
    if status not in {"confirmed", "checked_in", "checked_out", "cancelled"}:
        flash("Estado inválido.", "error")
        return redirect(url_for("list_reservations"))

    db.execute("UPDATE reservations SET status = ? WHERE id = ?", (status, reservation_id))
    db.commit()
    flash("Estado de reservación actualizado.", "success")
    return redirect(url_for("list_reservations"))


if __name__ == "__main__":
    if not DB_PATH.exists():
        init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
