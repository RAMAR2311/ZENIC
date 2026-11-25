import urllib.parse
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Local, Factura, Gasto, User, BitacoraCliente, AbonoPrestamo, obtener_hora_bogota
from routes.locales import _limpiar_moneda

ingresos_bp = Blueprint("ingresos_bp", __name__)

FECHA_CORTE_CAJA = date(2026, 11, 15)

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}


def _sincronizar_facturas_ciclo(locales, hoy):
    """
    Revisa cada local activo/pendiente con fecha_inicio_facturacion y dia_pago.
    Si su próxima fecha de corte está dentro de los próximos 3 días (o ya venció)
    y aún no existe factura emitida para ese mes/año y local, la genera automáticamente.
    """
    creadas = 0
    for loc in locales:
        if getattr(loc, "tipo_plan", "Mensual") == "Interna" or loc.estado_pago == "Suspendido":
            continue
        prox_corte = loc.proxima_fecha_corte
        if not prox_corte:
            continue
        # Respetar fecha_inicio_facturacion si está configurada en el futuro
        if loc.fecha_inicio_facturacion and prox_corte < loc.fecha_inicio_facturacion:
            continue

        dias_restantes = (prox_corte - hoy).days
        # Solo sincronizar si faltan 3 días o menos para el corte o ya se pasó
        if dias_restantes <= 3:
            tipo_cobro = "Anualidad" if loc.tipo_plan == "Anual" else "Mensualidad"
            monto = float(loc.valor_anualidad) if (loc.tipo_plan == "Anual" and float(loc.valor_anualidad) > 0) else float(loc.mensualidad)
            if monto <= 0:
                continue

            # Verificar si ya existe una factura de ese tipo para ese mismo mes y año de vencimiento
            existente = Factura.query.filter(
                Factura.local_id == loc.id,
                Factura.tipo_cobro == tipo_cobro,
                db.extract("month", Factura.fecha_vencimiento) == prox_corte.month,
                db.extract("year", Factura.fecha_vencimiento) == prox_corte.year,
            ).first()

            if not existente:
                prefijo = "ANUAL" if tipo_cobro == "Anualidad" else "CICLO"
                mes_nombre = MESES_ES.get(prox_corte.month, str(prox_corte.month))
                num_base = f"{prefijo}-{prox_corte.strftime('%y%m')}-{loc.id:03d}"
                # Evitar colisión de numero_factura
                if Factura.query.filter_by(numero_factura=num_base).first():
                    continue
                nueva_fac = Factura(
                    numero_factura=num_base,
                    local_id=loc.id,
                    monto=monto,
                    tipo_cobro=tipo_cobro,
                    fecha_emision=hoy,
                    fecha_vencimiento=prox_corte,
                    estado="Vencido" if prox_corte < hoy else "Pendiente",
                    observaciones=f"Período {mes_nombre} {prox_corte.year} (Corte día {loc.dia_pago})"
                )
                db.session.add(nueva_fac)
                creadas += 1
    if creadas > 0:
        db.session.commit()
                    numero_factura=num_base,
                    local_id=loc.id,
                    monto=monto,
                    tipo_cobro=tipo_cobro,
                    fecha_emision=hoy,
                    fecha_vencimiento=prox_corte,
                    estado="Vencido" if prox_corte < hoy else "Pendiente",
                    observaciones=f"Período {mes_nombre} {prox_corte.year} (Corte día {loc.dia_pago})"
                )
                db.session.add(nueva_fac)
                creadas += 1
    if creadas > 0:
        db.session.commit()


@ingresos_bp.route("/ingresos")
@login_required
def dashboard_ingresos():
    locales = Local.query.order_by(Local.nombre_marca.asc()).all()
    hoy = obtener_hora_bogota().date()

    # 0. Sincronizar automáticamente facturas de ciclos próximos según fecha_inicio_facturacion y dia_pago
    try:
        _sincronizar_facturas_ciclo(locales, hoy)
    except Exception:
        db.session.rollback()

    facturas_all = Factura.query.all()

    # Auto-actualizar estado de vencimiento
    try:
        cambios_venc = False
        for f in facturas_all:
            if f.estado == "Pendiente" and f.fecha_vencimiento and f.fecha_vencimiento < hoy:
                f.estado = "Vencido"
                cambios_venc = True
        if cambios_venc:
            db.session.commit()
    except Exception:
        db.session.rollback()

    # Ordenar priorizando las pendientes/vencidas más próximas a vencer primero, y luego las pagadas
    def _orden_cobro(f):
        prioridad_estado = 0 if f.estado in ("Vencido", "Pendiente") else 1
        # Para pendientes/vencidas: las de fecha_vencimiento más antigua/próxima primero
        # Para pagadas: las más recientes primero
        if prioridad_estado == 0:
            return (0, f.fecha_vencimiento.toordinal())
        return (1, -f.fecha_vencimiento.toordinal())

    facturas = sorted(facturas_all, key=_orden_cobro)
    por_cobrar_count = sum(1 for f in facturas if f.estado in ("Pendiente", "Vencido"))
    pagadas_count = sum(1 for f in facturas if f.estado == "Pagado")

    # 1. Facturas Pagadas (Punto de partida financiero: >= 15/11/2026)
    facturas_pagadas = sum(
        float(f.monto)
        for f in facturas
        if f.estado == "Pagado" and f.fecha_pago and f.fecha_pago >= FECHA_CORTE_CAJA
    )

    # Facturas Vencidas
    facturas_vencidas = sum(
        float(f.monto)
        for f in facturas
        if f.estado == "Vencido"
    )

    # Facturas Pendientes / Futuras
    facturas_futuras = sum(
        float(f.monto)
        for f in facturas
        if f.estado == "Pendiente"
    )

    # 2. Billeteras de Control (Nu y Nequi) — Vista Privada para Jhon / Admin
    tiene_acceso_billeteras = (
        current_user.rol == "admin"
        or "jhon" in current_user.nombre.lower()
        or "jhon" in current_user.email.lower()
    )

    saldo_nu = 0.0
    ingresos_nu = 0.0
    gastos_nu = 0.0

    saldo_nequi = 0.0
    ingresos_nequi = 0.0
    gastos_nequi = 0.0

    if tiene_acceso_billeteras:
        # Cuenta Nu (Facturas pagadas + Abonos de préstamos recibidos en Nu >= 15/11/2026)
        facturas_nu = Factura.query.filter(
            Factura.estado == "Pagado",
            Factura.cuenta_destino == "Nu",
            Factura.fecha_pago >= FECHA_CORTE_CAJA
        ).all()
        abonos_nu = AbonoPrestamo.query.filter(
            AbonoPrestamo.cuenta_destino == "Nu",
            AbonoPrestamo.fecha_abono >= FECHA_CORTE_CAJA
        ).all()
        ingresos_nu = sum(float(f.monto) for f in facturas_nu) + sum(float(a.monto) for a in abonos_nu)

        gastos_nu_list = Gasto.query.filter(
            Gasto.cuenta_origen == "Nu",
            Gasto.fecha >= FECHA_CORTE_CAJA
        ).all()
        gastos_nu = sum(float(g.monto) for g in gastos_nu_list)
        saldo_nu = ingresos_nu - gastos_nu

        # Cuenta Nequi (Facturas pagadas + Abonos de préstamos recibidos en Nequi >= 15/11/2026)
        facturas_nequi = Factura.query.filter(
            Factura.estado == "Pagado",
            Factura.cuenta_destino == "Nequi",
            Factura.fecha_pago >= FECHA_CORTE_CAJA
        ).all()
        abonos_nequi = AbonoPrestamo.query.filter(
            AbonoPrestamo.cuenta_destino == "Nequi",
            AbonoPrestamo.fecha_abono >= FECHA_CORTE_CAJA
        ).all()
        ingresos_nequi = sum(float(f.monto) for f in facturas_nequi) + sum(float(a.monto) for a in abonos_nequi)

        gastos_nequi_list = Gasto.query.filter(
            Gasto.cuenta_origen == "Nequi",
            Gasto.fecha >= FECHA_CORTE_CAJA
        ).all()
        gastos_nequi = sum(float(g.monto) for g in gastos_nequi_list)
        saldo_nequi = ingresos_nequi - gastos_nequi

    return render_template(
        "ingresos/dashboard.html",
        facturas=facturas,
        locales=locales,
        por_cobrar_count=por_cobrar_count,
        pagadas_count=pagadas_count,
        ingresos_actuales=facturas_pagadas,
        ingresos_vencidos=facturas_vencidas,
        ingresos_futuros=facturas_futuras,
        tiene_acceso_billeteras=tiene_acceso_billeteras,
        saldo_nu=saldo_nu,
        ingresos_nu=ingresos_nu,
        gastos_nu=gastos_nu,
        saldo_nequi=saldo_nequi,
        ingresos_nequi=ingresos_nequi,
        gastos_nequi=gastos_nequi,
        fecha_corte_caja=FECHA_CORTE_CAJA,
        hoy=hoy
    )


@ingresos_bp.route("/ingresos/nueva", methods=["POST"])
@login_required
def nueva_factura():
    local_id = request.form.get("local_id")
    tipo_cobro = request.form.get("tipo_cobro", "Mensualidad").strip()
    monto_custom = request.form.get("monto")
    fecha_venc_custom = request.form.get("fecha_vencimiento")
    observaciones = request.form.get("observaciones", "").strip()

    if not local_id:
        flash("Debes seleccionar un cliente/local.", "danger")
        return redirect(url_for("ingresos_bp.dashboard_ingresos"))

    try:
        local = Local.query.get(local_id)
        if not local:
            flash("Local no encontrado.", "danger")
            return redirect(url_for("ingresos_bp.dashboard_ingresos"))

        count = Factura.query.count() + 1
        hoy_dt = obtener_hora_bogota()
        prefijo = "INST" if tipo_cobro == "Instalación" else ("ANUAL" if tipo_cobro == "Anualidad" else "INV")
        numero_factura = f"{prefijo}-{hoy_dt.strftime('%y%m')}-{count:04d}"

        # Monto (soporta puntos de miles, ej: '450.000')
        monto_limpio = _limpiar_moneda(monto_custom) if monto_custom else 0.0
        if monto_limpio > 0:
            monto = monto_limpio
        elif tipo_cobro == "Instalación":
            monto = float(local.inversion_inicial)
        elif tipo_cobro == "Anualidad":
            monto = float(local.valor_anualidad) if float(local.valor_anualidad) > 0 else (float(local.mensualidad) * 12)
        else:
            monto = float(local.mensualidad)

        # Vencimiento
        if fecha_venc_custom:
            f_venc = datetime.strptime(fecha_venc_custom, "%Y-%m-%d").date()
        else:
            f_venc = (hoy_dt + timedelta(days=10)).date()

        nueva = Factura(
            numero_factura=numero_factura,
            local_id=local.id,
            monto=monto,
            tipo_cobro=tipo_cobro,
            fecha_emision=hoy_dt.date(),
            fecha_vencimiento=f_venc,
            estado="Pendiente",
            observaciones=observaciones or None
        )

        db.session.add(nueva)
        db.session.commit()
        flash(f"✅ Factura {numero_factura} ({tipo_cobro}) generada en estado Pendiente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al generar factura: {e}", "danger")

    return redirect(url_for("ingresos_bp.dashboard_ingresos"))


@ingresos_bp.route("/ingresos/<int:factura_id>/validar", methods=["POST"])
@login_required
def validar_pago(factura_id):
    """Acción de Validar Pago: confirma ingreso real y cuenta destino (Nu o Nequi)."""
    factura = Factura.query.get_or_404(factura_id)
    cuenta_destino = request.form.get("cuenta_destino", "Nu").strip()
    fecha_pago_str = request.form.get("fecha_pago")

    if fecha_pago_str:
        try:
            fecha_pago = datetime.strptime(fecha_pago_str, "%Y-%m-%d").date()
        except ValueError:
            fecha_pago = obtener_hora_bogota().date()
    else:
        fecha_pago = obtener_hora_bogota().date()

    factura.estado = "Pagado"
    factura.fecha_pago = fecha_pago
    factura.cuenta_destino = cuenta_destino
    factura.validado_por_id = current_user.id

    # Actualizar estado de pago del local a Activo y reiniciar semáforo
    if factura.local:
        factura.local.estado_pago = "Activo"
        mes_pagado = MESES_ES.get(factura.fecha_vencimiento.month, str(factura.fecha_vencimiento.month))
        evento_pago = BitacoraCliente(
            local_id=factura.local.id,
            user_id=current_user.id,
            tipo="Pago",
            titulo=f"Pago validado: {factura.tipo_cobro} ({mes_pagado} {factura.fecha_vencimiento.year})",
            detalle=f"Factura #{factura.numero_factura} por ${float(factura.monto):,.0f} COP recibida en cuenta {cuenta_destino}."
        )
        db.session.add(evento_pago)

    db.session.commit()
    flash(
        f"✅ Pago de Factura {factura.numero_factura} por ${float(factura.monto):,.0f} validado exitosamente en cuenta {cuenta_destino}. Local activo y al día.",
        "success"
    )
    return redirect(url_for("ingresos_bp.dashboard_ingresos"))


@ingresos_bp.route("/ingresos/<int:factura_id>/pagar", methods=["POST"])
@login_required
def pagar_factura(factura_id):
    """Compatibilidad: redispacha a validación rápida con cuenta por defecto."""
    return validar_pago(factura_id)


def generar_mensaje_recordatorio_wa(factura, hoy=None):
    """
    Construye el mensaje predeterminado de WhatsApp adaptándose automáticamente
    a cuántos días faltan para el vencimiento, si vence hoy o cuántos días lleva vencido.
    """
    if hoy is None:
        hoy = obtener_hora_bogota().date()
    local = factura.local
    monto_fmt = f"${float(factura.monto):,.0f} COP".replace(",", ".")
    venc_fmt = factura.fecha_vencimiento.strftime("%d/%m/%Y")
    dias_diff = (factura.fecha_vencimiento - hoy).days

    if dias_diff > 1:
        estado_msg = f"vence en *{dias_diff} días* (fecha de corte: *{venc_fmt}*)"
        cierre_msg = "Les enviamos este recordatorio preventivo para que puedan programar su pago a tiempo y mantener su servicio al día."
    elif dias_diff == 1:
        estado_msg = f"vence *mañana {venc_fmt}*"
        cierre_msg = "Les recordamos realizar el pago oportunamente para mantener su plataforma activa sin interrupciones."
    elif dias_diff == 0:
        estado_msg = f"tiene fecha de vencimiento el día de *HOY ({venc_fmt})*"
        cierre_msg = "Agradecemos realizar el pago durante el día de hoy y compartirnos el comprobante para registrarlo en el sistema."
    else:
        dias_mora = abs(dias_diff)
        if dias_mora == 1:
            estado_msg = f"presenta *1 día de vencimiento* (fecha límite: *{venc_fmt}*)"
        else:
            estado_msg = f"presenta *{dias_mora} días de vencimiento* (fecha límite: *{venc_fmt}*)"
        cierre_msg = "Agradecemos ponerse al día lo antes posible y enviarnos el comprobante de pago por este medio para evitar la suspensión automática del servicio."

    return (
        f"Hola equipo de *{local.nombre_marca}*, les saludamos de *Zenic S.A.S.* 👋\n\n"
        f"Les informamos cordialmente que la factura *{factura.numero_factura}* "
        f"por valor de *{monto_fmt}* ({factura.tipo_cobro}) {estado_msg}.\n\n"
        f"💳 Cuentas autorizadas para transferencia:\n"
        f"• *Nu Bank / Nequi*\n\n"
        f"{cierre_msg} ¡Muchas gracias!"
    )


@ingresos_bp.route("/ingresos/<int:factura_id>/recordatorio", methods=["POST"])
@login_required
def enviar_recordatorio(factura_id):
    """Envía recordatorio de mora/preventivo por WhatsApp (permite mensaje editable) y guarda constancia histórica."""
    factura = Factura.query.get_or_404(factura_id)
    local = factura.local

    # Registrar constancia inmediatamente en la BD
    ahora = obtener_hora_bogota()
    factura.ultimo_recordatorio = ahora
    factura.recordatorio_enviado_por_id = current_user.id
    factura.total_recordatorios = (factura.total_recordatorios or 0) + 1
    db.session.commit()

    # Si el usuario editó el mensaje en el modal, usamos su texto; si no, generamos el predeterminado adaptable
    mensaje_custom = request.form.get("mensaje_wa", "").strip()
    if mensaje_custom:
        texto_wa = mensaje_custom
    else:
        texto_wa = generar_mensaje_recordatorio_wa(factura, ahora.date())

    telefono = (request.form.get("telefono_wa", "").strip()) or (local.telefono_cobro or "")
    # Limpiar número de teléfono
    tel_limpio = "".join(filter(str.isdigit, telefono))
    if len(tel_limpio) == 10:
        tel_limpio = "57" + tel_limpio # Colombia por defecto

    texto_encoded = urllib.parse.quote(texto_wa)
    if tel_limpio:
        wa_url = f"https://api.whatsapp.com/send?phone={tel_limpio}&text={texto_encoded}"
    else:
        wa_url = f"https://api.whatsapp.com/send?text={texto_encoded}"

    flash(
        f"📲 Constancia registrada: Recordatorio de cobro de #{factura.numero_factura} generado por {current_user.nombre}.",
        "info"
    )

    # Redirigir a WhatsApp Web o API
    return redirect(wa_url)


@ingresos_bp.route("/ingresos/<int:factura_id>/soporte")
@login_required
def soporte_factura(factura_id):
    factura = Factura.query.get_or_404(factura_id)
    return render_template("ingresos/soporte_factura.html", factura=factura)
