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
    fecha_inicio_facturacion = db.Column(db.Date, nullable=True)       # Desde cuándo empieza a correr facturación en sistema
    version_software = db.Column(db.String(20), nullable=False, default="1.0.0")
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

    # Modalidad de Plan e Instancia
    tipo_plan = db.Column(db.String(30), nullable=False, default="Mensual") # 'Mensual', 'Anual', 'Interna'
    telefono_cobro = db.Column(db.String(50), nullable=True) # WhatsApp o teléfono de cobro

    # Finanzas
    inversion_inicial = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    mensualidad = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    valor_anualidad = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
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
    def proxima_fecha_corte(self):
        """Calcula la fecha exacta del próximo vencimiento/corte sin depender de librerías externas."""
        hoy = obtener_hora_bogota().date()
        import calendar
        from datetime import date

        def _add_months(d, months):
            total_m = (d.year * 12 + (d.month - 1)) + months
            ny = total_m // 12
            nm = (total_m % 12) + 1
            max_d = calendar.monthrange(ny, nm)[1]
            return date(ny, nm, min(d.day, max_d))

        if getattr(self, "tipo_plan", "Mensual") == "Interna":
            return None

        base_lanz = self.fecha_lanzamiento.date() if hasattr(self.fecha_lanzamiento, "date") else (self.fecha_lanzamiento or hoy)

        if getattr(self, "tipo_plan", "Mensual") == "Anual":
            if self.fecha_inicio_facturacion:
                proximo = self.fecha_inicio_facturacion
                while proximo < hoy:
                    proximo = _add_months(proximo, 12)
                return proximo
            proximo = _add_months(base_lanz, 12)
            while proximo < hoy:
                proximo = _add_months(proximo, 12)
            return proximo

        # Plan Mensual
        if self.fecha_inicio_facturacion:
            fecha_min_primer_cobro = self.fecha_inicio_facturacion
        else:
            fecha_min_primer_cobro = _add_months(base_lanz, 1)

        ref_date = max(hoy, fecha_min_primer_cobro)
        max_dia = calendar.monthrange(ref_date.year, ref_date.month)[1]
        dia_pago_val = int(self.dia_pago or 1)
        dia_efectivo = min(max(1, dia_pago_val), max_dia)
        corte_ref = date(ref_date.year, ref_date.month, dia_efectivo)

        if corte_ref < fecha_min_primer_cobro or corte_ref < hoy:
            mes_sig = ref_date.month + 1 if ref_date.month < 12 else 1
            ano_sig = ref_date.year if ref_date.month < 12 else ref_date.year + 1
            max_dia_sig = calendar.monthrange(ano_sig, mes_sig)[1]
            return date(ano_sig, mes_sig, min(max(1, dia_pago_val), max_dia_sig))

        return corte_ref

    @property
    def dias_para_pago(self):
        """
        Calcula cuántos días faltan para la próxima fecha de corte.
        """
        if self.tipo_plan == "Interna":
            return 999
        hoy = obtener_hora_bogota().date()
        prox = self.proxima_fecha_corte
        if not prox:
            return 999
        return (prox - hoy).days

    @property
    def semaforo(self):
        """
        Devuelve una clase CSS para colorear el semáforo de pago:
          - 'semaforo-azul'   → Instancia interna propia (sin cobro)
          - 'semaforo-verde'  → Activo y más de 5 días para el corte
          - 'semaforo-amarillo' → Activo pero corte en ≤5 días
          - 'semaforo-rojo'   → Pendiente, Suspendido o ya vencido
        """
        if self.tipo_plan == "Interna":
            return "semaforo-azul"
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
        if self.tipo_plan == "Interna":
            return "Interna"
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
    tipo_cobro = db.Column(db.String(30), nullable=False, default="Mensualidad") # 'Instalación', 'Mensualidad', 'Anualidad', 'Otro'
    fecha_emision = db.Column(db.Date, nullable=False, default=obtener_hora_bogota)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    fecha_pago = db.Column(db.Date, nullable=True)
    estado = db.Column(
        db.Enum("Pendiente", "Pagado", "Vencido", name="estado_factura_enum"),
        nullable=False,
        default="Pendiente"
    )
    cuenta_destino = db.Column(db.String(30), nullable=True) # 'Nu', 'Nequi', 'Bancolombia'
    validado_por_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Trazabilidad de recordatorios de mora
    ultimo_recordatorio = db.Column(db.DateTime, nullable=True)
    recordatorio_enviado_por_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    total_recordatorios = db.Column(db.Integer, nullable=False, default=0)

    observaciones = db.Column(db.Text, nullable=True)

    # Relaciones
    local = db.relationship('Local', backref=db.backref('facturas_list', lazy=True, cascade="all, delete-orphan"))
    validado_por = db.relationship('User', foreign_keys=[validado_por_id], backref=db.backref('facturas_validadas', lazy=True))
    recordatorio_por = db.relationship('User', foreign_keys=[recordatorio_enviado_por_id], backref=db.backref('recordatorios_enviados', lazy=True))

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
    cuenta_origen = db.Column(db.String(30), nullable=True, default="Nu") # 'Nu', 'Nequi', 'Banco', 'Caja Menor', 'Otra'
    comprobante_ruta = db.Column(db.String(255), nullable=True)            # Foto o PDF del comprobante del gasto
    presupuesto_id = db.Column(db.Integer, db.ForeignKey('presupuestos_area.id'), nullable=True)
    
    presupuesto = db.relationship('PresupuestoArea', backref=db.backref('gastos', lazy=True))


class CostoFijo(db.Model):
    """
    Costos Fijos Mensuales y Obligaciones Recurrentes de Zenic (incluyendo Préstamos de la empresa,
    Servidores, Licencias, Servicios, etc.).
    Permite dejarlos configurados de forma permanente y validarlos cada mes cuando ya se pagaron,
    guardando el comprobante y descontando de la cuenta seleccionada.
    """
    __tablename__ = 'costos_fijos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(180), nullable=False)             # Ej: Cuota Préstamo Empresarial, Servidores AWS
    categoria = db.Column(db.String(60), nullable=False, default="Operativo") # 'Préstamos', 'Servidores / Cloud', 'Software / Licencias', 'Servicios / Nómina', 'Otro'
    tipo_costo = db.Column(db.String(50), nullable=False, default="Costo Directo") # 'Costo Directo', 'Costo Indirecto', 'Gasto Administrativo', 'Pago de Préstamo'
    monto_mensual = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    dia_pago = db.Column(db.Integer, nullable=True, default=1)     # Día estimado de pago del mes (1-31)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    # Control del último pago validado
    ultimo_mes_pagado = db.Column(db.Integer, nullable=True)
    ultimo_ano_pagado = db.Column(db.Integer, nullable=True)
    ultima_fecha_pago = db.Column(db.Date, nullable=True)
    ultima_cuenta_origen = db.Column(db.String(40), nullable=True)
    ultimo_comprobante = db.Column(db.String(255), nullable=True)
    observaciones = db.Column(db.String(255), nullable=True)

    def pagado_en_periodo(self, mes, ano):
        return (self.ultimo_mes_pagado == mes) and (self.ultimo_ano_pagado == ano)

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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    usuario = db.relationship('User', backref=db.backref('personal_perfil', uselist=False, lazy=True))

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


# ─────────────────────────────────────────────────────────────────────────────
# MODELO: TicketCambio (Soporte TI & Solicitudes de Clientes)
# ─────────────────────────────────────────────────────────────────────────────
class TicketCambio(db.Model):
    """
    Gestión de tickets de soporte técnico, correcciones y cambios solicitados
    por Operaciones para clientes (Locales) y atendidos por el equipo de TI.
    """
    __tablename__ = "tickets_cambio"

    id = db.Column(db.Integer, primary_key=True)
    local_id = db.Column(db.Integer, db.ForeignKey("locales.id", ondelete="SET NULL"), nullable=True)
    solicitante_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    asignado_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    categoria = db.Column(
        db.String(50),
        nullable=False,
        default="Soporte", # Soporte, Error de Sistema, Nueva Función, Despliegue, Base de Datos
    )
    prioridad = db.Column(
        db.String(20),
        nullable=False,
        default="Media", # Baja, Media, Alta, Urgente
    )
    estado = db.Column(
        db.String(30),
        nullable=False,
        default="Pendiente", # Pendiente, En Desarrollo, Por Validar, Requiere Ajustes, Resuelto, Cancelado
    )
    notas_resolucion = db.Column(db.Text, nullable=True)       # Comentario dejado por el asignado al solucionarlo
    notas_validacion = db.Column(db.Text, nullable=True)       # Comentario dejado por quien lo asignó al validar o pedir revisión
    validado_por_solicitante = db.Column(db.Boolean, default=False, nullable=False)
    adjunto_ruta = db.Column(db.Text, nullable=True) # Nombre de archivo o lista en formato JSON de múltiples archivos
    adjunto_tipo = db.Column(db.String(50), nullable=True)  # 'imagen', 'video', o 'multiple'

    @property
    def adjuntos(self):
        """Retorna una lista normalizada de diccionarios [{'ruta': ..., 'tipo': ...}]"""
        if not self.adjunto_ruta:
            return []
        import json
        try:
            # Intenta parsear como JSON si son múltiples
            data = json.loads(self.adjunto_ruta)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        # Si era un solo archivo antiguo guardado como string simple
        return [{"ruta": self.adjunto_ruta, "tipo": self.adjunto_tipo or "imagen"}]
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)
    fecha_actualizacion = db.Column(db.DateTime, default=obtener_hora_bogota, onupdate=obtener_hora_bogota)
    fecha_cierre = db.Column(db.DateTime, nullable=True)

    local = db.relationship("Local", backref=db.backref("tickets", lazy=True))
    solicitante = db.relationship("User", foreign_keys=[solicitante_id], backref=db.backref("tickets_solicitados", lazy=True))
    asignado = db.relationship("User", foreign_keys=[asignado_id], backref=db.backref("tickets_asignados", lazy=True))


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS: Marketing (Contenido, Grabaciones, Recursos)
# ─────────────────────────────────────────────────────────────────────────────
class ContenidoMarketing(db.Model):
    """
    Planificación de contenidos para redes sociales oficiales de Zenic.
    """
    __tablename__ = "marketing_contenidos"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    red_social = db.Column(db.String(50), nullable=False) # Instagram, TikTok, LinkedIn, YouTube, Facebook, Multi-Plataforma
    formato = db.Column(db.String(50), nullable=False, default="Reel") # Reel, TikTok, Carrusel, Historia, Post, Video Largo
    estado = db.Column(
        db.String(30),
        nullable=False,
        default="Idea", # Idea, En Guion, Listo para Grabar, En Edicion, Aprobado, Publicado
    )
    fecha_programada = db.Column(db.Date, nullable=True)
    copy = db.Column(db.Text, nullable=True)
    link_recurso = db.Column(db.String(500), nullable=True) # Enlace a Drive, Canva, etc.
    autor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

    autor = db.relationship("User", backref=db.backref("contenidos_creados", lazy=True))


class SesionGrabacion(db.Model):
    """
    Agenda de grabaciones y producciones audiovisuales del equipo de marketing.
    """
    __tablename__ = "marketing_grabaciones"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    fecha_grabacion = db.Column(db.DateTime, nullable=False)
    locacion = db.Column(db.String(200), nullable=False) # Oficina Zenic, Local Cliente, Estudio, Remoto
    objetivo = db.Column(db.Text, nullable=True)
    participantes = db.Column(db.String(255), nullable=True) # Personal o actores
    equipos_requeridos = db.Column(db.Text, nullable=True) # Cámaras, luces, trípodes
    estado = db.Column(
        db.String(30),
        nullable=False,
        default="Programada", # Programada, Realizada, Cancelada, Pospuesta
    )
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)


# ─────────────────────────────────────────────────────────────────────────────
# MODELO: Documento (Gestión Documental: Zenic, Legal Clientes, Manuales)
# ─────────────────────────────────────────────────────────────────────────────
class Documento(db.Model):
    """
    Gestor documental centralizado de Zenic:
    - zenic: Documentación interna, procesos, arquitectura, actas
    - cliente: Documentación legal de clientes (RUT, Cámara de Comercio, Contratos, etc.)
    - manual: Manuales de usuario, instalación y guías de sistemas
    """
    __tablename__ = "documentos"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    tipo = db.Column(
        db.String(50),
        nullable=False,
        default="zenic" # zenic, cliente, manual
    )
    categoria = db.Column(db.String(100), nullable=False, default="General")
    # Asociado a cliente si tipo == 'cliente' o manual específico
    local_id = db.Column(db.Integer, db.ForeignKey("locales.id", ondelete="CASCADE"), nullable=True)
    
    # Archivo físico en disco
    archivo_ruta = db.Column(db.String(255), nullable=True)
    archivo_nombre_original = db.Column(db.String(255), nullable=True)
    archivo_tamano = db.Column(db.Integer, nullable=True, default=0) # en bytes
    archivo_extension = db.Column(db.String(20), nullable=True)
    
    # Enlace externo opcional (Drive, Notion, etc.)
    enlace_externo = db.Column(db.String(500), nullable=True)
    
    version = db.Column(db.String(20), nullable=False, default="1.0")
    autor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)
    fecha_actualizacion = db.Column(db.DateTime, default=obtener_hora_bogota, onupdate=obtener_hora_bogota)

    local = db.relationship("Local", backref=db.backref("documentos", lazy=True, cascade="all, delete-orphan"))
    autor = db.relationship("User", backref=db.backref("documentos_creados", lazy=True))

    @property
    def tamano_legible(self):
        if not self.archivo_tamano:
            return "—"
        tam = self.archivo_tamano
        if tam < 1024:
            return f"{tam} B"
        elif tam < 1024 * 1024:
            return f"{tam / 1024:.1f} KB"
        else:
            return f"{tam / (1024 * 1024):.1f} MB"

    @property
    def icono_fa(self):
        ext = (self.archivo_extension or "").lower()
        if ext == "pdf":
            return "fa-file-pdf text-danger"
        elif ext in ["doc", "docx"]:
            return "fa-file-word text-primary"
        elif ext in ["xls", "xlsx", "csv"]:
            return "fa-file-excel text-success"
        elif ext in ["ppt", "pptx"]:
            return "fa-file-powerpoint text-warning"
        elif ext in ["zip", "rar", "7z", "tar", "gz"]:
            return "fa-file-zipper text-secondary"
        elif ext in ["png", "jpg", "jpeg", "webp", "svg"]:
            return "fa-file-image text-info"
        elif self.enlace_externo:
            return "fa-link text-primary"
        return "fa-file-lines text-muted"

    @property
    def tipo_label(self):
        mapa = {
            "zenic": "Zenic Corporativo",
            "cliente": "Legal Cliente",
            "manual": "Manual de Sistema"
        }
        return mapa.get(self.tipo, self.tipo.capitalize())


# ─────────────────────────────────────────────────────────────────────────────
# MODELO: CorteMetricaSocial (Crecimiento y Métricas de Redes Sociales)
# ─────────────────────────────────────────────────────────────────────────────
class CorteMetricaSocial(db.Model):
    """
    Registro periódico de métricas de crecimiento en redes sociales oficiales
    (Instagram, TikTok, LinkedIn, Facebook, Consolidado).
    Permite calcular variaciones porcentuales, Engagement Rate y evolución temporal.
    """
    __tablename__ = "marketing_metricas"

    id = db.Column(db.Integer, primary_key=True)
    red_social = db.Column(db.String(50), nullable=False, default="Instagram") # Instagram, TikTok, LinkedIn, Facebook, Consolidado
    periodo_tipo = db.Column(db.String(30), nullable=False, default="Semanal") # Semanal, Quincenal, Mensual
    etiqueta_periodo = db.Column(db.String(150), nullable=False) # Ej: "Semana 46 - #LaOtraCaraDelMostrador"
    fecha_corte = db.Column(db.Date, nullable=False, default=obtener_hora_bogota)

    # Métricas base
    seguidores_totales = db.Column(db.Integer, nullable=False, default=0)
    visualizaciones = db.Column(db.Integer, nullable=False, default=0)
    alcance = db.Column(db.Integer, nullable=False, default=0)
    interacciones = db.Column(db.Integer, nullable=False, default=0)

    # Campos de valor comercial
    link_top_post = db.Column(db.String(500), nullable=True)
    leads_generados = db.Column(db.Integer, nullable=False, default=0)
    notas_campana = db.Column(db.Text, nullable=True)

    autor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

    autor = db.relationship("User", backref=db.backref("metricas_sociales_creadas", lazy=True))

    @property
    def engagement_rate(self):
        if self.alcance and self.alcance > 0:
            return round((float(self.interacciones) / float(self.alcance)) * 100, 2)
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# MODELO: BitacoraCliente (Historial de Cambios, Pagos y Eventos por Cliente)
# ─────────────────────────────────────────────────────────────────────────────
class BitacoraCliente(db.Model):
    """
    Registra cronológicamente todos los cambios y eventos realizados en un cliente:
    - Creación/modificación de condiciones comerciales o fechas de facturación
    - Pagos validados y facturas emitidas
    - Tickets de soporte o cambios técnicos realizados
    - Notas manuales de seguimiento del equipo
    """
    __tablename__ = "bitacora_clientes"

    id = db.Column(db.Integer, primary_key=True)
    local_id = db.Column(db.Integer, db.ForeignKey("locales.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tipo = db.Column(db.String(40), nullable=False, default="Cambio") # 'Pago', 'Ticket', 'Cambio', 'Configuración', 'Nota'
    titulo = db.Column(db.String(200), nullable=False)
    detalle = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=obtener_hora_bogota)

    local = db.relationship("Local", backref=db.backref("bitacora_list", lazy=True, cascade="all, delete-orphan"))
    usuario = db.relationship("User", backref=db.backref("bitacoras_registradas", lazy=True))


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS: Prestamo y AbonoPrestamo (Cuentas por Cobrar / Préstamos a Favor de Zenic)
# ─────────────────────────────────────────────────────────────────────────────
class Prestamo(db.Model):
    """
    Préstamos o créditos otorgados por Zenic (anteriores o nuevos) que constituyen
    un activo / cuenta por cobrar a favor de la empresa.
    Permite llevar el control del monto prestado, abonos recibidos y saldo pendiente.
    """
    __tablename__ = "prestamos"

    id = db.Column(db.Integer, primary_key=True)
    deudor = db.Column(db.String(150), nullable=False)            # Nombre de la persona, socio o cliente
    local_id = db.Column(db.Integer, db.ForeignKey("locales.id", ondelete="SET NULL"), nullable=True)
    concepto = db.Column(db.String(255), nullable=False)          # Motivo o detalle del préstamo
    monto_total = db.Column(db.Numeric(15, 2), nullable=False)    # Capital total prestado
    fecha_prestamo = db.Column(db.Date, nullable=True)            # Opcional (None para préstamos antiguos sin fecha)
    fecha_vencimiento = db.Column(db.Date, nullable=True)         # Opcional
    es_historico = db.Column(db.Boolean, default=True, nullable=False) # True si se prestó antes del corte (no resta caja actual)
    estado = db.Column(db.String(30), nullable=False, default="Activo") # 'Activo', 'Pagado'
    observaciones = db.Column(db.Text, nullable=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

    local = db.relationship("Local", backref=db.backref("prestamos_list", lazy=True))
    creado_por = db.relationship("User", backref=db.backref("prestamos_creados", lazy=True))
    abonos = db.relationship("AbonoPrestamo", backref="prestamo", lazy=True, cascade="all, delete-orphan", order_by="AbonoPrestamo.fecha_abono.desc()")

    @property
    def total_abonado(self):
        return sum(float(a.monto) for a in self.abonos)

    @property
    def saldo_pendiente(self):
        restante = float(self.monto_total) - self.total_abonado
        return max(0.0, restante)

    @property
    def porcentaje_pagado(self):
        if not self.monto_total or float(self.monto_total) <= 0:
            return 0.0
        return min(100.0, round((self.total_abonado / float(self.monto_total)) * 100, 1))


class AbonoPrestamo(db.Model):
    """
    Registro de cada abono o pago parcial/total recibido sobre un préstamo a favor de Zenic,
    incluyendo la cuenta destino donde entró el dinero y el archivo del comprobante.
    """
    __tablename__ = "abonos_prestamo"

    id = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey("prestamos.id", ondelete="CASCADE"), nullable=False)
    monto = db.Column(db.Numeric(15, 2), nullable=False)
    fecha_abono = db.Column(db.Date, nullable=False, default=obtener_hora_bogota)
    cuenta_destino = db.Column(db.String(40), nullable=False, default="Nu") # 'Nu', 'Nequi', 'Banco', 'Caja Menor'
    comprobante_ruta = db.Column(db.String(255), nullable=True)   # Imagen o PDF del comprobante de pago
    observacion = db.Column(db.String(255), nullable=True)
    registrado_por_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=obtener_hora_bogota)

    registrado_por = db.relationship("User", backref=db.backref("abonos_prestamos_registrados", lazy=True))



