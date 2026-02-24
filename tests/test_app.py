from datetime import date, timedelta

import app


def setup_module(module):
    app.DB_PATH.unlink(missing_ok=True)
    app.init_db()


def test_dashboard_loads():
    client = app.app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "Hotel Casa Bella" in response.get_data(as_text=True)


def test_create_reservation_success():
    client = app.app.test_client()
    today = date.today()
    payload = {
        "guest_name": "Ana Torres",
        "email": "ana@example.com",
        "phone": "555123456",
        "room_id": "1",
        "check_in": (today + timedelta(days=2)).isoformat(),
        "check_out": (today + timedelta(days=4)).isoformat(),
        "guests": "2",
        "special_requests": "Late check-in",
    }

    response = client.post("/reservations/new", data=payload, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Reservación registrada exitosamente." in body


def test_prevent_overlapping_reservation():
    client = app.app.test_client()
    today = date.today()
    payload = {
        "guest_name": "Luis Mora",
        "email": "luis@example.com",
        "phone": "555987654",
        "room_id": "1",
        "check_in": (today + timedelta(days=3)).isoformat(),
        "check_out": (today + timedelta(days=5)).isoformat(),
        "guests": "2",
        "special_requests": "",
    }

    response = client.post("/reservations/new", data=payload, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "no está disponible" in body
