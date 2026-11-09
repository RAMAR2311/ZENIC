"""
routes/marketing.py — Módulo de Marketing & Contenidos Zenic
============================================================
Portal integral para el equipo de marketing:
  - Planificador y calendario de contenidos
  - Agenda de grabaciones y producciones audiovisuales
  - Monitoreo y accesos rápidos a redes oficiales
  - Repositorio de recursos de marca (Brand Kit)
"""

from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user

from models import db, ContenidoMarketing, SesionGrabacion, obtener_hora_bogota
from decorators import marketing_required

marketing_bp = Blueprint("marketing_bp", __name__, url_prefix="/marketing")


@marketing_bp.route("/")
@login_required
@marketing_required
def dashboard():
    """Vista general y métricas del módulo de marketing."""
    hoy = obtener_hora_bogota().date()
    
    contenidos_pendientes = ContenidoMarketing.query.filter(
        ContenidoMarketing.estado != "Publicado"
    ).order_by(ContenidoMarketing.fecha_programada.asc()).all()

    grabaciones_proximas = SesionGrabacion.query.filter(
        SesionGrabacion.fecha_grabacion >= datetime.combine(hoy, datetime.min.time())
    ).order_by(SesionGrabacion.fecha_grabacion.asc()).all()

    total_publicados = ContenidoMarketing.query.filter_by(estado="Publicado").count()
    total_ideas = ContenidoMarketing.query.filter_by(estado="Idea").count()
    total_en_produccion = ContenidoMarketing.query.filter(
        ContenidoMarketing.estado.in_(["En Guion", "Listo para Grabar", "En Edicion"])
    ).count()

    return render_template(
        "marketing/dashboard.html",
        contenidos=contenidos_pendientes,
        grabaciones=grabaciones_proximas,
        total_publicados=total_publicados,
        total_ideas=total_ideas,
        total_en_produccion=total_en_produccion
    )


@marketing_bp.route("/contenidos", methods=["GET", "POST"])
@login_required
@marketing_required
def contenidos():
    """Gestión y creación del calendario de contenidos para redes sociales."""
    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        red_social = request.form.get("red_social")
        formato = request.form.get("formato")
        copy = request.form.get("copy", "").strip()
        link_recurso = request.form.get("link_recurso", "").strip()
        fecha_str = request.form.get("fecha_programada")
        estado = request.form.get("estado", "Idea")

        fecha_prog = None
        if fecha_str:
            try:
                fecha_prog = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        if titulo and red_social:
            nuevo = ContenidoMarketing(
                titulo=titulo,
                red_social=red_social,
                formato=formato,
                copy=copy,
                link_recurso=link_recurso,
                fecha_programada=fecha_prog,
                estado=estado,
                autor_id=current_user.id
            )
            db.session.add(nuevo)
            db.session.commit()
            flash("Contenido programado exitosamente.", "success")
        return redirect(url_for("marketing_bp.contenidos"))

    red_filtro = request.args.get("red", "")
    estado_filtro = request.args.get("estado", "")

    query = ContenidoMarketing.query.order_by(ContenidoMarketing.fecha_programada.desc(), ContenidoMarketing.id.desc())
    if red_filtro:
        query = query.filter_by(red_social=red_filtro)
    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)

    lista_contenidos = query.all()
    return render_template("marketing/contenidos.html", contenidos=lista_contenidos, red_filtro=red_filtro, estado_filtro=estado_filtro)


@marketing_bp.route("/contenidos/<int:id>/estado", methods=["POST"])
@login_required
@marketing_required
def cambiar_estado_contenido(id):
    """Cambio rápido de estado en el embudo de contenidos."""
    contenido = ContenidoMarketing.query.get_or_404(id)
    nuevo_estado = request.form.get("estado")
    if nuevo_estado:
        contenido.estado = nuevo_estado
        db.session.commit()
        flash(f"Estado de '{contenido.titulo}' actualizado a {nuevo_estado}.", "success")
    return redirect(url_for("marketing_bp.contenidos"))


@marketing_bp.route("/grabaciones", methods=["GET", "POST"])
@login_required
@marketing_required
def grabaciones():
    """Planificador de grabaciones y producciones audiovisuales."""
    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        fecha_str = request.form.get("fecha_grabacion")
        locacion = request.form.get("locacion", "").strip()
        objetivo = request.form.get("objetivo", "").strip()
        participantes = request.form.get("participantes", "").strip()
        equipos = request.form.get("equipos_requeridos", "").strip()

        if titulo and fecha_str and locacion:
            try:
                fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M")
                grabacion = SesionGrabacion(
                    titulo=titulo,
                    fecha_grabacion=fecha_obj,
                    locacion=locacion,
                    objetivo=objetivo,
                    participantes=participantes,
                    equipos_requeridos=equipos
                )
                db.session.add(grabacion)
                db.session.commit()
                flash("Sesión de grabación agendada exitosamente.", "success")
            except ValueError:
                flash("Formato de fecha inválido.", "error")
        return redirect(url_for("marketing_bp.grabaciones"))

    sesiones = SesionGrabacion.query.order_by(SesionGrabacion.fecha_grabacion.desc()).all()
    return render_template("marketing/grabaciones.html", sesiones=sesiones)


@marketing_bp.route("/social-hub")
@login_required
@marketing_required
def social_hub():
    """Centro de monitoreo de canales oficiales, Brand Kit y redes de Zenic."""
    return render_template("marketing/social_hub.html")

