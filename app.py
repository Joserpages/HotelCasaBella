from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

DB_PATH = Path(__file__).resolve().parent / "hotel.db"


@dataclass
class Reservation:
    id: int
    guest_name: str
    email: str
    room_type: str
    check_in: str
    check_out: str
    guests: int
    notes: str
    created_at: str


class ReservationSystem:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_name TEXT NOT NULL,
                email TEXT NOT NULL,
                room_type TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                guests INTEGER NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def create_reservation(
        self,
        guest_name: str,
        email: str,
        room_type: str,
        check_in: str,
        check_out: str,
        guests: int,
        notes: str = "",
    ) -> int:
        required = [guest_name, email, room_type, check_in, check_out]
        if not all(field and str(field).strip() for field in required):
            raise ValueError("Todos los campos obligatorios deben completarse.")

        try:
            check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
            check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Las fechas deben estar en formato YYYY-MM-DD.") from exc

        if check_out_date <= check_in_date:
            raise ValueError("La fecha de salida debe ser posterior a la fecha de llegada.")

        if guests <= 0:
            raise ValueError("El número de huéspedes debe ser mayor a cero.")

        conn = self._connect()
        cursor = conn.execute(
            """
            INSERT INTO reservations
                (guest_name, email, room_type, check_in, check_out, guests, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guest_name.strip(),
                email.strip(),
                room_type.strip(),
                check_in,
                check_out,
                guests,
                notes.strip(),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()
        return reservation_id

    def list_reservations(self) -> List[Reservation]:
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT id, guest_name, email, room_type, check_in, check_out, guests, notes, created_at
            FROM reservations
            ORDER BY check_in ASC
            """
        ).fetchall()
        conn.close()
        return [Reservation(**dict(row)) for row in rows]


def main() -> None:
    system = ReservationSystem()
    print("=== Hotel Casa Bella - Sistema de Reservación ===")
    print("1) Crear reservación")
    print("2) Ver reservaciones")
    option = input("Selecciona una opción: ").strip()

    if option == "1":
        try:
            reservation_id = system.create_reservation(
                guest_name=input("Nombre del huésped: "),
                email=input("Correo electrónico: "),
                room_type=input("Tipo de habitación (Sencilla/Doble/Suite): "),
                check_in=input("Fecha de llegada (YYYY-MM-DD): "),
                check_out=input("Fecha de salida (YYYY-MM-DD): "),
                guests=int(input("Número de huéspedes: ").strip()),
                notes=input("Notas adicionales (opcional): "),
            )
            print(f"Reservación creada con éxito. ID: {reservation_id}")
        except ValueError as error:
            print(f"Error: {error}")
    elif option == "2":
        reservations = system.list_reservations()
        if not reservations:
            print("No hay reservaciones registradas.")
            return

        for reservation in reservations:
            print(
                f"[{reservation.id}] {reservation.guest_name} | {reservation.room_type} | "
                f"{reservation.check_in} -> {reservation.check_out} | Huéspedes: {reservation.guests}"
            )
    else:
        print("Opción inválida.")


if __name__ == "__main__":
    main()
