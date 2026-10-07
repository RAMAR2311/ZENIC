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

from models import db, Local, Notificacion
from crypto_utils import encrypt_password, decrypt_password

locales_bp = Blueprint("locales_bp", __name__)


# ─── Utilidades ──────────────────────────────────────────────────────────────

def _calcular_mrr(locales):
    """Suma las mensualidades de todos los locales registrados."""
    return sum(
        float(l.mensualidad)
        for l in locales
    )


def _stats_semaforo(locales):
    """Devuelve conteo por color del semáforo."""
    verde = sum(1 for l in locales if l.semaforo == "semaforo-verde")
    amarillo = sum(1 for l in locales if l.semaforo == "semaforo-amarillo")
    rojo = sum(1 for l in locales if l.semaforo == "semaforo-rojo")
    return verde, amarillo, rojo


# ─── Dashboard Principal ─────────────────────────────────────────────────────

@locales_bp.route("/")
@locales_bp.route("/dashboard")
@login_required
def dashboard():
    locales = Local.query.order_by(Local.nombre_marca).all()

    mrr = _calcular_mrr(locales)
    arr = mrr * 12
    total_invertido = sum(float(l.inversion_inicial) for l in locales)
    verde, amarillo, rojo = _stats_semaforo(locales)
    
    online_count = sum(1 for l in locales if l.is_online)
    offline_count = sum(1 for l in locales if not l.is_online)

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
            # Cifrar credenciales antes de guardar
            email_plain = request.form.get("boveda_email", "").strip()
            pass_plain = request.form.get("boveda_password", "").strip()

            local = Local(
                nombre_marca=request.form["nombre_marca"].strip(),
                url_instancia=request.form.get("url_instancia", "").strip() or None,
                fecha_lanzamiento=datetime.strptime(
                    request.form["fecha_lanzamiento"], "%Y-%m-%d"
                ).date(),
                version_software=request.form.get("version_software", "1.0.0").strip(),
                inversion_inicial=float(request.form.get("inversion_inicial", 0)),
                mensualidad=float(request.form.get("mensualidad", 0)),
                dia_pago=int(request.form.get("dia_pago", 1)),
                estado_pago=request.form.get("estado_pago", "Activo"),
                boveda_email=encrypt_password(email_plain) if email_plain else None,
                boveda_password=encrypt_password(pass_plain) if pass_plain else None,
            )
            db.session.add(local)
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
            local.version_software = request.form.get("version_software", "1.0.0").strip()
            local.inversion_inicial = float(request.form.get("inversion_inicial", 0))
            local.mensualidad = float(request.form.get("mensualidad", 0))
            local.dia_pago = int(request.form.get("dia_pago", 1))
            local.estado_pago = request.form.get("estado_pago", "Activo")

            # Solo actualizar bóveda si se ingresó nuevo valor
            email_plain = request.form.get("boveda_email", "").strip()
            pass_plain = request.form.get("boveda_password", "").strip()
            if email_plain:
                local.boveda_email = encrypt_password(email_plain)
            if pass_plain:
                local.boveda_password = encrypt_password(pass_plain)

            db.session.commit()
            flash(f"✅ Local «{local.nombre_marca}» actualizado.", "success")
            return redirect(url_for("locales_bp.ver_local", local_id=local.id))
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Error: {str(e)}", "danger")

    return render_template("locales/form_local.html", local=local, modo="editar")


@locales_bp.route("/locales/<int:local_id>")
@login_required
def ver_local(local_id):
    local = Local.query.get_or_404(local_id)
    # Desencriptar para mostrar (solo en vista detalle)
    email_dec = decrypt_password(local.boveda_email) if local.boveda_email else "—"
    pass_dec = decrypt_password(local.boveda_password) if local.boveda_password else "—"
    return render_template(
        "locales/detalle_local.html",
        local=local,
        email_dec=email_dec,
        pass_dec=pass_dec,
    )


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
