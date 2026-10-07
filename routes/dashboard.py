from flask import Blueprint, render_template
from flask_login import login_required
from models import db, Local, Gasto, Ingreso, Factura, Tesoreria, ActivoFijo, Personal, obtener_hora_bogota
from sqlalchemy import func
import calendar
from dateutil.relativedelta import relativedelta

dashboard_bp = Blueprint("dashboard_bp", __name__)

@dashboard_bp.route("/")
@login_required
def master():
    hoy = obtener_hora_bogota()
    mes_actual = hoy.month
    ano_actual = hoy.year
    
    # 1. Finanzas (Ingresos y Gastos del mes)
    gastos_mes = Gasto.query.filter(db.extract('month', Gasto.fecha) == mes_actual, db.extract('year', Gasto.fecha) == ano_actual).all()
    total_gastos = sum(float(g.monto) for g in gastos_mes)
    
    ingresos_reales = Ingreso.query.filter(db.extract('month', Ingreso.fecha) == mes_actual, db.extract('year', Ingreso.fecha) == ano_actual).all()
    facturas_pagadas = Factura.query.filter(Factura.estado == 'Pagado', db.extract('month', Factura.fecha_pago) == mes_actual, db.extract('year', Factura.fecha_pago) == ano_actual).all()
    total_ingresos = sum(float(i.monto) for i in ingresos_reales) + sum(float(f.monto) for f in facturas_pagadas)
    
    beneficio_neto = total_ingresos - total_gastos
    
    # 2. Distribución de Gastos
    gastos_directos = sum(float(g.monto) for g in gastos_mes if getattr(g, 'tipo_costo', '') == 'Costo Directo')
    gastos_indirectos = sum(float(g.monto) for g in gastos_mes if getattr(g, 'tipo_costo', '') == 'Costo Indirecto')
    gastos_admin = sum(float(g.monto) for g in gastos_mes if getattr(g, 'tipo_costo', '') == 'Gasto Administrativo')
    
    # 3. Tesoreria
    tesoreria = Tesoreria.query.first()
    patrimonio = (float(tesoreria.saldo_banco) + float(tesoreria.caja_menor)) if tesoreria else 0
    total_equipos = db.session.query(func.sum(ActivoFijo.valor)).scalar() or 0
    patrimonio_neto = patrimonio + float(total_equipos)
    
    # 4. Locales (Clientes)
    locales = Local.query.all()
    mrr = sum(float(l.mensualidad) for l in locales if l.estado_pago == "Activo")
    total_locales = len(locales)
    
    online_count = sum(1 for l in locales if getattr(l, 'is_online', False))
    
    # Estados de clientes
    al_dia = sum(1 for l in locales if l.semaforo == 'semaforo-verde')
    por_vencer = sum(1 for l in locales if l.semaforo == 'semaforo-amarillo')
    atrasado = sum(1 for l in locales if l.semaforo == 'semaforo-rojo')
    
    # 5. Operaciones
    total_personal = Personal.query.count()
    
    # 6. Histórico últimos 6 meses
    meses_labels = []
    ingresos_hist = []
    gastos_hist = []
    
    for i in range(5, -1, -1):
        d = hoy - relativedelta(months=i)
        meses_labels.append(f"{calendar.month_abbr[d.month]} {d.year}")
        
        gm = Gasto.query.filter(db.extract('month', Gasto.fecha) == d.month, db.extract('year', Gasto.fecha) == d.year).all()
        gastos_hist.append(sum(float(g.monto) for g in gm))
        
        imm = Ingreso.query.filter(db.extract('month', Ingreso.fecha) == d.month, db.extract('year', Ingreso.fecha) == d.year).all()
        fmm = Factura.query.filter(Factura.estado == 'Pagado', db.extract('month', Factura.fecha_pago) == d.month, db.extract('year', Factura.fecha_pago) == d.year).all()
        ingresos_hist.append(sum(float(x.monto) for x in imm) + sum(float(y.monto) for y in fmm))

    return render_template(
        "dashboard_master.html",
        total_ingresos=total_ingresos,
        total_gastos=total_gastos,
        beneficio_neto=beneficio_neto,
        patrimonio_neto=patrimonio_neto,
        mrr=mrr,
        total_locales=total_locales,
        online_count=online_count,
        total_personal=total_personal,
        gastos_directos=gastos_directos,
        gastos_indirectos=gastos_indirectos,
        gastos_admin=gastos_admin,
        al_dia=al_dia,
        por_vencer=por_vencer,
        atrasado=atrasado,
        meses_labels=meses_labels,
        ingresos_hist=ingresos_hist,
        gastos_hist=gastos_hist,
        facturas_recientes=Factura.query.order_by(Factura.fecha_emision.desc()).limit(5).all(),
        hoy=hoy
    )
