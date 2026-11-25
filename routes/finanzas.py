import os
import csv
import io
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, Response
from flask_login import login_required, current_user
from models import (
    db, Ingreso, Gasto, PresupuestoArea, Factura, Tesoreria,
    ActivoFijo, Prestamo, AbonoPrestamo, Local, BitacoraCliente, CostoFijo, obtener_hora_bogota
)
from routes.locales import _limpiar_moneda
from datetime import datetime, date

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
            monto = _limpiar_moneda(request.form.get("monto"))
            fecha_str = request.form.get("fecha")
            categoria = request.form.get("categoria", "General")
            
            if descripcion and monto > 0 and fecha_str:
                fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                nuevo = Ingreso(descripcion=descripcion, monto=monto, fecha=fecha_dt, categoria=categoria)  # type: ignore
                db.session.add(nuevo)
                db.session.commit()
                flash("Ingreso registrado.", "success")
                
        elif action == "actualizar_banco":
            tesoreria.saldo_banco = _limpiar_moneda(request.form.get("saldo_banco", 0))
            db.session.commit()
            flash("Saldo de banco actualizado.", "success")
            
        elif action == "actualizar_caja":
            tesoreria.caja_menor = _limpiar_moneda(request.form.get("caja_menor", 0))
            db.session.commit()
            flash("Saldo de caja menor actualizado.", "success")
            
        elif action == "registrar_activo":
            descripcion = request.form.get("descripcion")
            valor = _limpiar_moneda(request.form.get("valor"))
            if descripcion and valor > 0:
                nuevo_activo = ActivoFijo(descripcion=descripcion, valor=valor)  # type: ignore
                db.session.add(nuevo_activo)
                db.session.commit()
                flash("Activo registrado correctamente.", "success")
                
        elif action == "transferir":
            origen = request.form.get("origen")
            monto = _limpiar_moneda(request.form.get("monto", 0))
            if monto > 0:
                if origen == "banco_a_caja":
                    tesoreria.saldo_banco = float(tesoreria.saldo_banco) - monto
                    tesoreria.caja_menor = float(tesoreria.caja_menor) + monto
                elif origen == "caja_a_banco":
                    tesoreria.caja_menor = float(tesoreria.caja_menor) - monto
                    tesoreria.saldo_banco = float(tesoreria.saldo_banco) + monto
                db.session.commit()
                flash("Transferencia realizada con éxito.", "success")

        return redirect(url_for("finanzas_bp.ingresos"))
        
    hoy = obtener_hora_bogota()
    ingresos_list = Ingreso.query.order_by(Ingreso.fecha.desc()).all()
    activos = ActivoFijo.query.all()
    gastos_list = Gasto.query.order_by(Gasto.fecha.desc()).limit(15).all()
    
    total_equipos = sum(float(a.valor) for a in activos)
    prestamos_activos = Prestamo.query.all()
    total_cartera_prestamos = sum(p.saldo_pendiente for p in prestamos_activos if p.estado != "Pagado")
    
    # Facturas Pagadas del mes (Ingresos Locales)
    facturas_pagadas = Factura.query.filter(
        Factura.estado == 'Pagado',
        db.extract('month', Factura.fecha_pago) == hoy.month,
        db.extract('year', Factura.fecha_pago) == hoy.year
    ).all()
    total_locales = sum(float(f.monto) for f in facturas_pagadas)
    total_ingresos_extra = sum(float(i.monto) for i in ingresos_list if i.fecha.month == hoy.month and i.fecha.year == hoy.year)
    
    # Abonos de préstamos recibidos este mes
    abonos_mes = AbonoPrestamo.query.filter(
        db.extract('month', AbonoPrestamo.fecha_abono) == hoy.month,
        db.extract('year', AbonoPrestamo.fecha_abono) == hoy.year
    ).all()
    total_abonos_mes = sum(float(ab.monto) for ab in abonos_mes)
    
    total_mensual_liquidez = float(tesoreria.caja_menor) + total_locales + total_ingresos_extra + total_abonos_mes
    # Patrimonio Neto incluye Banco + Caja Menor + Equipos + Cartera por Cobrar de Préstamos a favor de Zenic
    patrimonio_neto = float(tesoreria.saldo_banco) + float(tesoreria.caja_menor) + total_equipos + total_cartera_prestamos
    
    return render_template(
        "finanzas/ingresos.html", 
        ingresos=ingresos_list,
        tesoreria=tesoreria,
        gastos=gastos_list,
        total_equipos=total_equipos,
        total_cartera_prestamos=total_cartera_prestamos,
        total_abonos_mes=total_abonos_mes,
        total_locales=total_locales,
        total_ingresos_extra=total_ingresos_extra,
        total_mensual_liquidez=total_mensual_liquidez,
        patrimonio_neto=patrimonio_neto,
        hoy=hoy
    )

FECHA_CORTE_CAJA = date(2026, 11, 15)


def _obtener_saldos_cuentas():
    """Calcula el saldo actual disponible en Nu, Nequi, Banco y Caja Menor."""
    tesoreria = Tesoreria.query.first()
    if not tesoreria:
        tesoreria = Tesoreria(saldo_banco=0, caja_menor=0)
        db.session.add(tesoreria)
        db.session.commit()

    # Saldo Nu
    fac_nu = Factura.query.filter(Factura.estado == "Pagado", Factura.cuenta_destino == "Nu", Factura.fecha_pago >= FECHA_CORTE_CAJA).all()
    ab_nu = AbonoPrestamo.query.filter(AbonoPrestamo.cuenta_destino == "Nu", AbonoPrestamo.fecha_abono >= FECHA_CORTE_CAJA).all()
    gas_nu = Gasto.query.filter(Gasto.cuenta_origen == "Nu", Gasto.fecha >= FECHA_CORTE_CAJA).all()
    saldo_nu = sum(float(f.monto) for f in fac_nu) + sum(float(a.monto) for a in ab_nu) - sum(float(g.monto) for g in gas_nu)

    # Saldo Nequi
    fac_nq = Factura.query.filter(Factura.estado == "Pagado", Factura.cuenta_destino == "Nequi", Factura.fecha_pago >= FECHA_CORTE_CAJA).all()
    ab_nq = AbonoPrestamo.query.filter(AbonoPrestamo.cuenta_destino == "Nequi", AbonoPrestamo.fecha_abono >= FECHA_CORTE_CAJA).all()
    gas_nq = Gasto.query.filter(Gasto.cuenta_origen == "Nequi", Gasto.fecha >= FECHA_CORTE_CAJA).all()
    saldo_nequi = sum(float(f.monto) for f in fac_nq) + sum(float(a.monto) for a in ab_nq) - sum(float(g.monto) for g in gas_nq)

    return {
        "Nu": saldo_nu,
        "Nequi": saldo_nequi,
        "Banco": float(tesoreria.saldo_banco),
        "Caja Menor": float(tesoreria.caja_menor),
        "tesoreria": tesoreria
    }


def _guardar_comprobante_gasto(archivo, prefijo="gasto"):
    """Guarda la imagen o PDF del comprobante de pago de un gasto o costo fijo."""
    if not archivo or not archivo.filename:
        return None
    orig_name = secure_filename(archivo.filename)
    if not orig_name:
        return None
    _, ext = os.path.splitext(orig_name)
    ext = ext.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
        return None
    folder = current_app.config.get("COMPROBANTES_UPLOAD_FOLDER")
    os.makedirs(folder, exist_ok=True)
    ts = obtener_hora_bogota().strftime("%Y%m%d%H%M%S")
    nombre_final = f"{prefijo}_{ts}{ext}"
    archivo.save(os.path.join(folder, nombre_final))
    return nombre_final


# -- Gastos & Costos Fijos --
@finanzas_bp.route("/finanzas/gastos", methods=["GET", "POST"])
@login_required
def gastos():
    hoy = obtener_hora_bogota()
    saldos = _obtener_saldos_cuentas()
    tesoreria = saldos["tesoreria"]

    if request.method == "POST":
        descripcion = request.form.get("descripcion", "").strip()
        monto = _limpiar_moneda(request.form.get("monto", 0))
        fecha_str = request.form.get("fecha", "").strip()
        categoria = request.form.get("categoria", "General").strip() or "General"
        tipo_costo = request.form.get("tipo_costo", "Gasto Administrativo").strip()
        presupuesto_id = request.form.get("presupuesto_id", "").strip()
        cuenta_origen = request.form.get("cuenta_origen", "Nu").strip()
        archivo = request.files.get("comprobante")

        if descripcion and monto > 0 and fecha_str:
            fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            p_id = int(presupuesto_id) if (presupuesto_id and presupuesto_id.isdigit()) else None
            comp_nombre = _guardar_comprobante_gasto(archivo, prefijo="gasto")

            nuevo = Gasto(
                descripcion=descripcion,
                monto=monto,
                fecha=fecha_dt,
                categoria=categoria,
                tipo_costo=tipo_costo,
                presupuesto_id=p_id,
                cuenta_origen=cuenta_origen,
                comprobante_ruta=comp_nombre
            )
            db.session.add(nuevo)

            # Si se pagó desde Banco o Caja Menor, descontar directamente del saldo en Tesorería
            # (Nu y Nequi se descuentan dinámicamente por consulta sobre la tabla Gasto)
            if cuenta_origen in ("Banco", "Bancolombia"):
                tesoreria.saldo_banco = float(tesoreria.saldo_banco) - monto
            elif cuenta_origen == "Caja Menor":
                tesoreria.caja_menor = float(tesoreria.caja_menor) - monto

            db.session.commit()
            flash(f"✅ Salida registrada por ${monto:,.0f} descontada de {cuenta_origen}.", "success")
        else:
            flash("Por favor ingresa un concepto y un monto válido mayor a $0.", "danger")
        return redirect(url_for("finanzas_bp.gastos"))

    gastos_list = Gasto.query.order_by(Gasto.fecha.desc(), Gasto.id.desc()).all()
    costos_fijos = CostoFijo.query.filter_by(activo=True).order_by(CostoFijo.dia_pago.asc(), CostoFijo.id.asc()).all()

    # Solo mostrar presupuestos que realmente tengan límite asignado (> 0) en el mes actual
    presupuestos_activos = PresupuestoArea.query.filter(
        PresupuestoArea.mes == hoy.month,
        PresupuestoArea.ano == hoy.year,
        PresupuestoArea.limite_gastos > 0
    ).all()

    total_directo = sum(float(g.monto) for g in gastos_list if g.fecha.month == hoy.month and g.tipo_costo == 'Costo Directo')
    total_indirecto = sum(float(g.monto) for g in gastos_list if g.fecha.month == hoy.month and g.tipo_costo == 'Costo Indirecto')
    total_admin = sum(float(g.monto) for g in gastos_list if g.fecha.month == hoy.month and g.tipo_costo == 'Gasto Administrativo')
    total_prestamos_pagados = sum(float(g.monto) for g in gastos_list if g.fecha.month == hoy.month and (g.tipo_costo == 'Pago de Préstamo' or g.categoria == 'Préstamos'))
    total_salidas_mes = sum(float(g.monto) for g in gastos_list if g.fecha.month == hoy.month and g.fecha.year == hoy.year)
    total_salidas_historico = sum(float(g.monto) for g in gastos_list)

    total_fijos_mensual = sum(float(cf.monto_mensual) for cf in costos_fijos)
    fijos_pagados_mes = sum(1 for cf in costos_fijos if cf.pagado_en_periodo(hoy.month, hoy.year))
    fijos_pendientes_mes = len(costos_fijos) - fijos_pagados_mes

    return render_template(
        "finanzas/gastos.html",
        gastos=gastos_list,
        costos_fijos=costos_fijos,
        presupuestos=presupuestos_activos,
        total_directo=total_directo,
        total_indirecto=total_indirecto,
        total_admin=total_admin,
        total_prestamos_pagados=total_prestamos_pagados,
        total_salidas_mes=total_salidas_mes,
        total_salidas_historico=total_salidas_historico,
        total_fijos_mensual=total_fijos_mensual,
        fijos_pagados_mes=fijos_pagados_mes,
        fijos_pendientes_mes=fijos_pendientes_mes,
        saldos=saldos,
        hoy=hoy
    )


@finanzas_bp.route("/finanzas/costos-fijos/nuevo", methods=["POST"])
@login_required
def nuevo_costo_fijo():
    """Registra una plantilla de Costo Fijo u Obligación Mensual (incluyendo Préstamos de la empresa)."""
    nombre = request.form.get("nombre", "").strip()
    categoria = request.form.get("categoria", "Operativo").strip()
    tipo_costo = request.form.get("tipo_costo", "Costo Directo").strip()
    monto_mensual = _limpiar_moneda(request.form.get("monto_mensual", 0))
    dia_pago_raw = request.form.get("dia_pago", "").strip()
    observaciones = request.form.get("observaciones", "").strip()

    if not nombre or monto_mensual <= 0:
        flash("Debes indicar el nombre del costo fijo y su valor mensual.", "danger")
        return redirect(url_for("finanzas_bp.gastos"))

    if categoria == "Préstamos":
        tipo_costo = "Pago de Préstamo"

    dia_pago = int(dia_pago_raw) if (dia_pago_raw and dia_pago_raw.isdigit()) else 1

    cf = CostoFijo(
        nombre=nombre,
        categoria=categoria,
        tipo_costo=tipo_costo,
        monto_mensual=monto_mensual,
        dia_pago=min(max(dia_pago, 1), 31),
        observaciones=observaciones or None,
        activo=True
    )
    db.session.add(cf)
    db.session.commit()
    flash(f"✅ Costo fijo «{nombre}» (${monto_mensual:,.0f}/mes) agregado a obligaciones mensuales.", "success")
    return redirect(url_for("finanzas_bp.gastos"))


@finanzas_bp.route("/finanzas/costos-fijos/<int:cf_id>/validar", methods=["POST"])
@login_required
def validar_costo_fijo(cf_id):
    """
    Valida que un Costo Fijo (o cuota de préstamo) ya fue pagado en el mes actual:
    - Descuenta de la cuenta seleccionada (Nu, Nequi, Banco o Caja Menor)
    - Guarda el comprobante (Foto o PDF)
    - Crea el registro real en Historial de Salidas (Gasto)
    - Marca el costo fijo como Pagado en el mes vigente
    """
    cf = CostoFijo.query.get_or_404(cf_id)
    hoy = obtener_hora_bogota()
    saldos = _obtener_saldos_cuentas()
    tesoreria = saldos["tesoreria"]

    monto_real = _limpiar_moneda(request.form.get("monto", cf.monto_mensual))
    if monto_real <= 0:
        monto_real = float(cf.monto_mensual)

    cuenta_origen = request.form.get("cuenta_origen", "Nu").strip()
    fecha_str = request.form.get("fecha_pago", "").strip()
    presupuesto_id = request.form.get("presupuesto_id", "").strip()
    archivo = request.files.get("comprobante")

    fecha_pago = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else hoy.date()
    p_id = int(presupuesto_id) if (presupuesto_id and presupuesto_id.isdigit()) else None
    comp_nombre = _guardar_comprobante_gasto(archivo, prefijo=f"cf{cf.id}")

    # 1. Crear el gasto real en el historial de salidas
    gasto_generado = Gasto(
        descripcion=f"[Costo Fijo] {cf.nombre}",
        monto=monto_real,
        fecha=fecha_pago,
        categoria=cf.categoria,
        tipo_costo=cf.tipo_costo,
        cuenta_origen=cuenta_origen,
        presupuesto_id=p_id,
        comprobante_ruta=comp_nombre
    )
    db.session.add(gasto_generado)

    # 2. Si salió de Banco o Caja Menor, descontar del saldo en Tesorería
    if cuenta_origen in ("Banco", "Bancolombia"):
        tesoreria.saldo_banco = float(tesoreria.saldo_banco) - monto_real
    elif cuenta_origen == "Caja Menor":
        tesoreria.caja_menor = float(tesoreria.caja_menor) - monto_real

    # 3. Marcar costo fijo como validado en el periodo
    cf.ultimo_mes_pagado = fecha_pago.month
    cf.ultimo_ano_pagado = fecha_pago.year
    cf.ultima_fecha_pago = fecha_pago
    cf.ultima_cuenta_origen = cuenta_origen
    if comp_nombre:
        cf.ultimo_comprobante = comp_nombre

    db.session.commit()
    flash(
        f"✅ Pago de costo fijo «{cf.nombre}» por ${monto_real:,.0f} validado y descontado de {cuenta_origen}.",
        "success"
    )
    return redirect(url_for("finanzas_bp.gastos"))


@finanzas_bp.route("/finanzas/costos-fijos/<int:cf_id>/eliminar", methods=["POST"])
@login_required
def eliminar_costo_fijo(cf_id):
    cf = CostoFijo.query.get_or_404(cf_id)
    nombre = cf.nombre
    db.session.delete(cf)
    db.session.commit()
    flash(f"🗑️ Costo fijo «{nombre}» eliminado.", "info")
    return redirect(url_for("finanzas_bp.gastos"))


# ─────────────────────────────────────────────────────────────────────────────
# REPORTE DE TRAZABILIDAD FINANCIERA (ENTRADAS VS. SALIDAS — PDF IMPRIMIBLE Y EXCEL/CSV)
# ─────────────────────────────────────────────────────────────────────────────
def _construir_movimientos_trazabilidad(fecha_inicio=None, fecha_fin=None, tipo_filtro="todos"):
    """
    Unifica cronológicamente todas las Entradas (Facturas pagadas, Abonos de préstamos, Otros ingresos)
    y todas las Salidas (Costos Directos, Indirectos, Gastos Admin y Pagos de Préstamos).
    """
    movimientos = []

    # 1. ENTRADAS: Facturas Pagadas de Clientes
    q_fac = Factura.query.filter(Factura.estado == "Pagado", Factura.fecha_pago.isnot(None))
    if fecha_inicio:
        q_fac = q_fac.filter(Factura.fecha_pago >= fecha_inicio)
    if fecha_fin:
        q_fac = q_fac.filter(Factura.fecha_pago <= fecha_fin)
    for f in q_fac.all():
        movimientos.append({
            "fecha": f.fecha_pago,
            "tipo": "Entrada",
            "origen_tipo": f"Factura ({f.tipo_cobro})",
            "concepto": f"{f.local.nombre_marca if f.local else 'Cliente'} — Factura #{f.numero_factura}",
            "cuenta": f.cuenta_destino or "Nu",
            "monto": float(f.monto),
            "comprobante": None
        })

    # 2. ENTRADAS: Abonos recibidos de Préstamos a favor de Zenic
    q_ab = AbonoPrestamo.query
    if fecha_inicio:
        q_ab = q_ab.filter(AbonoPrestamo.fecha_abono >= fecha_inicio)
    if fecha_fin:
        q_ab = q_ab.filter(AbonoPrestamo.fecha_abono <= fecha_fin)
    for ab in q_ab.all():
        deudor_nom = ab.prestamo.deudor if ab.prestamo else "Préstamo"
        movimientos.append({
            "fecha": ab.fecha_abono,
            "tipo": "Entrada",
            "origen_tipo": "Abono de Préstamo",
            "concepto": f"Abono de {deudor_nom} ({ab.observacion or 'Recuperación de cartera'})",
            "cuenta": ab.cuenta_destino or "Nu",
            "monto": float(ab.monto),
            "comprobante": ab.comprobante_ruta
        })

    # 3. ENTRADAS: Otros Ingresos / Servicios Extra
    q_ing = Ingreso.query
    if fecha_inicio:
        q_ing = q_ing.filter(Ingreso.fecha >= fecha_inicio)
    if fecha_fin:
        q_ing = q_ing.filter(Ingreso.fecha <= fecha_fin)
    for ing in q_ing.all():
        movimientos.append({
            "fecha": ing.fecha,
            "tipo": "Entrada",
            "origen_tipo": f"Ingreso Extra ({ing.categoria})",
            "concepto": ing.descripcion,
            "cuenta": "Tesorería / Banco",
            "monto": float(ing.monto),
            "comprobante": None
        })

    # 4. SALIDAS: Todos los Costos, Gastos y Cuotas de Préstamos
    q_gas = Gasto.query
    if fecha_inicio:
        q_gas = q_gas.filter(Gasto.fecha >= fecha_inicio)
    if fecha_fin:
        q_gas = q_gas.filter(Gasto.fecha <= fecha_fin)
    for g in q_gas.all():
        movimientos.append({
            "fecha": g.fecha,
            "tipo": "Salida",
            "origen_tipo": f"{g.tipo_costo} ({g.categoria or 'General'})",
            "concepto": g.descripcion,
            "cuenta": g.cuenta_origen or "Nu",
            "monto": float(g.monto),
            "comprobante": g.comprobante_ruta
        })

    if tipo_filtro == "entradas":
        movimientos = [m for m in movimientos if m["tipo"] == "Entrada"]
    elif tipo_filtro == "salidas":
        movimientos = [m for m in movimientos if m["tipo"] == "Salida"]

    # Ordenar por fecha descendente
    movimientos.sort(key=lambda x: x["fecha"], reverse=True)
    return movimientos


@finanzas_bp.route("/finanzas/trazabilidad")
@login_required
def reporte_trazabilidad():
    """
    Genera el documento ejecutivo de Trazabilidad Financiera (Entradas vs. Salidas)
    listo para imprimir / guardar como PDF o descargar en Excel (CSV).
    """
    hoy = obtener_hora_bogota().date()
    f_ini_str = request.args.get("fecha_inicio", "").strip()
    f_fin_str = request.args.get("fecha_fin", "").strip()
    tipo_filtro = request.args.get("tipo", "todos").strip() # 'todos', 'entradas', 'salidas'
    formato = request.args.get("formato", "pdf").strip()    # 'pdf' (vista imprimible) o 'csv'

    fecha_inicio = datetime.strptime(f_ini_str, "%Y-%m-%d").date() if f_ini_str else None
    fecha_fin = datetime.strptime(f_fin_str, "%Y-%m-%d").date() if f_fin_str else None

    movimientos = _construir_movimientos_trazabilidad(fecha_inicio, fecha_fin, tipo_filtro)

    total_entradas = sum(m["monto"] for m in movimientos if m["tipo"] == "Entrada")
    total_salidas = sum(m["monto"] for m in movimientos if m["tipo"] == "Salida")
    balance_neto = total_entradas - total_salidas
    saldos = _obtener_saldos_cuentas()

    if formato == "csv":
        output = io.StringIO()
        # BOM UTF-8 para que Excel en Windows abra tildes y símbolos perfectamente
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["REPORTE DE TRAZABILIDAD FINANCIERA - ZENIC S.A.S."])
        writer.writerow(["Fecha Generacion", hoy.strftime("%d/%m/%Y"), "Total Entradas", f"{total_entradas:.0f}", "Total Salidas", f"{total_salidas:.0f}", "Balance Neto", f"{balance_neto:.0f}"])
        writer.writerow([])
        writer.writerow(["Fecha", "Movimiento", "Clasificacion / Categoria", "Concepto / Descripcion", "Cuenta / Billetera", "Entrada (COP)", "Salida (COP)"])
        for m in movimientos:
            val_in = f"{m['monto']:.0f}" if m["tipo"] == "Entrada" else "0"
            val_out = f"{m['monto']:.0f}" if m["tipo"] == "Salida" else "0"
            writer.writerow([
                m["fecha"].strftime("%d/%m/%Y") if m["fecha"] else "",
                m["tipo"],
                m["origen_tipo"],
                m["concepto"],
                m["cuenta"],
                val_in,
                val_out
            ])
        csv_content = output.getvalue()
        filename = f"Trazabilidad_Zenic_{hoy.strftime('%Y%m%d')}.csv"
        return Response(
            csv_content,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    return render_template(
        "finanzas/reporte_trazabilidad.html",
        movimientos=movimientos,
        total_entradas=total_entradas,
        total_salidas=total_salidas,
        balance_neto=balance_neto,
        saldos=saldos,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        tipo_filtro=tipo_filtro,
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


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: Préstamos & Cartera a Favor de Zenic (Cuentas por Cobrar + Abonos con Comprobante)
# ─────────────────────────────────────────────────────────────────────────────
EXTENSIONES_COMPROBANTE = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


@finanzas_bp.route("/finanzas/prestamos", methods=["GET", "POST"])
@login_required
def prestamos():
    hoy = obtener_hora_bogota().date()

    if request.method == "POST":
        deudor = request.form.get("deudor", "").strip()
        concepto = request.form.get("concepto", "").strip()
        monto_total = _limpiar_moneda(request.form.get("monto_total", 0))
        abono_inicial = _limpiar_moneda(request.form.get("abono_inicial", 0))
        fecha_str = request.form.get("fecha_prestamo", "").strip()
        venc_str = request.form.get("fecha_vencimiento", "").strip()
        observaciones = request.form.get("observaciones", "").strip()

        if not deudor or not concepto or monto_total <= 0:
            flash("Debes indicar el nombre de la persona/deudor, el concepto y un monto mayor a $0.", "danger")
            return redirect(url_for("finanzas_bp.prestamos"))

        # Las fechas son totalmente opcionales; para préstamos antiguos quedan en None (Sin fecha)
        fecha_prestamo = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else None
        fecha_venc = datetime.strptime(venc_str, "%Y-%m-%d").date() if venc_str else None

        nuevo_p = Prestamo(
            deudor=deudor,
            local_id=None,
            concepto=concepto,
            monto_total=monto_total,
            fecha_prestamo=fecha_prestamo,
            fecha_vencimiento=fecha_venc,
            es_historico=True,
            estado="Pagado" if abono_inicial >= monto_total else "Activo",
            observaciones=observaciones or None,
            creado_por_id=current_user.id
        )
        db.session.add(nuevo_p)
        db.session.flush()

        # Si el préstamo ya traía un abono previo histórico registrado al momento de cargarlo
        if abono_inicial > 0:
            ab_ini = AbonoPrestamo(
                prestamo_id=nuevo_p.id,
                monto=min(abono_inicial, monto_total),
                fecha_abono=fecha_prestamo or hoy,
                cuenta_destino="Histórico (Previo)",
                observacion="Abono acumulado previo al registro inicial en sistema",
                registrado_por_id=current_user.id
            )
            db.session.add(ab_ini)

        db.session.commit()
        flash(f"✅ Préstamo antiguo a favor de Zenic ({deudor}) por ${monto_total:,.0f} registrado.", "success")
        return redirect(url_for("finanzas_bp.prestamos"))

    prestamos_list = Prestamo.query.order_by(Prestamo.estado.asc(), Prestamo.id.desc()).all()

    total_prestado = sum(float(p.monto_total) for p in prestamos_list)
    total_recuperado = sum(p.total_abonado for p in prestamos_list)
    total_por_cobrar = sum(p.saldo_pendiente for p in prestamos_list)
    activos_count = sum(1 for p in prestamos_list if p.saldo_pendiente > 0)

    return render_template(
        "finanzas/prestamos.html",
        prestamos=prestamos_list,
        total_prestado=total_prestado,
        total_recuperado=total_recuperado,
        total_por_cobrar=total_por_cobrar,
        activos_count=activos_count,
        hoy=hoy
    )


@finanzas_bp.route("/finanzas/prestamos/<int:prestamo_id>/abonar", methods=["POST"])
@login_required
def abonar_prestamo(prestamo_id):
    """Registra un abono parcial o total a un préstamo, guarda el comprobante y suma a la cuenta/billetera."""
    prestamo = Prestamo.query.get_or_404(prestamo_id)
    hoy = obtener_hora_bogota().date()

    monto_abono = _limpiar_moneda(request.form.get("monto", 0))
    cuenta_destino = request.form.get("cuenta_destino", "Nu").strip()
    fecha_str = request.form.get("fecha_abono", "").strip()
    observacion = request.form.get("observacion", "").strip()
    archivo = request.files.get("comprobante")

    if monto_abono <= 0:
        flash("El monto del abono debe ser mayor a $0.", "danger")
        return redirect(url_for("finanzas_bp.prestamos"))

    saldo_actual = prestamo.saldo_pendiente
    if monto_abono > saldo_actual:
        monto_abono = saldo_actual

    fecha_abono = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else hoy

    comprobante_nombre = None
    if archivo and archivo.filename:
        orig_name = secure_filename(archivo.filename)
        _, ext = os.path.splitext(orig_name)
        ext = ext.lower()
        if ext not in EXTENSIONES_COMPROBANTE:
            flash("Formato de comprobante no válido. Usa imagen (JPG, PNG, WEBP) o PDF.", "danger")
            return redirect(url_for("finanzas_bp.prestamos"))

        folder = current_app.config.get("COMPROBANTES_UPLOAD_FOLDER")
        os.makedirs(folder, exist_ok=True)
        ts = obtener_hora_bogota().strftime("%Y%m%d%H%M%S")
        comprobante_nombre = f"abono_p{prestamo.id}_{ts}{ext}"
        archivo.save(os.path.join(folder, comprobante_nombre))

    abono = AbonoPrestamo(
        prestamo_id=prestamo.id,
        monto=monto_abono,
        fecha_abono=fecha_abono,
        cuenta_destino=cuenta_destino,
        comprobante_ruta=comprobante_nombre,
        observacion=observacion or None,
        registrado_por_id=current_user.id
    )
    db.session.add(abono)
    db.session.flush()

    # Si entró a Banco o Caja Menor en Tesorería, actualizar saldo directamente
    tesoreria = Tesoreria.query.first()
    if tesoreria:
        if cuenta_destino == "Banco":
            tesoreria.saldo_banco = float(tesoreria.saldo_banco) + monto_abono
        elif cuenta_destino == "Caja Menor":
            tesoreria.caja_menor = float(tesoreria.caja_menor) + monto_abono

    # Actualizar estado del préstamo si ya quedó 100% saldado
    if prestamo.saldo_pendiente <= 0:
        prestamo.estado = "Pagado"
    else:
        prestamo.estado = "Activo"

    # Si está asociado a un cliente local, registrar también en su Bitácora 360°
    if prestamo.local_id:
        db.session.add(BitacoraCliente(
            local_id=prestamo.local_id,
            user_id=current_user.id,
            tipo="Pago",
            titulo=f"Abono a préstamo recibido: ${monto_abono:,.0f} COP ({cuenta_destino})",
            detalle=f"Préstamo: {prestamo.concepto} · Saldo restante de la deuda: ${prestamo.saldo_pendiente:,.0f} COP."
        ))

    db.session.commit()
    flash(
        f"✅ Abono de ${monto_abono:,.0f} registrado en {cuenta_destino}. Saldo pendiente de {prestamo.deudor}: ${prestamo.saldo_pendiente:,.0f}.",
        "success"
    )
    return redirect(url_for("finanzas_bp.prestamos"))


@finanzas_bp.route("/finanzas/prestamos/<int:prestamo_id>/eliminar", methods=["POST"])
@login_required
def eliminar_prestamo(prestamo_id):
    prestamo = Prestamo.query.get_or_404(prestamo_id)
    deudor = prestamo.deudor
    db.session.delete(prestamo)
    db.session.commit()
    flash(f"🗑️ Registro de préstamo de «{deudor}» eliminado.", "info")
    return redirect(url_for("finanzas_bp.prestamos"))

