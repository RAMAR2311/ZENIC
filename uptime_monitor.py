"""
uptime_monitor.py — Monitoreo de Disponibilidad Concurrente
============================================================
Verifica el estado HTTP (Online/Offline) de cada instancia cliente (Local)
de manera concurrente utilizando un ThreadPoolExecutor para evitar bloqueos
y reducir drásticamente los tiempos de respuesta.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pytz
import requests

TIMEOUT_SECONDS = 8
MAX_WORKERS = 10


def _check_single_url(url: str) -> bool:
    """Verifica si una URL responde con estado < 400."""
    try:
        # Usamos stream=True y un header User-Agent para evitar bloqueos por WAF comunes
        headers = {
            "User-Agent": "ZenicMaster-HealthCheck/1.0",
            "Accept": "*/*"
        }
        resp = requests.get(url, timeout=TIMEOUT_SECONDS, headers=headers, allow_redirects=True, stream=True)
        return resp.status_code < 400
    except requests.RequestException:
        return False


def check_locales_health(app):
    """
    Verifica concurrentemente la salud de las instancias de clientes.
    Se ejecuta como tarea periódica en APScheduler.
    """
    with app.app_context():
        from models import db, Local

        # 1. Obtener los locales activos
        locales = Local.query.all()
        if not locales:
            return

        hora_actual = datetime.now(pytz.timezone("America/Bogota")).replace(tzinfo=None)

        # 2. Filtrar los que tienen URL válida para chequear en paralelo
        items_to_check = []
        locales_by_id = {}

        for local in locales:
            locales_by_id[local.id] = local
            if local.url_instancia and local.url_instancia.strip():
                url = local.url_instancia.strip().rstrip("/")
                items_to_check.append((local.id, url))
            else:
                # Si no tiene URL configurada, se considera neutro / online
                local.is_online = True
                local.last_checked = hora_actual

        # 3. Ejecución concurrente
        if items_to_check:
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(items_to_check))) as executor:
                future_to_id = {
                    executor.submit(_check_single_url, url): local_id
                    for local_id, url in items_to_check
                }
                for future in as_completed(future_to_id):
                    local_id = future_to_id[future]
                    is_online = False
                    try:
                        is_online = future.result()
                    except Exception:
                        is_online = False

                    local_obj = locales_by_id.get(local_id)
                    if local_obj:
                        local_obj.is_online = is_online
                        local_obj.last_checked = hora_actual

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
