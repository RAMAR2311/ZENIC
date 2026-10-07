"""
init_zenic_db.py -- Inicializacion directa de ZenicMaster via SQL puro.
No depende de SQLAlchemy ORM para evitar conflictos de metadata.
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from werkzeug.security import generate_password_hash

DB_HOST = "localhost"
DB_USER = "postgres"
DB_PASS = "admin123"
DB_NAME = "ZenicMaster"

print("=== Iniciando setup de ZenicMaster ===")

# 1. Eliminar y recrear la BD
print("Conectando a PostgreSQL...")
conn = psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, database="postgres")
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

print("Terminando conexiones activas...")
cur.execute("""
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = %s AND pid <> pg_backend_pid()
""", (DB_NAME,))

print("Eliminando base de datos...")
cur.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}"')

print("Creando base de datos nueva...")
cur.execute(f'CREATE DATABASE "{DB_NAME}"')
cur.close()
conn.close()

# 2. Conectar a la nueva BD y crear tablas con SQL puro
print("Creando esquema...")
conn2 = psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME)
conn2.autocommit = True
cur2 = conn2.cursor()

# Tabla users
cur2.execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    rol VARCHAR(50) NOT NULL DEFAULT 'admin',
    fecha_creacion TIMESTAMP DEFAULT NOW()
)
""")
print("  + Tabla users creada")

# Enum estado_pago
cur2.execute("""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_pago_enum') THEN
        CREATE TYPE estado_pago_enum AS ENUM ('Activo', 'Pendiente', 'Suspendido');
    END IF;
END$$
""")

# Tabla locales
cur2.execute("""
CREATE TABLE IF NOT EXISTS locales (
    id SERIAL PRIMARY KEY,
    nombre_marca VARCHAR(150) NOT NULL,
    url_instancia VARCHAR(255),
    fecha_lanzamiento DATE NOT NULL DEFAULT CURRENT_DATE,
    version_software VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    fecha_creacion TIMESTAMP DEFAULT NOW(),
    inversion_inicial NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    mensualidad NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    dia_pago INTEGER NOT NULL DEFAULT 1,
    estado_pago estado_pago_enum NOT NULL DEFAULT 'Activo',
    boveda_email VARCHAR(255),
    boveda_password TEXT,
    is_online BOOLEAN NOT NULL DEFAULT TRUE,
    last_checked TIMESTAMP
)
""")
print("  + Tabla locales creada")

# Enum notificacion tipo
cur2.execute("""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notif_tipo_enum') THEN
        CREATE TYPE notif_tipo_enum AS ENUM ('info', 'warning', 'error', 'success');
    END IF;
END$$
""")

# Tabla notificaciones
cur2.execute("""
CREATE TABLE IF NOT EXISTS notificaciones (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    titulo VARCHAR(200) NOT NULL,
    mensaje TEXT NOT NULL,
    tipo notif_tipo_enum NOT NULL DEFAULT 'info',
    destinos TEXT,
    resultados TEXT,
    fecha_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
print("  + Tabla notificaciones creada")

# --- Creación de tabla: facturas ---
print("Creando tabla facturas...")
cur2.execute("""
CREATE TABLE IF NOT EXISTS facturas (
    id SERIAL PRIMARY KEY,
    numero_factura VARCHAR(50) UNIQUE NOT NULL,
    local_id INTEGER NOT NULL REFERENCES locales(id) ON DELETE CASCADE,
    monto NUMERIC(12, 2) NOT NULL,
    fecha_emision DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_vencimiento DATE NOT NULL,
    fecha_pago DATE,
    estado VARCHAR(20) NOT NULL DEFAULT 'Pendiente',
    observaciones TEXT
)
""")
print("  + Tabla facturas creada")

# 3. Crear usuario administrador
admin_hash = generate_password_hash("Zenic2026!")
cur2.execute("""
INSERT INTO users (nombre, email, password_hash, rol)
VALUES (%s, %s, %s, %s)
ON CONFLICT (email) DO NOTHING
""", ("Master Admin - Zenic S.A.S.", "admin@zenic.co", admin_hash, "admin"))
print("  + Usuario admin@zenic.co creado")

cur2.close()
conn2.close()

print("")
print("===========================================================")
print("LISTO. ZenicMaster inicializado correctamente.")
print("  DB:    ZenicMaster en localhost:5432")
print("  Email: admin@zenic.co")
print("  Clave: Zenic2026!")
print("  Arranca con: venv\\Scripts\\python.exe app.py")
print("===========================================================")
