"""
models.py — Zenic Master Control
=================================
Estructura de datos LIMPIA para el panel administrativo centralizado.
Contiene: User (operadores del panel), Local (instancias de clientes),
Notificacion (mensajes), ObligacionFinanciera (deudas) y Negociacion (gestión de deudas).
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import pytz

db = SQLAlchemy()


def obtener_hora_bogota():
    """Retorna la hora actual en la zona horaria de Colombia (Bogotá)."""
    return datetime.now(pytz.timezone("America/Bogota")).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# MODELO: User (Operadores del Master Control)
# ─────────────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(50), nullable=False, default="admin")
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)



# ─────────────────────────────────────────────────────────────────────────────
# MODELO: Local (Instancias de Clientes - Tabla Maestra)
# ─────────────────────────────────────────────────────────────────────────────
class Local(db.Model):
    """
    Representa una instancia/local cliente gestionada por Zenic S.A.S.
    Cada registro es un CRM desplegado para un cliente.
    """

    __tablename__ = "locales"

    # Identificación
    id = db.Column(db.Integer, primary_key=True)
    nombre_marca = db.Column(db.String(150), nullable=False)          # Ej: Tekfix, Sarotex
    url_instancia = db.Column(db.String(255), nullable=True)          # URL del CRM cliente

    # Fechas y Versión
    fecha_lanzamiento = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    version_software = db.Column(db.String(20), nullable=False, default="1.0.0")
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

    # Finanzas
    inversion_inicial = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    mensualidad = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    dia_pago = db.Column(db.Integer, nullable=False, default=1)       # Día del mes (1–31)

    # Estado de Pago — Semáforo
    estado_pago = db.Column(
        db.Enum("Activo", "Pendiente", "Suspendido", name="estado_pago_enum"),
        nullable=False,
        default="Activo",
    )

    # Bóveda de Credenciales (encriptadas con Fernet)
    boveda_email = db.Column(db.String(255), nullable=True)           # Email admin (cifrado)
    boveda_password = db.Column(db.Text, nullable=True)               # Password admin (cifrado)

    # Uptime Tracking
    is_online = db.Column(db.Boolean, default=True, nullable=False)
    last_checked = db.Column(db.DateTime, nullable=True)


    # ── Propiedades de utilidad ──────────────────────────────────────────────

    @property
    def dias_para_pago(self):
        """
        Calcula cuántos días faltan para la próxima fecha de corte.
        """
        hoy = obtener_hora_bogota().date()
        import calendar
        from datetime import date
        
        max_dia = calendar.monthrange(hoy.year, hoy.month)[1]
        dia_efectivo = min(self.dia_pago, max_dia)
        fecha_corte = date(hoy.year, hoy.month, dia_efectivo)
        
        dias = (fecha_corte - hoy).days
        
        # Si ya pasó la fecha de corte este mes y el local está Activo,
        # su próximo corte es el mes siguiente.
        if dias < 0 and self.estado_pago == "Activo":
            mes_sig = hoy.month + 1 if hoy.month < 12 else 1
            ano_sig = hoy.year if hoy.month < 12 else hoy.year + 1
            max_dia_sig = calendar.monthrange(ano_sig, mes_sig)[1]
            dia_efectivo_sig = min(self.dia_pago, max_dia_sig)
            fecha_corte_sig = date(ano_sig, mes_sig, dia_efectivo_sig)
            dias = (fecha_corte_sig - hoy).days
            
        return dias

    @property
    def semaforo(self):
        """
        Devuelve una clase CSS para colorear el semáforo de pago:
          - 'semaforo-verde'  → Activo y más de 5 días para el corte
          - 'semaforo-amarillo' → Activo pero corte en ≤5 días
          - 'semaforo-rojo'   → Pendiente, Suspendido o ya vencido
        """
        if self.estado_pago == "Suspendido":
            return "semaforo-rojo"
        if self.estado_pago == "Pendiente":
            return "semaforo-rojo"
        dias = self.dias_para_pago
        if dias < 0:
            return "semaforo-rojo"
        if dias <= 5:
            return "semaforo-amarillo"
        return "semaforo-verde"

    @property
    def semaforo_label(self):
        mapa = {
            "semaforo-verde": "Al día",
            "semaforo-amarillo": "Por vencer",
            "semaforo-rojo": "Atención",
        }
        return mapa.get(self.semaforo, "—")


# ─────────────────────────────────────────────────────────────────────────────
# MODELO: Notificacion (Mensajes enviados a instancias)
# ─────────────────────────────────────────────────────────────────────────────
class Notificacion(db.Model):
    """
    Registro de cada mensaje/alerta enviado a una o más instancias.
    Permite auditar el historial de comunicaciones.
    """

    __tablename__ = "notificaciones"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    tipo = db.Column(
        db.Enum("info", "warning", "error", "success", name="notif_tipo_enum"),
        nullable=False,
        default="info",
    )
    destinos = db.Column(db.Text, nullable=True)   # JSON con IDs de locales destino
    resultados = db.Column(db.Text, nullable=True)  # JSON con respuestas de cada webhook
    fecha_envio = db.Column(db.DateTime, default=obtener_hora_bogota)

    autor = db.relationship("User", backref="notificaciones_enviadas", lazy=True)


# ─────────────────────────────────────────────────────────────────────────────
# MODELO: Factura (Gestión de Ingresos / Soportes de Pago)
# ─────────────────────────────────────────────────────────────────────────────
class Factura(db.Model):
    __tablename__ = 'facturas'

    id = db.Column(db.Integer, primary_key=True)
    numero_factura = db.Column(db.String(50), unique=True, nullable=False)
    local_id = db.Column(db.Integer, db.ForeignKey('locales.id', ondelete='CASCADE'), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    fecha_emision = db.Column(db.Date, nullable=False, default=obtener_hora_bogota)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    fecha_pago = db.Column(db.Date, nullable=True)
    estado = db.Column(
        db.Enum("Pendiente", "Pagado", "Vencido", name="estado_factura_enum"),
        nullable=False,
        default="Pendiente"
    )
    observaciones = db.Column(db.Text, nullable=True)

    # Relación bidireccional
    local = db.relationship('Local', backref=db.backref('facturas_list', lazy=True, cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<Factura {self.numero_factura} - {self.estado}>"


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS: Finanzas (Ingresos, Gastos, Presupuestos)
# ─────────────────────────────────────────────────────────────────────────────
class Ingreso(db.Model):
    __tablename__ = 'ingresos'
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(255), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=obtener_hora_bogota)
    categoria = db.Column(db.String(100), nullable=False, default="General")
    
class Gasto(db.Model):
    __tablename__ = 'gastos'
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(255), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=obtener_hora_bogota)
    categoria = db.Column(db.String(100), nullable=True)
    tipo_costo = db.Column(db.String(50), nullable=False, default="Gasto Administrativo")
    presupuesto_id = db.Column(db.Integer, db.ForeignKey('presupuestos_area.id'), nullable=True)
    
    presupuesto = db.relationship('PresupuestoArea', backref=db.backref('gastos', lazy=True))

class PresupuestoArea(db.Model):
    __tablename__ = 'presupuestos_area'
    id = db.Column(db.Integer, primary_key=True)
    nombre_area = db.Column(db.String(150), nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    ano = db.Column(db.Integer, nullable=False)
    limite_gastos = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    
    __table_args__ = (db.UniqueConstraint('nombre_area', 'mes', 'ano', name='_area_mes_ano_uc'),)

class Tesoreria(db.Model):
    __tablename__ = 'tesoreria'
    id = db.Column(db.Integer, primary_key=True)
    saldo_banco = db.Column(db.Numeric(15, 2), nullable=False, default=0.00)
    caja_menor = db.Column(db.Numeric(15, 2), nullable=False, default=0.00)

class Personal(db.Model):
    __tablename__ = 'personal'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    cargo = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    estado = db.Column(db.String(20), nullable=False, default="Activo")
    fecha_ingreso = db.Column(db.Date, nullable=False, default=obtener_hora_bogota)

class ActivoFijo(db.Model):
    __tablename__ = 'activos_fijos'
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Numeric(15, 2), nullable=False, default=0.00)
    imei = db.Column(db.String(100), nullable=True)
    documento_ruta = db.Column(db.String(255), nullable=True)
    personal_id = db.Column(db.Integer, db.ForeignKey('personal.id'), nullable=True)
    fecha_adquisicion = db.Column(db.Date, nullable=False, default=obtener_hora_bogota)
    
    personal = db.relationship('Personal', backref=db.backref('equipos', lazy=True))
