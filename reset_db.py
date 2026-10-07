"""
reset_db.py -- Reinicia la base de datos ZenicMaster limpia.
Ejecutar una sola vez despues de la migracion inicial.
Usa DROP DATABASE ... CASCADE via psycopg2 para forzar limpieza total.
"""
import os
os.environ.setdefault("ZENIC_VAULT_KEY", "W_xjkl0fH5G2giHZFcXnnhklpe8QoP_9O1ngrqUJzcM=")

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_HOST = "localhost"
DB_USER = "postgres"
DB_PASS = "admin123"
DB_NAME = "ZenicMaster"

print("Conectando a PostgreSQL...")
conn = psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, database="postgres")
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

# Terminar conexiones activas a ZenicMaster
print("Terminando conexiones activas a ZenicMaster...")
cur.execute("""
    SELECT pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = %s
    AND pid <> pg_backend_pid()
""", (DB_NAME,))

# Eliminar la BD
print("Eliminando base de datos ZenicMaster...")
cur.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}"')

# Recrear
print("Creando base de datos ZenicMaster nueva...")
cur.execute(f'CREATE DATABASE "{DB_NAME}"')
cur.close()
conn.close()
print("Base de datos recreada.")

# Ahora crear tablas con el nuevo esquema
from app import app
from models import db, User

with app.app_context():
    print("Creando tablas con esquema Zenic Master Control...")
    db.create_all()
    print("Tablas creadas.")

    from werkzeug.security import generate_password_hash
    master = User(
        nombre="Master Admin - Zenic S.A.S.",
        email="admin@zenic.co",
        password_hash=generate_password_hash("Zenic2026!"),
        rol="admin",
    )
    db.session.add(master)
    db.session.commit()
    print("===========================================================")
    print("LISTO. Base de datos ZenicMaster inicializada.")
    print("  Email: admin@zenic.co")
    print("  Clave: Zenic2026!")
    print("===========================================================")
