import requests
import pytz
from datetime import datetime

def check_locales_health(app):
    """
    Verifica el estado HTTP (Online/Offline) de cada instancia de cliente (Local).
    Se ejecuta de forma recurrente (por defecto cada 5 min).
    """
    with app.app_context():
        from models import db, Local
        # Consultamos todos los locales
        locales = Local.query.all()
        
        for local in locales:
            if local.url_instancia:
                url = local.url_instancia.strip().rstrip('/')
                try:
                    # Hacemos un GET request de máximo 10s
                    resp = requests.get(url, timeout=10)
                    local.is_online = (resp.status_code < 400)
                except requests.RequestException:
                    local.is_online = False
            else:
                # Si no tiene URL configurada, lo consideramos en línea o neutro
                local.is_online = True
                
            # Actualizar última vez checado (hora Colombia)
            local.last_checked = datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)
            
        db.session.commit()
