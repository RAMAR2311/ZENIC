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

from models import db, ContenidoMarketing, SesionGrabacion, CorteMetricaSocial, obtener_hora_bogota
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


@marketing_bp.route("/metricas", methods=["GET", "POST"])
@login_required
@marketing_required
def metricas():
    """Panel de Crecimiento y Métricas de Redes Sociales (Especificación Santiago/Miguel)."""
    hoy = obtener_hora_bogota().date()

    if request.method == "POST":
        red_social = request.form.get("red_social", "Instagram").strip()
        periodo_tipo = request.form.get("periodo_tipo", "Semanal").strip()
        etiqueta_periodo = request.form.get("etiqueta_periodo", "").strip()
        fecha_corte_str = request.form.get("fecha_corte")
        seguidores_totales = int(request.form.get("seguidores_totales", 0) or 0)
        visualizaciones = int(request.form.get("visualizaciones", 0) or 0)
        alcance = int(request.form.get("alcance", 0) or 0)
        interacciones = int(request.form.get("interacciones", 0) or 0)
        link_top_post = request.form.get("link_top_post", "").strip() or None
        leads_generados = int(request.form.get("leads_generados", 0) or 0)
        notas_campana = request.form.get("notas_campana", "").strip() or None

        fecha_corte = hoy
        if fecha_corte_str:
            try:
                fecha_corte = datetime.strptime(fecha_corte_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        if not etiqueta_periodo:
            etiqueta_periodo = f"{periodo_tipo} al {fecha_corte.strftime('%d/%m/%Y')}"

        nuevo_corte = CorteMetricaSocial(
            red_social=red_social,
            periodo_tipo=periodo_tipo,
            etiqueta_periodo=etiqueta_periodo,
            fecha_corte=fecha_corte,
            seguidores_totales=seguidores_totales,
            visualizaciones=visualizaciones,
            alcance=alcance,
            interacciones=interacciones,
            link_top_post=link_top_post,
            leads_generados=leads_generados,
            notas_campana=notas_campana,
            autor_id=current_user.id
        )
        db.session.add(nuevo_corte)
        db.session.commit()
        flash(f"✅ Corte de métricas para {red_social} ({etiqueta_periodo}) registrado con éxito.", "success")
        return redirect(url_for("marketing_bp.metricas", red=red_social))

    red_filtro = request.args.get("red", "Instagram").strip()
    periodo_filtro = request.args.get("periodo", "").strip()

    query = CorteMetricaSocial.query
    if red_filtro and red_filtro != "Consolidado":
        query = query.filter_by(red_social=red_filtro)
    if periodo_filtro:
        query = query.filter_by(periodo_tipo=periodo_filtro)

    cortes = query.order_by(CorteMetricaSocial.fecha_corte.desc(), CorteMetricaSocial.id.desc()).all()

    ultimo_corte = cortes[0] if cortes else None
    corte_anterior = cortes[1] if len(cortes) > 1 else None

    # Cálculo de variaciones porcentuales (▲ +X% / ▼ -Y%)
    def calc_variacion(val_actual, val_anterior):
        if not val_anterior or val_anterior == 0:
            if val_actual and val_actual > 0:
                return {"pct": 100.0, "sube": True, "neutro": False, "label": "+100%"}
            return {"pct": 0.0, "sube": False, "neutro": True, "label": "0%"}
        pct = round(((val_actual - val_anterior) / val_anterior) * 100, 1)
        sube = pct >= 0
        signo = "+" if pct > 0 else ""
        return {"pct": pct, "sube": sube, "neutro": (pct == 0), "label": f"{signo}{pct}%"}

    variaciones = {}
    if ultimo_corte:
        val_ant_seg = corte_anterior.seguidores_totales if corte_anterior else 0
        val_ant_vis = corte_anterior.visualizaciones if corte_anterior else 0
        val_ant_alc = corte_anterior.alcance if corte_anterior else 0
        val_ant_int = corte_anterior.interacciones if corte_anterior else 0
        val_ant_leads = corte_anterior.leads_generados if corte_anterior else 0
        val_ant_eng = corte_anterior.engagement_rate if corte_anterior else 0.0

        variaciones["seguidores"] = calc_variacion(ultimo_corte.seguidores_totales, val_ant_seg)
        variaciones["visualizaciones"] = calc_variacion(ultimo_corte.visualizaciones, val_ant_vis)
        variaciones["alcance"] = calc_variacion(ultimo_corte.alcance, val_ant_alc)
        variaciones["interacciones"] = calc_variacion(ultimo_corte.interacciones, val_ant_int)
        variaciones["leads"] = calc_variacion(ultimo_corte.leads_generados, val_ant_leads)

        diff_eng = round(ultimo_corte.engagement_rate - val_ant_eng, 2)
        variaciones["engagement"] = {
            "pct": diff_eng,
            "sube": diff_eng >= 0,
            "neutro": diff_eng == 0,
            "label": f"{'+' if diff_eng > 0 else ''}{diff_eng}%"
        }

    # Datos para Chart.js (orden cronológico ascendente)
    historico_grafica = list(reversed(cortes[:12]))
    chart_labels = [c.etiqueta_periodo or c.fecha_corte.strftime("%d/%m") for c in historico_grafica]
    chart_alcance = [c.alcance for c in historico_grafica]
    chart_interacciones = [c.interacciones for c in historico_grafica]
    chart_seguidores = [c.seguidores_totales for c in historico_grafica]
    chart_leads = [c.leads_generados for c in historico_grafica]

    return render_template(
        "marketing/metricas.html",
        cortes=cortes,
        ultimo_corte=ultimo_corte,
        corte_anterior=corte_anterior,
        variaciones=variaciones,
        red_filtro=red_filtro,
        periodo_filtro=periodo_filtro,
        chart_labels=chart_labels,
        chart_alcance=chart_alcance,
        chart_interacciones=chart_interacciones,
        chart_seguidores=chart_seguidores,
        chart_leads=chart_leads,
        hoy=hoy
    )


@marketing_bp.route("/metricas/<int:id>/eliminar", methods=["POST"])
@login_required
@marketing_required
def eliminar_metrica(id):
    corte = CorteMetricaSocial.query.get_or_404(id)
    red = corte.red_social
    db.session.delete(corte)
    db.session.commit()
    flash("Registro de métrica eliminado.", "info")
    return redirect(url_for("marketing_bp.metricas", red=red))

