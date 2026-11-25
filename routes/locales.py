"""
routes/locales.py — Blueprint: Gestión de Locales (Instancias)
===============================================================
Endpoints del Zenic Master Control para:
  - CRUD de Locales
  - Dashboard MRR
  - Sistema de Notificaciones (Webhook)
  - Bóveda de credenciales (encriptada)
"""

import json
import calendar
from datetime import datetime, date

import requests
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
)
from flask_login import login_required, current_user
from sqlalchemy import func

from models import db, Local, Notificacion, Factura, TicketCambio, BitacoraCliente, User, obtener_hora_bogota
from crypto_utils import encrypt_password, decrypt_password

locales_bp = Blueprint("locales_bp", __name__)


# ─── Utilidades ──────────────────────────────────────────────────────────────

FECHA_CORTE_CAJA = date(2026, 11, 15)


def _limpiar_moneda(valor_raw):
    """Convierte un string con puntos de miles o formato moneda ('1.250.000') a float."""
    if valor_raw is None:
        return 0.0
    if isinstance(valor_raw, (int, float)):
        return float(valor_raw)
    texto = str(valor_raw).strip().replace("$", "").replace(" ", "")
    if not texto:
        return 0.0
    # Si viene como decimal estándar de Python (ej: '8500000.00' con un solo punto y 1-2 decimales)
    if texto.count(".") == 1 and "," not in texto:
        partes = texto.split(".")
        if len(partes[1]) <= 2:
            try:
                return float(texto)
            except ValueError:
                pass
    # Formato colombiano con puntos de miles (ej: '8.500.000' o '450.000')
    texto_limpio = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto_limpio)
    except ValueError:
        return 0.0

def _calcular_mrr(locales):
    """Suma las mensualidades de todos los locales comerciales facturables."""
    return sum(
        float(l.mensualidad)
        for l in locales
        if getattr(l, "tipo_plan", "Mensual") != "Interna" and l.estado_pago == "Activo"
    )


def _stats_semaforo(locales):
    """Devuelve conteo por color del semáforo para locales facturables."""
    locales_fact = [l for l in locales if getattr(l, "tipo_plan", "Mensual") != "Interna"]
    verde = sum(1 for l in locales_fact if l.semaforo == "semaforo-verde")
    amarillo = sum(1 for l in locales_fact if l.semaforo == "semaforo-amarillo")
    rojo = sum(1 for l in locales_fact if l.semaforo == "semaforo-rojo")
    return verde, amarillo, rojo


# ─── Dashboard Principal ─────────────────────────────────────────────────────

@locales_bp.route("/")
@locales_bp.route("/dashboard")
@login_required
def dashboard():
    locales = Local.query.order_by(Local.nombre_marca).all()

    mrr = _calcular_mrr(locales)
    arr = mrr * 12
    # Total invertido histórico
    total_invertido = sum(float(l.inversion_inicial) for l in locales if getattr(l, "tipo_plan", "Mensual") != "Interna")
    verde, amarillo, rojo = _stats_semaforo(locales)
    
    online_count = sum(1 for l in locales if l.is_online)
    offline_count = sum(1 for l in locales if not l.is_online)
    total_facturables = sum(1 for l in locales if getattr(l, "tipo_plan", "Mensual") != "Interna")

    # Últimas 5 notificaciones
    notifs_recientes = (
        Notificacion.query.order_by(Notificacion.fecha_envio.desc()).limit(5).all()
    )

    return render_template(
        "locales/dashboard.html",
        locales=locales,
        mrr=mrr,
        arr=arr,
        total_invertido=total_invertido,
        total_locales=len(locales),
        total_facturables=total_facturables,
        verde=verde,
        amarillo=amarillo,
        rojo=rojo,
        online_count=online_count,
        offline_count=offline_count,
        notifs_recientes=notifs_recientes,
    )


# ─── CRUD Locales ────────────────────────────────────────────────────────────

@locales_bp.route("/locales/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_local():
    if request.method == "POST":
        try:
            email_plain = request.form.get("boveda_email", "").strip()
            pass_plain = request.form.get("boveda_password", "").strip()

            fecha_lanzamiento = datetime.strptime(
                request.form["fecha_lanzamiento"], "%Y-%m-%d"
            ).date()

            fecha_inicio_str = request.form.get("fecha_inicio_facturacion", "").strip()
            if fecha_inicio_str:
                fecha_inicio_facturacion = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            else:
                import calendar
                from datetime import date as _date
                tm = fecha_lanzamiento.year * 12 + fecha_lanzamiento.month
                ny, nm = tm // 12, (tm % 12) + 1
                fecha_inicio_facturacion = _date(ny, nm, min(fecha_lanzamiento.day, calendar.monthrange(ny, nm)[1]))

            tipo_plan = request.form.get("tipo_plan", "Mensual").strip()
            inversion_inicial = _limpiar_moneda(request.form.get("inversion_inicial", 0))
            valor_anualidad = _limpiar_moneda(request.form.get("valor_anualidad", 0))
            
            # Si es anual y no especifican mensualidad, se calcula la mensualidad equivalente
            if tipo_plan == "Anual":
                mensualidad_input = _limpiar_moneda(request.form.get("mensualidad", 0))
                mensualidad = mensualidad_input if mensualidad_input > 0 else (valor_anualidad / 12)
                dia_pago = fecha_inicio_facturacion.day if fecha_inicio_facturacion else fecha_lanzamiento.day
            elif tipo_plan == "Interna":
                mensualidad = 0.0
                dia_pago = 1
            else:
                mensualidad = _limpiar_moneda(request.form.get("mensualidad", 0))
                dia_pago = int(request.form.get("dia_pago", 1) or 1)

            telefono_cobro = request.form.get("telefono_cobro", "").strip() or None

            local = Local(
                nombre_marca=request.form["nombre_marca"].strip(),
                url_instancia=request.form.get("url_instancia", "").strip() or None,
                fecha_lanzamiento=fecha_lanzamiento,
                fecha_inicio_facturacion=fecha_inicio_facturacion,
                version_software=request.form.get("version_software", "1.0.0").strip(),
                tipo_plan=tipo_plan,
                telefono_cobro=telefono_cobro,
                inversion_inicial=inversion_inicial,
                mensualidad=mensualidad,
                valor_anualidad=valor_anualidad,
                dia_pago=dia_pago,
                estado_pago=request.form.get("estado_pago", "Activo"),
                boveda_email=encrypt_password(email_plain) if email_plain else None,
                boveda_password=encrypt_password(pass_plain) if pass_plain else None,
            )
            db.session.add(local)
            db.session.flush() # Obtener local.id

            # Registrar evento inicial en bitácora del cliente
            db.session.add(BitacoraCliente(
                local_id=local.id,
                user_id=current_user.id,
                tipo="Configuración",
                titulo="Cliente registrado en Zenic Master Control",
                detalle=f"Modalidad: {tipo_plan} · Mensualidad: ${mensualidad:,.0f} · Inicio facturación: {fecha_inicio_facturacion.strftime('%d/%m/%Y')} (Corte día {dia_pago})."
            ))

            # Control de cobro de instalación:
            # Si el usuario marcó que el cliente es antiguo / instalación ya pagada ('instalacion_pagada' == 'si'),
            # o si la fecha de lanzamiento es anterior al corte de caja (15/11/2026) y no pidió generar cobro pendiente,
            # NO se genera factura pendiente de instalación para no alterar la caja actual.
            estado_instalacion = request.form.get("estado_instalacion", "auto")
            generar_cobro_instalacion = False
            if tipo_plan != "Interna" and inversion_inicial > 0:
                if estado_instalacion == "pendiente":
                    generar_cobro_instalacion = True
                elif estado_instalacion == "pagada":
                    generar_cobro_instalacion = False
                else:
                    # 'auto': solo si lanzamiento >= 15/11/2026
                    generar_cobro_instalacion = (fecha_lanzamiento >= FECHA_CORTE_CAJA)

            if generar_cobro_instalacion:
                from datetime import timedelta
                from routes.ingresos import generar_sigla_local
                hoy_dt = obtener_hora_bogota()
                sigla = generar_sigla_local(local.nombre_marca)
                num_fac = f"{sigla}-INST"
                if Factura.query.filter_by(numero_factura=num_fac).first():
                    num_fac = f"{sigla}-INST-{hoy_dt.strftime('%y%m')}"
                factura_instalacion = Factura(
                    numero_factura=num_fac,
                    local_id=local.id,
                    monto=inversion_inicial,
                    tipo_cobro="Instalación",
                    fecha_emision=fecha_lanzamiento,
                    fecha_vencimiento=fecha_lanzamiento + timedelta(days=5),
                    estado="Pendiente",
                    observaciones="Cobro de instalación y parametrización inicial (incluye 1er mes de servicio)"
                )
                db.session.add(factura_instalacion)

            db.session.commit()
            flash(f"✅ Local «{local.nombre_marca}» registrado exitosamente.", "success")
            return redirect(url_for("locales_bp.dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Error al guardar: {str(e)}", "danger")

    return render_template("locales/form_local.html", local=None, modo="nuevo")


@locales_bp.route("/locales/<int:local_id>/editar", methods=["GET", "POST"])
@login_required
def editar_local(local_id):
    local = Local.query.get_or_404(local_id)

    if request.method == "POST":
        try:
            local.nombre_marca = request.form["nombre_marca"].strip()
            local.url_instancia = request.form.get("url_instancia", "").strip() or None
            local.fecha_lanzamiento = datetime.strptime(
                request.form["fecha_lanzamiento"], "%Y-%m-%d"
            ).date()

            fecha_inicio_str = request.form.get("fecha_inicio_facturacion", "").strip()
            if fecha_inicio_str:
                local.fecha_inicio_facturacion = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            else:
                import calendar
                from datetime import date as _date
                tm = local.fecha_lanzamiento.year * 12 + local.fecha_lanzamiento.month
                ny, nm = tm // 12, (tm % 12) + 1
                local.fecha_inicio_facturacion = _date(ny, nm, min(local.fecha_lanzamiento.day, calendar.monthrange(ny, nm)[1]))

            local.version_software = request.form.get("version_software", "1.0.0").strip()
            
            tipo_plan = request.form.get("tipo_plan", "Mensual").strip()
            local.tipo_plan = tipo_plan
            local.inversion_inicial = _limpiar_moneda(request.form.get("inversion_inicial", 0))
            local.valor_anualidad = _limpiar_moneda(request.form.get("valor_anualidad", 0))

            if tipo_plan == "Anual":
                mensualidad_input = _limpiar_moneda(request.form.get("mensualidad", 0))
                local.mensualidad = mensualidad_input if mensualidad_input > 0 else (local.valor_anualidad / 12)
                local.dia_pago = local.fecha_inicio_facturacion.day if local.fecha_inicio_facturacion else local.fecha_lanzamiento.day
            elif tipo_plan == "Interna":
                local.mensualidad = 0.0
                local.dia_pago = 1
            else:
                local.mensualidad = _limpiar_moneda(request.form.get("mensualidad", 0))
                local.dia_pago = int(request.form.get("dia_pago", 1) or 1)

            local.telefono_cobro = request.form.get("telefono_cobro", "").strip() or None
            local.estado_pago = request.form.get("estado_pago", "Activo")

            # Solo actualizar bóveda si se ingresó nuevo valor
            email_plain = request.form.get("boveda_email", "").strip()
            pass_plain = request.form.get("boveda_password", "").strip()
            if email_plain:
                local.boveda_email = encrypt_password(email_plain)
            if pass_plain:
                local.boveda_password = encrypt_password(pass_plain)

            db.session.add(BitacoraCliente(
                local_id=local.id,
                user_id=current_user.id,
                tipo="Configuración",
                titulo="Actualización de ficha comercial / configuración",
                detalle=f"Plan: {local.tipo_plan} · Mensualidad: ${float(local.mensualidad):,.0f} · Inicio cobro: {local.fecha_inicio_facturacion.strftime('%d/%m/%Y') if local.fecha_inicio_facturacion else 'Automático'} · Día corte: {local.dia_pago} · Estado: {local.estado_pago}."
            ))

            db.session.commit()
            flash(f"✅ Local «{local.nombre_marca}» actualizado.", "success")
            return redirect(url_for("locales_bp.ver_local", local_id=local.id))
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Error: {str(e)}", "danger")

    return render_template("locales/form_local.html", local=local, modo="editar")


@locales_bp.route("/clientes")
@login_required
def directorio_clientes():
    """Módulo Directorio de Perfiles de Clientes: Tarjetas 360° con resumen de pagos, tickets y cambios."""
    locales = Local.query.order_by(Local.nombre_marca.asc()).all()
    hoy = obtener_hora_bogota().date()
    return render_template(
        "locales/clientes_hub.html",
        locales=locales,
        hoy=hoy
    )


@locales_bp.route("/locales/<int:local_id>")
@login_required
def ver_local(local_id):
    local = Local.query.get_or_404(local_id)
    hoy = obtener_hora_bogota().date()

    # Desencriptar para mostrar (solo en vista detalle)
    email_dec = decrypt_password(local.boveda_email) if local.boveda_email else "—"
    pass_dec = decrypt_password(local.boveda_password) if local.boveda_password else "—"

    # 1. Historial de Facturas y Meses Pagados del cliente
    facturas_cliente = Factura.query.filter_by(local_id=local.id).order_by(Factura.fecha_vencimiento.desc()).all()
    facturas_pagadas = [f for f in facturas_cliente if f.estado == "Pagado"]
    facturas_pendientes = [f for f in facturas_cliente if f.estado in ("Pendiente", "Vencido")]
    total_pagado_cliente = sum(float(f.monto) for f in facturas_pagadas)
    total_pendiente_cliente = sum(float(f.monto) for f in facturas_pendientes)

    # 2. Tickets de Soporte y Cambios Técnicos del cliente
    tickets_cliente = TicketCambio.query.filter_by(local_id=local.id).order_by(TicketCambio.fecha_creacion.desc()).all()
    usuarios_ti = User.query.filter(User.rol.in_(["ti", "admin"])).order_by(User.nombre).all()

    # 3. Bitácora cronológica de cambios y eventos (combina registros explícitos + pagos + tickets)
    bitacora_db = BitacoraCliente.query.filter_by(local_id=local.id).order_by(BitacoraCliente.fecha.desc()).all()

    return render_template(
        "locales/detalle_local.html",
        local=local,
        email_dec=email_dec,
        pass_dec=pass_dec,
        facturas_cliente=facturas_cliente,
        facturas_pagadas=facturas_pagadas,
        facturas_pendientes=facturas_pendientes,
        total_pagado_cliente=total_pagado_cliente,
        total_pendiente_cliente=total_pendiente_cliente,
        tickets_cliente=tickets_cliente,
        usuarios_ti=usuarios_ti,
        bitacora_db=bitacora_db,
        hoy=hoy
    )


@locales_bp.route("/locales/<int:local_id>/bitacora", methods=["POST"])
@login_required
def agregar_bitacora_cliente(local_id):
    """Permite registrar un cambio, ajuste o nota en el perfil histórico del cliente."""
    local = Local.query.get_or_404(local_id)
    tipo = request.form.get("tipo", "Cambio").strip()
    titulo = request.form.get("titulo", "").strip()
    detalle = request.form.get("detalle", "").strip()

    if not titulo:
        flash("El título del cambio o registro es obligatorio.", "danger")
        return redirect(url_for("locales_bp.ver_local", local_id=local.id))

    nuevo_evento = BitacoraCliente(
        local_id=local.id,
        user_id=current_user.id,
        tipo=tipo,
        titulo=titulo,
        detalle=detalle or None
    )
    db.session.add(nuevo_evento)
    db.session.commit()
    flash(f"✅ Registro agregado al historial de «{local.nombre_marca}».", "success")
    return redirect(url_for("locales_bp.ver_local", local_id=local.id))


@locales_bp.route("/locales/<int:local_id>/eliminar", methods=["POST"])
@login_required
def eliminar_local(local_id):
    local = Local.query.get_or_404(local_id)
    nombre = local.nombre_marca
    db.session.delete(local)
    db.session.commit()
    flash(f"🗑️ Local «{nombre}» eliminado.", "success")
    return redirect(url_for("locales_bp.dashboard"))


@locales_bp.route("/locales/<int:local_id>/cambiar-estado", methods=["POST"])
@login_required
def cambiar_estado(local_id):
    """Actualiza rápidamente el estado de pago desde la tabla del dashboard."""
    local = Local.query.get_or_404(local_id)
    nuevo_estado = request.form.get("estado_pago")
    if nuevo_estado in ("Activo", "Pendiente", "Suspendido"):
        local.estado_pago = nuevo_estado
        db.session.commit()
        flash(f"✅ Estado de «{local.nombre_marca}» actualizado a {nuevo_estado}.", "success")
    return redirect(url_for("locales_bp.dashboard"))


# ─── Sistema de Notificaciones ───────────────────────────────────────────────

@locales_bp.route("/notificaciones", methods=["GET"])
@login_required
def notificaciones():
    historial = Notificacion.query.order_by(Notificacion.fecha_envio.desc()).all()
    locales = Local.query.order_by(Local.nombre_marca).all()
    return render_template(
        "locales/notificaciones.html", historial=historial, locales=locales
    )


@locales_bp.route("/notificaciones/enviar", methods=["POST"])
@login_required
def enviar_notificacion():
    """
    Recibe el formulario con título, mensaje, tipo y destinos (IDs de locales).
    Para cada destino que tenga URL, hace un POST HTTP (webhook) con el payload.
    """
    titulo = request.form.get("titulo", "").strip()
    mensaje = request.form.get("mensaje", "").strip()
    tipo = request.form.get("tipo", "info")
    destino_ids = request.form.getlist("destinos")  # lista de IDs como strings

    if not titulo or not mensaje:
        flash("❌ El título y el mensaje son obligatorios.", "danger")
        return redirect(url_for("locales_bp.notificaciones"))

    # Convertir a enteros y obtener locales
    if "todos" in destino_ids:
        locales_dest = Local.query.all()
    else:
        ids = [int(x) for x in destino_ids if x.isdigit()]
        locales_dest = Local.query.filter(Local.id.in_(ids)).all()

    resultados = {}
    payload = {
        "titulo": titulo,
        "mensaje": mensaje,
        "tipo": tipo,
        "origen": "Zenic Master Control",
        "timestamp": datetime.utcnow().isoformat(),
    }

    for local in locales_dest:
        if local.url_instancia:
            webhook_url = local.url_instancia.rstrip("/") + "/api/zenic/notificacion"
            try:
                resp = requests.post(
                    webhook_url,
                    json=payload,
                    timeout=5,
                    headers={"Content-Type": "application/json"},
                )
                resultados[local.id] = {
                    "nombre": local.nombre_marca,
                    "status": resp.status_code,
                    "ok": resp.ok,
                }
            except requests.exceptions.RequestException as e:
                resultados[local.id] = {
                    "nombre": local.nombre_marca,
                    "status": 0,
                    "ok": False,
                    "error": str(e),
                }
        else:
            resultados[local.id] = {
                "nombre": local.nombre_marca,
                "status": None,
                "ok": None,
                "error": "Sin URL configurada",
            }

    # Guardar en historial
    notif = Notificacion(
        user_id=current_user.id,
        titulo=titulo,
        mensaje=mensaje,
        tipo=tipo,
        destinos=json.dumps([l.id for l in locales_dest]),
        resultados=json.dumps(resultados),
    )
    db.session.add(notif)
    db.session.commit()

    enviados_ok = sum(1 for r in resultados.values() if r.get("ok"))
    flash(
        f"📡 Notificación enviada a {len(locales_dest)} instancias "
        f"({enviados_ok} respondieron OK).",
        "success",
    )
    return redirect(url_for("locales_bp.notificaciones"))


# ─── API interna ─────────────────────────────────────────────────────────────

@locales_bp.route("/api/mrr")
@login_required
def api_mrr():
    """Retorna el MRR en JSON para gráficas JS."""
    locales = Local.query.all()
    data = {
        "mrr": _calcular_mrr(locales),
        "total_locales": len(locales),
        "activos": sum(1 for l in locales if l.estado_pago == "Activo"),
        "pendientes": sum(1 for l in locales if l.estado_pago == "Pendiente"),
        "suspendidos": sum(1 for l in locales if l.estado_pago == "Suspendido"),
    }
    return jsonify(data)
