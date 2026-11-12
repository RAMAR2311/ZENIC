"""
app.py -- Zenic Master Control
================================
Punto de entrada del panel administrativo centralizado de Zenic S.A.S.
"""

import os
from dotenv import load_dotenv

# Cargar variables de entorno ANTES de importar modelos (necesario para VAULT KEY)
load_dotenv()

from flask import Flask, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

from models import db, User
from flask_apscheduler import APScheduler

scheduler = APScheduler()


def create_app():
    app = Flask(__name__)

    # -- Configuracion --------------------------------------------------------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "zenic-master-dev-key-2026")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:admin123@localhost:5432/ZenicMaster"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'documentos')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    TICKETS_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'tickets')
    os.makedirs(TICKETS_UPLOAD_FOLDER, exist_ok=True)
    app.config['TICKETS_UPLOAD_FOLDER'] = TICKETS_UPLOAD_FOLDER

    # -- Extensiones ----------------------------------------------------------
    db.init_app(app)
    Migrate(app, db)
    CSRFProtect(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth_bp.login"
    login_manager.login_message = "Por favor inicia sesion para continuar."
    login_manager.init_app(app)

    # Iniciar scheduler solo en el proceso principal (evita doble ejecución con reloaders de Flask y workers múltiples WSGI)
    scheduler_enabled = os.environ.get("ENABLE_SCHEDULER", "true").lower() in ("true", "1", "yes")
    is_main_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug

    if scheduler_enabled and is_main_process and not scheduler.running:
        scheduler.init_app(app)
        from uptime_monitor import check_locales_health
        scheduler.add_job(
            id="uptime_monitor",
            func=check_locales_health,
            args=[app],
            trigger="interval",
            minutes=5,
            replace_existing=True,
        )
        scheduler.start()

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.locales import locales_bp
    from routes.ingresos import ingresos_bp
    from routes.finanzas import finanzas_bp
    from routes.operaciones import operaciones_bp
    from routes.dashboard import dashboard_bp
    from routes.ti import ti_bp
    from routes.marketing import marketing_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="")
    app.register_blueprint(locales_bp, url_prefix="")
    app.register_blueprint(ingresos_bp, url_prefix="")
    app.register_blueprint(finanzas_bp, url_prefix="")
    app.register_blueprint(operaciones_bp, url_prefix="/operaciones")
    app.register_blueprint(ti_bp)
    app.register_blueprint(marketing_bp)

    # -- Filtros de Plantilla -------------------------------------------------
    @app.template_filter("fromjson")
    def fromjson_filter(value):
        import json
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}

    @app.template_filter("cop")
    def cop_filter(value):
        if value is None:
            return "$0"
        try:
            formatted = "{:,.0f}".format(float(value)).replace(",", ".")
            return f"${formatted}"
        except (ValueError, TypeError):
            return value

    @app.template_filter("fecha_corta")
    def fecha_corta_filter(value):
        if value is None:
            return "--"
        try:
            if hasattr(value, "strftime"):
                return value.strftime("%d/%m/%Y")
            return str(value)
        except Exception:
            return str(value)

    # -- Rutas PWA (Root Scope) -----------------------------------------------
    from flask import send_from_directory

    @app.route("/sw.js")
    def service_worker():
        response = send_from_directory(app.static_folder, "sw.js")
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/manifest.json")
    def manifest():
        response = send_from_directory(app.static_folder, "manifest.json", mimetype="application/manifest+json")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")

    @app.route("/offline")
    def offline():
        return render_template("offline.html")

    # -- Ruta Raiz ------------------------------------------------------------
    @app.route("/")
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for("auth_bp.login"))
        return redirect(url_for("dashboard_bp.master"))

    return app


# Crear la app en el scope del modulo para que Flask CLI y gunicorn lo encuentren
app = create_app()

if __name__ == "__main__":
    # La inicializacion de BD se hace en reset_db.py (una sola vez)
    # Aqui solo levantamos el servidor
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.run(debug=True, port=5000)
