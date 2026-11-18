"""
reset_db.py -- Reinicia la base de datos ZenicMaster limpia.
Soporta tanto SQLite (para entorno local directo) como PostgreSQL.
"""
import os
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("ZENIC_VAULT_KEY", "W_xjkl0fH5G2giHZFcXnnhklpe8QoP_9O1ngrqUJzcM=")

db_url = os.environ.get("DATABASE_URL", "sqlite:///zenic_master.db")

print(f"=== Inicializando base de datos ({db_url}) ===")

if db_url.startswith("sqlite:"):
    # Limpiar archivo SQLite si existe
    db_path = db_url.replace("sqlite:///", "")
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Archivo de base de datos {db_path} eliminado.")
else:
    # PostgreSQL
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "postgres")
    DB_PASS = os.environ.get("DB_PASS", "admin123")
    DB_NAME = os.environ.get("DB_NAME", "ZenicMaster")

    print("Conectando a PostgreSQL...")
    conn = psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, database="postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    print(f"Terminando conexiones activas a {DB_NAME}...")
    cur.execute("""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = %s
        AND pid <> pg_backend_pid()
    """, (DB_NAME,))

    print(f"Eliminando base de datos {DB_NAME}...")
    cur.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}"')

    print(f"Creando base de datos {DB_NAME} nueva...")
    cur.execute(f'CREATE DATABASE "{DB_NAME}"')
    cur.close()
    conn.close()
    print("Base de datos recreada.")

# Crear tablas con el esquema de Zenic Master Control
from app import create_app
from models import db, User, Tesoreria

app = create_app()

with app.app_context():
    print("Creando tablas con esquema Zenic Master Control...")
    db.create_all()
    print("Tablas creadas exitosamente.")

    from werkzeug.security import generate_password_hash
    master = User(
        nombre="Master Admin - Zenic S.A.S.",
        email="admin@zenic.co",
        password_hash=generate_password_hash("Zenic2026!"),
        rol="admin",
    )
    db.session.add(master)

    # Inicializar tesorería por defecto
    tesoreria = Tesoreria(saldo_banco=0, caja_menor=0)
    db.session.add(tesoreria)

    db.session.commit()
    print("===========================================================")
    print("LISTO. Base de datos ZenicMaster inicializada.")
    print("  Email: admin@zenic.co")
    print("  Clave: Zenic2026!")
    print("===========================================================")
