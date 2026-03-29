PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS hotel_checkins;
DROP TABLE IF EXISTS reservations;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','client','superadmin')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE rooms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  price_per_night REAL NOT NULL DEFAULT 0,
  capacity INTEGER NOT NULL,
  description TEXT
);

CREATE TABLE reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  guest_name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL,
  room_id INTEGER NOT NULL,
  check_in TEXT NOT NULL,
  check_out TEXT NOT NULL,
  guests INTEGER NOT NULL,
  special_requests TEXT,
  status TEXT NOT NULL CHECK(status IN ('confirmed','checked_in','checked_out','cancelled')) DEFAULT 'confirmed',
  admin_alert_dismissed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE
);

CREATE TABLE hotel_checkins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reservation_id INTEGER,
  source_type TEXT NOT NULL DEFAULT 'direct'
    CHECK(source_type IN ('direct','reservation')),

  guest_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  room_id INTEGER NOT NULL,
  check_in TEXT NOT NULL,
  check_out TEXT NOT NULL,
  guests INTEGER NOT NULL,
  extra_person INTEGER NOT NULL DEFAULT 0,
  special_requests TEXT,

  payment_method TEXT NOT NULL DEFAULT 'cash'
    CHECK(payment_method IN ('cash','card','transfer','mixed')),
  total_amount REAL NOT NULL DEFAULT 0,
  amount_paid REAL NOT NULL DEFAULT 0,
  amount_pending REAL NOT NULL DEFAULT 0,

  status TEXT NOT NULL DEFAULT 'checked_in'
    CHECK(status IN ('checked_in','checked_out','cancelled')),

  created_by INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  checked_out_at TEXT,

  FOREIGN KEY(reservation_id) REFERENCES reservations(id) ON DELETE SET NULL,
  FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
  FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_users_role ON users(role);

CREATE INDEX idx_reservations_room_dates ON reservations(room_id, check_in, check_out);
CREATE INDEX idx_reservations_user ON reservations(user_id);
CREATE INDEX idx_reservations_status ON reservations(status);
CREATE INDEX idx_reservations_created_at ON reservations(created_at);

CREATE INDEX idx_hotel_checkins_room_dates ON hotel_checkins(room_id, check_in, check_out);
CREATE INDEX idx_hotel_checkins_status ON hotel_checkins(status);
CREATE INDEX idx_hotel_checkins_created_at ON hotel_checkins(created_at);
CREATE INDEX idx_hotel_checkins_reservation_id ON hotel_checkins(reservation_id);