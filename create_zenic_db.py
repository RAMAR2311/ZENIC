import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

try:
    conn = psycopg2.connect(host='localhost', user='postgres', password='admin123', database='postgres')
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname='ZenicMaster'")
    if not cur.fetchone():
        cur.execute('CREATE DATABASE "ZenicMaster"')
        print('Base de datos ZenicMaster creada exitosamente.')
    else:
        print('La base de datos ZenicMaster ya existe.')
    cur.close()
    conn.close()
except Exception as e:
    print(f'ERROR: {e}')
