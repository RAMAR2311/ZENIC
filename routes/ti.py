"""
routes/ti.py — Módulo de TI: Conexiones, Uptime & Tickets de Cambios
====================================================================
Gestiona las solicitudes técnicas creadas por Operaciones para los clientes
y centraliza los accesos a instancias y monitor de estado.
"""

from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user

from models import db, TicketCambio, Local, User, obtener_hora_bogota
from decorators import ti_required, tickets_access_required

ti_bp = Blueprint("ti_bp", __name__, url_prefix="/ti")


@ti_bp.route("/tickets", methods=["GET"])
@login_required
@tickets_access_required
def tickets():
    """
    Lista de tickets de cambio / soporte.
    Permite filtrar por estado y prioridad.
    """
    estado_filtro = request.args.get("estado", "")
    local_filtro = request.args.get("local_id", "")

    query = TicketCambio.query.order_by(
        TicketCambio.estado.asc(),
        TicketCambio.fecha_creacion.desc()
    )

    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)
    if local_filtro:
        query = query.filter_by(local_id=int(local_filtro))

    tickets_list = query.all()
    locales = Local.query.order_by(Local.nombre_marca).all()
    usuarios_ti = User.query.filter(User.rol.in_(["ti", "admin"])).all()

    # Métricas rápidas
    total_pendientes = TicketCambio.query.filter(TicketCambio.estado.in_(["Pendiente", "En Desarrollo"])).count()
    total_urgentes = TicketCambio.query.filter(TicketCambio.prioridad == "Urgente", TicketCambio.estado != "Resuelto").count()
    total_resueltos = TicketCambio.query.filter_by(estado="Resuelto").count()

    return render_template(
        "ti/tickets.html",
        tickets=tickets_list,
        locales=locales,
        usuarios_ti=usuarios_ti,
        total_pendientes=total_pendientes,
        total_urgentes=total_urgentes,
        total_resueltos=total_resueltos,
        estado_filtro=estado_filtro,
        local_filtro=local_filtro
    )


@ti_bp.route("/tickets/nuevo", methods=["POST"])
@login_required
@tickets_access_required
def nuevo_ticket():
    """Creación de un nuevo ticket de soporte por parte de Operaciones o Admin."""
    titulo = request.form.get("titulo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    local_id = request.form.get("local_id")
    categoria = request.form.get("categoria", "Soporte")
    prioridad = request.form.get("prioridad", "Media")

    if not titulo or not descripcion:
        flash("El título y la descripción son obligatorios.", "error")
        return redirect(url_for("ti_bp.tickets"))

    ticket = TicketCambio(
        titulo=titulo,
        descripcion=descripcion,
        local_id=int(local_id) if local_id else None,
        categoria=categoria,
        prioridad=prioridad,
        solicitante_id=current_user.id,
        estado="Pendiente"
    )

    db.session.add(ticket)
    db.session.commit()

    flash(f"Ticket #{ticket.id} registrado correctamente.", "success")
    return redirect(url_for("ti_bp.tickets"))


@ti_bp.route("/tickets/<int:ticket_id>/actualizar", methods=["POST"])
@login_required
@ti_required
def actualizar_ticket(ticket_id):
    """Actualización del estado y notas de resolución por parte del equipo de TI."""
    ticket = TicketCambio.query.get_or_404(ticket_id)

    nuevo_estado = request.form.get("estado")
    asignado_id = request.form.get("asignado_id")
    notas = request.form.get("notas_resolucion")

    if nuevo_estado:
        ticket.estado = nuevo_estado
        if nuevo_estado == "Resuelto" and not ticket.fecha_cierre:
            ticket.fecha_cierre = obtener_hora_bogota()
        elif nuevo_estado != "Resuelto":
            ticket.fecha_cierre = None

    if asignado_id:
        ticket.asignado_id = int(asignado_id) if asignado_id != "" else None

    if notas is not None:
        ticket.notas_resolucion = notas.strip()

    db.session.commit()
    flash(f"Ticket #{ticket.id} actualizado exitosamente.", "success")
    return redirect(url_for("ti_bp.tickets"))


@ti_bp.route("/conexiones")
@login_required
@ti_required
def conexiones():
    """Centro de conexiones de sistemas: Uptime, URLs y acceso a servidores."""
    locales = Local.query.order_by(Local.nombre_marca).all()
    return render_template("ti/conexiones.html", locales=locales)

