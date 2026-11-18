import urllib.parse
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Local, Factura, Gasto, User, obtener_hora_bogota

ingresos_bp = Blueprint("ingresos_bp", __name__)

FECHA_CORTE_CAJA = date(2026, 11, 15)


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
        # Cuenta Nu
        facturas_nu = Factura.query.filter(
            Factura.estado == "Pagado",
            Factura.cuenta_destino == "Nu",
            Factura.fecha_pago >= FECHA_CORTE_CAJA
        ).all()
        ingresos_nu = sum(float(f.monto) for f in facturas_nu)

        gastos_nu_list = Gasto.query.filter(
            Gasto.cuenta_origen == "Nu",
            Gasto.fecha >= FECHA_CORTE_CAJA
        ).all()
        gastos_nu = sum(float(g.monto) for g in gastos_nu_list)
        saldo_nu = ingresos_nu - gastos_nu

        # Cuenta Nequi
        facturas_nequi = Factura.query.filter(
            Factura.estado == "Pagado",
            Factura.cuenta_destino == "Nequi",
            Factura.fecha_pago >= FECHA_CORTE_CAJA
        ).all()
        ingresos_nequi = sum(float(f.monto) for f in facturas_nequi)

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

        # Monto
        if monto_custom and float(monto_custom) > 0:
            monto = float(monto_custom)
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


@ingresos_bp.route("/ingresos/<int:factura_id>/recordatorio", methods=["POST"])
@login_required
def enviar_recordatorio(factura_id):
    """Envía recordatorio de mora por WhatsApp y guarda constancia histórica de envío."""
    factura = Factura.query.get_or_404(factura_id)
    local = factura.local

    # Registrar constancia inmediatamente en la BD
    ahora = obtener_hora_bogota()
    factura.ultimo_recordatorio = ahora
    factura.recordatorio_enviado_por_id = current_user.id
    factura.total_recordatorios = (factura.total_recordatorios or 0) + 1
    db.session.commit()

    # Formatear mensaje para WhatsApp
    monto_fmt = f"${float(factura.monto):,.0f} COP".replace(",", ".")
    venc_fmt = factura.fecha_vencimiento.strftime("%d/%m/%Y")
    dias_atraso = (ahora.date() - factura.fecha_vencimiento).days

    if dias_atraso > 0:
        estado_msg = f"presenta {dias_atraso} día(s) de vencimiento (fecha límite: {venc_fmt})"
    else:
        estado_msg = f"vence el próximo {venc_fmt}"

    texto_wa = (
        f"Hola equipo de *{local.nombre_marca}*, les saludamos de *Zenic S.A.S.* 👋\n\n"
        f"Les recordamos cordialmente que la factura *{factura.numero_factura}* "
        f"por valor de *{monto_fmt}* ({factura.tipo_cobro}) {estado_msg}.\n\n"
        f"💳 Cuentas autorizadas para transferencia:\n"
        f"• *Nu Bank / Nequi*\n\n"
        f"Agradecemos enviarnos el comprobante de pago por este medio para validar y mantener su servicio activo. ¡Muchas gracias!"
    )

    telefono = local.telefono_cobro or ""
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
