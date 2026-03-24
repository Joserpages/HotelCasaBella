PRAGMA foreign_keys = ON;

-- =========================================
-- ELIMINAR TABLAS (RESETEO)
-- =========================================
DROP TABLE IF EXISTS reservations;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS users;

-- =========================================
-- TABLA USUARIOS
-- =========================================
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','client','superadmin')), -- ✅ agregado superadmin
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================
-- TABLA HABITACIONES
-- =========================================
CREATE TABLE rooms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  price_per_night REAL NOT NULL DEFAULT 0,
  capacity INTEGER NOT NULL,
  description TEXT
);

-- =========================================
-- TABLA RESERVACIONES
-- =========================================
CREATE TABLE reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  guest_name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT NOT NULL,
  room_id INTEGER NOT NULL,
  check_in TEXT NOT NULL,
  check_out TEXT NOT NULL,
  guests INTEGER NOT NULL,
  special_requests TEXT,
  status TEXT NOT NULL CHECK(status IN ('confirmed','checked_in','checked_out','cancelled')) DEFAULT 'confirmed',
  
  -- 🔥 ESTA COLUMNA ES CLAVE PARA TU APP
  admin_alert_dismissed INTEGER NOT NULL DEFAULT 0,

  created_at TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE
);

-- =========================================
-- ÍNDICES (OPTIMIZACIÓN)
-- =========================================
CREATE INDEX idx_users_role ON users(role);

CREATE INDEX idx_reservations_room_dates 
ON reservations(room_id, check_in, check_out);

CREATE INDEX idx_reservations_user 
ON reservations(user_id);

CREATE INDEX idx_reservations_status 
ON reservations(status);

CREATE INDEX idx_reservations_created_at 
ON reservations(created_at);