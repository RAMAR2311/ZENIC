from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from models import db, Ingreso, Gasto, PresupuestoArea, Factura, Tesoreria, ActivoFijo, obtener_hora_bogota
from datetime import datetime

finanzas_bp = Blueprint("finanzas_bp", __name__)

# -- Ingresos / Tesorería --
@finanzas_bp.route("/finanzas/ingresos", methods=["GET", "POST"])
@login_required
def ingresos():
    tesoreria = Tesoreria.query.first()
    if not tesoreria:
        tesoreria = Tesoreria(saldo_banco=0, caja_menor=0)  # type: ignore
        db.session.add(tesoreria)
        db.session.commit()

    if request.method == "POST":
        action = request.form.get("action", "registrar_ingreso")
        
        if action == "registrar_ingreso":
            descripcion = request.form.get("descripcion")
            monto = request.form.get("monto")
            fecha_str = request.form.get("fecha")
            categoria = request.form.get("categoria", "General")
            
            if descripcion and monto and fecha_str:
                fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                nuevo = Ingreso(descripcion=descripcion, monto=float(monto), fecha=fecha_dt, categoria=categoria)  # type: ignore
                db.session.add(nuevo)
                db.session.commit()
                flash("Ingreso registrado.", "success")
                
        elif action == "actualizar_banco":
            tesoreria.saldo_banco = float(request.form.get("saldo_banco", 0))
            db.session.commit()
            flash("Saldo de banco actualizado.", "success")
            
        elif action == "actualizar_caja":
            tesoreria.caja_menor = float(request.form.get("caja_menor", 0))
            db.session.commit()
            flash("Saldo de caja menor actualizado.", "success")
            
        elif action == "registrar_activo":
            descripcion = request.form.get("descripcion")
            valor = request.form.get("valor")
            if descripcion and valor:
                nuevo_activo = ActivoFijo(descripcion=descripcion, valor=float(valor))  # type: ignore
                db.session.add(nuevo_activo)
                db.session.commit()
                flash("Activo registrado correctamente.", "success")
                
        elif action == "transferir":
            origen = request.form.get("origen")
            monto = float(request.form.get("monto", 0))
            if monto > 0:
                if origen == "banco_a_caja":
                    tesoreria.saldo_banco -= monto
                    tesoreria.caja_menor += monto
                elif origen == "caja_a_banco":
                    tesoreria.caja_menor -= monto
                    tesoreria.saldo_banco += monto
                db.session.commit()
                flash("Transferencia realizada con éxito.", "success")

        return redirect(url_for("finanzas_bp.ingresos"))
        
    hoy = obtener_hora_bogota()
    ingresos_list = Ingreso.query.order_by(Ingreso.fecha.desc()).all()
    activos = ActivoFijo.query.all()
    gastos_list = Gasto.query.order_by(Gasto.fecha.desc()).limit(15).all()
    
    total_equipos = sum(float(a.valor) for a in activos)
    
    # Facturas Pagadas del mes (Ingresos Locales)
    facturas_pagadas = Factura.query.filter(
        Factura.estado == 'Pagado',
        db.extract('month', Factura.fecha_pago) == hoy.month,
        db.extract('year', Factura.fecha_pago) == hoy.year
    ).all()
    total_locales = sum(float(f.monto) for f in facturas_pagadas)
    total_ingresos_extra = sum(float(i.monto) for i in ingresos_list if i.fecha.month == hoy.month and i.fecha.year == hoy.year)
    
    total_mensual_liquidez = float(tesoreria.caja_menor) + total_locales + total_ingresos_extra
    patrimonio_neto = float(tesoreria.saldo_banco) + float(tesoreria.caja_menor) + total_equipos
    
    return render_template(
        "finanzas/ingresos.html", 
        ingresos=ingresos_list,
        tesoreria=tesoreria,
        gastos=gastos_list,
        total_equipos=total_equipos,
        total_locales=total_locales,
        total_ingresos_extra=total_ingresos_extra,
        total_mensual_liquidez=total_mensual_liquidez,
        patrimonio_neto=patrimonio_neto,
        hoy=hoy
    )

# -- Gastos --
@finanzas_bp.route("/finanzas/gastos", methods=["GET", "POST"])
@login_required
def gastos():
    hoy = obtener_hora_bogota()
    if request.method == "POST":
        descripcion = request.form.get("descripcion")
        monto = request.form.get("monto")
        fecha_str = request.form.get("fecha")
        categoria = request.form.get("categoria", "General")
        tipo_costo = request.form.get("tipo_costo", "Gasto Administrativo")
        presupuesto_id = request.form.get("presupuesto_id")
        
        if descripcion and monto and fecha_str:
            fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            p_id = int(presupuesto_id) if presupuesto_id else None
            nuevo = Gasto(
                descripcion=descripcion, 
                monto=float(monto), 
                fecha=fecha_dt, 
                categoria=categoria,
                tipo_costo=tipo_costo,
                presupuesto_id=p_id
            )  # type: ignore
            db.session.add(nuevo)
            db.session.commit()
            flash("Gasto registrado.", "success")
        return redirect(url_for("finanzas_bp.gastos"))
        
    gastos_list = Gasto.query.order_by(Gasto.fecha.desc()).all()
    presupuestos_activos = PresupuestoArea.query.filter_by(mes=hoy.month, ano=hoy.year).all()
    
    total_directo = sum(float(g.monto) for g in gastos_list if g.fecha.month == hoy.month and g.tipo_costo == 'Costo Directo')
    total_indirecto = sum(float(g.monto) for g in gastos_list if g.fecha.month == hoy.month and g.tipo_costo == 'Costo Indirecto')
    total_admin = sum(float(g.monto) for g in gastos_list if g.fecha.month == hoy.month and g.tipo_costo == 'Gasto Administrativo')
    
    return render_template(
        "finanzas/gastos.html", 
        gastos=gastos_list, 
        presupuestos=presupuestos_activos,
        total_directo=total_directo,
        total_indirecto=total_indirecto,
        total_admin=total_admin,
        hoy=hoy
    )

# -- Presupuestos --
@finanzas_bp.route("/finanzas/presupuestos", methods=["GET", "POST"])
@login_required
def presupuestos():
    hoy = obtener_hora_bogota()
    mes_actual = request.args.get("mes", hoy.month, type=int)
    ano_actual = request.args.get("ano", hoy.year, type=int)
    
    if request.method == "POST":
        nombre_area = request.form.get("nombre_area")
        limite_gastos = float(request.form.get("limite_gastos", 0))
        
        if nombre_area:
            presupuesto = PresupuestoArea.query.filter_by(nombre_area=nombre_area, mes=mes_actual, ano=ano_actual).first()
            if not presupuesto:
                presupuesto = PresupuestoArea(nombre_area=nombre_area, mes=mes_actual, ano=ano_actual)  # type: ignore
                db.session.add(presupuesto)
            
            presupuesto.limite_gastos = limite_gastos
            db.session.commit()
            flash(f"Presupuesto para {nombre_area} actualizado.", "success")
            
        return redirect(url_for("finanzas_bp.presupuestos", mes=mes_actual, ano=ano_actual))
        
    presupuestos_list = PresupuestoArea.query.filter_by(mes=mes_actual, ano=ano_actual).all()
    
    # Calcular el progreso de cada presupuesto
    for p in presupuestos_list:
        gastado = sum(float(g.monto) for g in p.gastos)
        p.gastado = gastado
        p.porcentaje = (gastado / float(p.limite_gastos) * 100) if p.limite_gastos > 0 else 0
        p.estado_color = "success" if p.porcentaje < 75 else ("warning" if p.porcentaje < 90 else "danger")
    
    return render_template(
        "finanzas/presupuestos.html",
        presupuestos=presupuestos_list,
        mes_actual=mes_actual,
        ano_actual=ano_actual,
        hoy=hoy
    )
