from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from models import db, Local, Factura, obtener_hora_bogota
from datetime import datetime

ingresos_bp = Blueprint("ingresos_bp", __name__)

@ingresos_bp.route("/ingresos")
@login_required
def dashboard_ingresos():
    locales = Local.query.order_by(Local.nombre_marca.asc()).all()
    facturas = Factura.query.order_by(Factura.fecha_vencimiento.desc()).all()
    
    hoy = obtener_hora_bogota().date()
    
    # Auto-actualizar estado de vencimiento
    for f in facturas:
        if f.estado == "Pendiente" and f.fecha_vencimiento < hoy:
            f.estado = "Vencido"
            db.session.commit()
            
    # Calcular KPIs
    facturas_pagadas = sum(float(f.monto) for f in facturas if f.estado == "Pagado" and f.fecha_pago and f.fecha_pago.month == hoy.month and f.fecha_pago.year == hoy.year)
    
    facturas_vencidas = 0
    for l in locales:
        # Verifica si tiene alguna factura generada este mes
        tiene_factura_mes = any(f.fecha_emision.month == hoy.month and f.fecha_emision.year == hoy.year for f in l.facturas_list)
        if not tiene_factura_mes or l.semaforo == "semaforo-rojo":
            facturas_vencidas += float(l.mensualidad)
            
    facturas_futuras = sum(float(f.monto) for f in facturas if f.estado == "Pendiente" and f.fecha_emision.month == hoy.month and f.fecha_emision.year == hoy.year)
            
    return render_template(
        "ingresos/dashboard.html",
        facturas=facturas,
        locales=locales,
        ingresos_actuales=facturas_pagadas,
        ingresos_vencidos=facturas_vencidas,
        ingresos_futuros=facturas_futuras
    )

@ingresos_bp.route("/ingresos/nueva", methods=["POST"])
@login_required
def nueva_factura():
    local_id = request.form.get("local_id")
    observaciones = request.form.get("observaciones", "")
    
    if not local_id:
        flash("Faltan datos requeridos.", "error")
        return redirect(url_for("ingresos_bp.dashboard_ingresos"))
        
    try:
        local = Local.query.get(local_id)
        if not local:
            flash("Local no encontrado.", "error")
            return redirect(url_for("ingresos_bp.dashboard_ingresos"))
            
        count = Factura.query.count() + 1
        hoy = obtener_hora_bogota()
        numero_factura = f"INV-{hoy.strftime('%Y%m')}-{count:04d}"
        
        # Asignar vencimiento a 15 días (o el día actual, según preferencia, ya que se ocultó del form)
        from datetime import timedelta
        f_venc = (hoy + timedelta(days=15)).date()
        
        nueva = Factura(
            numero_factura=numero_factura,
            local_id=local.id,
            monto=local.mensualidad,
            fecha_vencimiento=f_venc,
            observaciones=observaciones
        )
        
        local.estado_pago = "Activo"
        
        db.session.add(nueva)
        db.session.commit()
        flash("Factura generada y cliente actualizado a 'Activo' con éxito.", "success")
    except Exception as e:
        flash(f"Error al generar factura: {e}", "error")
        db.session.rollback()
        
    return redirect(url_for("ingresos_bp.dashboard_ingresos"))

@ingresos_bp.route("/ingresos/<int:factura_id>/pagar", methods=["POST"])
@login_required
def pagar_factura(factura_id):
    factura = Factura.query.get_or_404(factura_id)
    if factura.estado != "Pagado":
        factura.estado = "Pagado"
        factura.fecha_pago = obtener_hora_bogota().date()
        factura.local.estado_pago = "Activo"
        db.session.commit()
        flash(f"Factura {factura.numero_factura} cobrada y cliente en estado 'Al día'.", "success")
    return redirect(url_for("ingresos_bp.dashboard_ingresos"))

@ingresos_bp.route("/ingresos/<int:factura_id>/soporte")
@login_required
def soporte_factura(factura_id):
    factura = Factura.query.get_or_404(factura_id)
    return render_template("ingresos/soporte_factura.html", factura=factura)
