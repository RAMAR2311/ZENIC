"""
seed_test_data.py — Redirige a seed_ficticios.py y seed_bloques.py
(Mantiene compatibilidad con el esquema actual de Zenic Master Control).
"""
import subprocess
import sys


def seed_test_data():
    subprocess.run([sys.executable, "seed_ficticios.py"], check=True)
    subprocess.run([sys.executable, "seed_bloques.py"], check=True)


if __name__ == "__main__":
    seed_test_data()

