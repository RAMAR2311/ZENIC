"""
routes/ti.py — Módulo de TI: Conexiones, Uptime & Tickets de Cambios
====================================================================
Gestiona las solicitudes técnicas creadas por Operaciones para los clientes
y centraliza los accesos a instancias y monitor de estado.
Incluye optimización y compresión automática de imágenes y videos adjuntos.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort, current_app, jsonify
from flask_login import login_required, current_user

from models import db, TicketCambio, Local, User, BitacoraCliente, obtener_hora_bogota
from decorators import ti_required, tickets_access_required, admin_required

ti_bp = Blueprint("ti_bp", __name__, url_prefix="/ti")

EXTENSIONES_IMAGENES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
EXTENSIONES_VIDEOS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE = 45 * 1024 * 1024  # 45 MB máximo antes de compresión


def optimizar_imagen(input_file, output_path, max_dim=1280, quality=80):
    """
    Redimensiona y comprime una imagen a formato JPEG o WebP optimizado
    manteniendo la proporción y corrigiendo la rotación EXIF si viene de celular.
    """
    img = Image.open(input_file)
    # Corregir orientación de fotos tomadas con móvil (cámara vertical/horizontal)
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    width, height = img.size
    if width > max_dim or height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    img.save(output_path, "JPEG", optimize=True, quality=quality)


def optimizar_video(input_path, output_path):
    """
    Intenta comprimir video usando ffmpeg si está disponible en el servidor.
    Reduce resolución a máx 720p y usa H.264/AAC con CRF 28 para reducir peso drásticamente.
    Si ffmpeg no está disponible, se copia el video original directamente.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        shutil.copyfile(input_path, output_path)
        return

    # Comando ffmpeg para reducción de tamaño eficiente
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", input_path,
        "-vcodec", "libx264",
        "-crf", "28",
        "-preset", "faster",
        "-vf", "scale='min(1280,iw)':-2",
        "-acodec", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if res.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            shutil.copyfile(input_path, output_path)
    except Exception:
        shutil.copyfile(input_path, output_path)


def procesar_adjunto_ticket(archivo):
    """
    Valida, comprime y almacena el archivo adjunto (imagen o video).
    Retorna tupla: (nombre_archivo_final, tipo_adjunto)
    """
    if not archivo or not archivo.filename:
        return None, None

    filename_orig = secure_filename(archivo.filename)
    if not filename_orig:
        return None, None

    _, ext = os.path.splitext(filename_orig)
    ext = ext.lower()

    if ext not in EXTENSIONES_IMAGENES and ext not in EXTENSIONES_VIDEOS:
        raise ValueError("Formato de archivo no permitido. Solo se aceptan imágenes (JPG, PNG, WEBP) o videos (MP4, MOV, WEBM).")

    upload_folder = current_app.config.get("TICKETS_UPLOAD_FOLDER")
    os.makedirs(upload_folder, exist_ok=True)

    timestamp = obtener_hora_bogota().strftime("%Y%m%d%H%M%S")

    if ext in EXTENSIONES_IMAGENES:
        filename_final = f"ticket_{timestamp}_{filename_orig[:20]}.jpg"
        output_path = os.path.join(upload_folder, filename_final)
        optimizar_imagen(archivo.stream, output_path)
        return filename_final, "imagen"

    elif ext in EXTENSIONES_VIDEOS:
        temp_input_filename = f"temp_{timestamp}_{filename_orig}"
        temp_input_path = os.path.join(upload_folder, temp_input_filename)
        archivo.save(temp_input_path)

        filename_final = f"ticket_{timestamp}_{os.path.splitext(filename_orig)[0][:20]}.mp4"
        output_path = os.path.join(upload_folder, filename_final)

        try:
            optimizar_video(temp_input_path, output_path)
        finally:
            if os.path.exists(temp_input_path):
                try:
                    os.remove(temp_input_path)
                except OSError:
                    pass

        return filename_final, "video"

    return None, None


@ti_bp.route("/tickets", methods=["GET"])
@login_required
@tickets_access_required
def tickets():
    """
    Módulo Universal de Tickets, Asignaciones y Validación:
    Permite ver Todos los tickets, Mis Tickets Asignados (pendientes por resolver)
    y los Tickets Por Validar (que el usuario asignó y ya fueron solucionados).
    """
    estado_filtro = request.args.get("estado", "")
    local_filtro = request.args.get("local_id", "")
    vista_activa = request.args.get("vista", "") # 'mis_asignados', 'por_validar', 'todos'

    query = TicketCambio.query.order_by(
        TicketCambio.fecha_actualizacion.desc(),
        TicketCambio.fecha_creacion.desc()
    )

    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)
    if local_filtro and local_filtro.isdigit():
        query = query.filter_by(local_id=int(local_filtro))

    tickets_list = query.all()
    locales = Local.query.order_by(Local.nombre_marca).all()
    usuarios = User.query.order_by(User.nombre).all()

    # Subconjuntos personalizados para el usuario actual
    mis_asignados = [
        t for t in tickets_list
        if t.asignado_id == current_user.id and t.estado in ("Pendiente", "En Desarrollo", "Requiere Ajustes")
    ]
    por_validar_mios = [
        t for t in tickets_list
        if (t.solicitante_id == current_user.id or current_user.rol == "admin") and t.estado == "Por Validar"
    ]

    # Si el usuario no especificó pestaña pero tiene tickets asignados pendientes, mostrarle esos primero si no es admin/operaciones, o mantener vista inteligente
    if not vista_activa:
        if len(mis_asignados) > 0 and current_user.rol in ("ti", "marketing"):
            vista_activa = "mis_asignados"
        elif len(por_validar_mios) > 0:
            vista_activa = "por_validar"
        else:
            vista_activa = "todos"

    # Métricas rápidas
    total_pendientes = TicketCambio.query.filter(TicketCambio.estado.in_(["Pendiente", "En Desarrollo", "Requiere Ajustes"])).count()
    total_por_validar = TicketCambio.query.filter_by(estado="Por Validar").count()
    total_urgentes = TicketCambio.query.filter(TicketCambio.prioridad == "Urgente", TicketCambio.estado != "Resuelto").count()
    total_resueltos = TicketCambio.query.filter_by(estado="Resuelto").count()

    return render_template(
        "ti/tickets.html",
        tickets=tickets_list,
        mis_asignados=mis_asignados,
        por_validar_mios=por_validar_mios,
        vista_activa=vista_activa,
        locales=locales,
        usuarios=usuarios,
        usuarios_ti=usuarios,
        total_pendientes=total_pendientes,
        total_por_validar=total_por_validar,
        total_urgentes=total_urgentes,
        total_resueltos=total_resueltos,
        estado_filtro=estado_filtro,
        local_filtro=local_filtro
    )


@ti_bp.route("/tickets/nuevo", methods=["POST"])
@login_required
@tickets_access_required
def nuevo_ticket():
    """Creación de un nuevo ticket de soporte por parte de Operaciones o Admin con soporte de múltiples adjuntos multimedia."""
    titulo = request.form.get("titulo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    local_id = request.form.get("local_id")
    asignado_id = request.form.get("asignado_id")
    categoria = request.form.get("categoria", "Soporte")
    prioridad = request.form.get("prioridad", "Media")
    archivos_adjuntos = request.files.getlist("adjunto")

    if not titulo or not descripcion:
        flash("El título y la descripción son obligatorios.", "error")
        return redirect(url_for("ti_bp.tickets"))

    adjuntos_procesados = []

    for archivo in archivos_adjuntos:
        if archivo and archivo.filename:
            try:
                ruta, tipo = procesar_adjunto_ticket(archivo)
                if ruta:
                    adjuntos_procesados.append({"ruta": ruta, "tipo": tipo})
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("ti_bp.tickets"))
            except Exception as e:
                flash(f"Error procesando archivo '{archivo.filename}': {str(e)}", "error")
                return redirect(url_for("ti_bp.tickets"))

    adjunto_ruta = None
    adjunto_tipo = None

    if adjuntos_procesados:
        if len(adjuntos_procesados) == 1:
            adjunto_ruta = adjuntos_procesados[0]["ruta"]
            adjunto_tipo = adjuntos_procesados[0]["tipo"]
        else:
            adjunto_ruta = json.dumps(adjuntos_procesados)
            adjunto_tipo = "multiple"

    ticket = TicketCambio(
        titulo=titulo,
        descripcion=descripcion,
        local_id=int(local_id) if local_id else None,
        asignado_id=int(asignado_id) if (asignado_id and asignado_id.strip()) else None,
        categoria=categoria,
        prioridad=prioridad,
        solicitante_id=current_user.id,
        estado="Pendiente",
        adjunto_ruta=adjunto_ruta,
        adjunto_tipo=adjunto_tipo
    )

    db.session.add(ticket)
    db.session.flush()

    if ticket.local_id:
        db.session.add(BitacoraCliente(
            local_id=ticket.local_id,
            user_id=current_user.id,
            tipo="Ticket",
            titulo=f"Ticket #{ticket.id} creado: {ticket.titulo}",
            detalle=f"Categoría: {ticket.categoria} · Prioridad: {ticket.prioridad} · {ticket.descripcion[:160]}"
        ))

    db.session.commit()

    flash(f"Ticket #{ticket.id} registrado correctamente.", "success")
    next_url = request.form.get("next_url")
    if next_url:
        return redirect(next_url)
    return redirect(url_for("ti_bp.tickets"))


@ti_bp.route("/tickets/<int:ticket_id>/actualizar", methods=["POST"])
@login_required
@tickets_access_required
def actualizar_ticket(ticket_id):
    """
    Permite a la persona asignada (de cualquier perfil) o a TI/Admin/Solicitante:
    - Cambiar el estado del ticket (ej. 'En Desarrollo', 'Por Validar')
    - Reasignar responsable si aplica
    - Dejar su comentario de solución después de realizar el cambio
    """
    ticket = TicketCambio.query.get_or_404(ticket_id)

    nuevo_estado = request.form.get("estado")
    asignado_id = request.form.get("asignado_id")
    notas = request.form.get("notas_resolucion")

    if nuevo_estado:
        ticket.estado = nuevo_estado
        if nuevo_estado == "Resuelto":
            ticket.fecha_cierre = obtener_hora_bogota()
            ticket.validado_por_solicitante = True
        else:
            ticket.fecha_cierre = None
            if nuevo_estado in ("Por Validar", "Requiere Ajustes", "Pendiente", "En Desarrollo"):
                ticket.validado_por_solicitante = False

    if asignado_id is not None and (current_user.rol in ["admin", "operaciones_finanzas", "ti"] or ticket.solicitante_id == current_user.id):
        ticket.asignado_id = int(asignado_id) if (asignado_id and asignado_id.strip()) else None

    if notas is not None and notas.strip():
        ticket.notas_resolucion = notas.strip()

    notas_val = request.form.get("notas_validacion")
    if notas_val is not None and notas_val.strip():
        ticket.notas_validacion = notas_val.strip()

    if ticket.local_id:
        db.session.add(BitacoraCliente(
            local_id=ticket.local_id,
            user_id=current_user.id,
            tipo="Ticket",
            titulo=f"Ticket #{ticket.id} pasó a «{ticket.estado}» por {current_user.nombre.split()[0]}",
            detalle=ticket.notas_resolucion or f"Actualización en ticket ({ticket.titulo})."
        ))

    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json":
        return jsonify({
            "ok": True,
            "ticket_id": ticket.id,
            "estado": ticket.estado,
            "mensaje": f"Ticket #{ticket.id} actualizado a «{ticket.estado}»."
        })

    if ticket.estado == "Por Validar":
        flash(f"✅ Ticket #{ticket.id} marcado como solucionado y enviado a validación de quien lo solicitó.", "success")
    elif ticket.estado == "Requiere Ajustes":
        flash(f"🔄 Ticket #{ticket.id} devuelto a «Requiere Ajustes». Se notificó al responsable asignado.", "info")
    else:
        flash(f"✅ Ticket #{ticket.id} actualizado a «{ticket.estado}».", "success")

    next_url = request.form.get("next_url")
    if next_url:
        return redirect(next_url)
    return redirect(url_for("ti_bp.tickets"))


@ti_bp.route("/api/notificaciones", methods=["GET"])
@login_required
def api_notificaciones_tickets():
    """
    Endpoint JSON en tiempo real para notificaciones en PC, Android y iPhone (PWA/Navegador).
    Devuelve los tickets asignados al usuario actual (incluyendo los devueltos a 'Requiere Ajustes')
    y los tickets que el usuario asignó y están listos 'Por Validar'.
    """
    asignados = TicketCambio.query.filter(
        TicketCambio.asignado_id == current_user.id,
        TicketCambio.estado.in_(["Pendiente", "En Desarrollo", "Requiere Ajustes"])
    ).order_by(TicketCambio.fecha_actualizacion.desc()).all()

    por_validar = TicketCambio.query.filter(
        TicketCambio.solicitante_id == current_user.id,
        TicketCambio.estado == "Por Validar"
    ).order_by(TicketCambio.fecha_actualizacion.desc()).all()

    items = []
    for t in asignados:
        es_ajuste = (t.estado == "Requiere Ajustes")
        ts = (t.fecha_actualizacion or t.fecha_creacion).strftime("%Y-%m-%d %H:%M:%S")
        items.append({
            "key": f"asig_{t.id}_{t.estado}_{ts}",
            "id": t.id,
            "titulo": t.titulo,
            "estado": t.estado,
            "prioridad": t.prioridad,
            "tipo": "ajustes" if es_ajuste else "asignado",
            "encabezado": f"🔄 Revisar nuevamente Ticket #{t.id}" if es_ajuste else f"🛠️ Ticket #{t.id} asignado ({t.estado})",
            "mensaje": (f"Observación: {t.notas_validacion}" if (es_ajuste and t.notas_validacion) else t.titulo),
            "url": url_for("ti_bp.tickets", vista="mis_asignados")
        })

    for tv in por_validar:
        ts = (tv.fecha_actualizacion or tv.fecha_creacion).strftime("%Y-%m-%d %H:%M:%S")
        resp_nombre = tv.asignado.nombre.split()[0] if tv.asignado else "Responsable"
        items.append({
            "key": f"val_{tv.id}_{tv.estado}_{ts}",
            "id": tv.id,
            "titulo": tv.titulo,
            "estado": tv.estado,
            "prioridad": tv.prioridad,
            "tipo": "por_validar",
            "encabezado": f"✅ Ticket #{tv.id} listo para validar",
            "mensaje": f"{resp_nombre} reportó solución: {tv.notas_resolucion or tv.titulo}",
            "url": url_for("ti_bp.tickets", vista="por_validar")
        })

    return jsonify({
        "ok": True,
        "total": len(items),
        "asignados_count": len(asignados),
        "por_validar_count": len(por_validar),
        "items": items
    })


@ti_bp.route("/tickets/<int:ticket_id>/validar", methods=["POST"])
@login_required
@tickets_access_required
def validar_ticket(ticket_id):
    """
    Permite a la persona que creó/asignó el ticket (o Admin/Operaciones) validar el trabajo:
    - 'aprobar': Marca el ticket como 'Resuelto', validado_por_solicitante=True y guarda su comentario de conformidad.
    - 'revisar': Devuelve el ticket a 'Requiere Ajustes' y guarda el comentario con lo que falta por revisar para que le notifique al responsable.
    """
    ticket = TicketCambio.query.get_or_404(ticket_id)
    decision = request.form.get("decision", "aprobar").strip() # 'aprobar' o 'revisar'
    comentario = request.form.get("notas_validacion", "").strip()

    if decision == "aprobar":
        ticket.estado = "Resuelto"
        ticket.validado_por_solicitante = True
        ticket.fecha_cierre = obtener_hora_bogota()
        ticket.notas_validacion = comentario or "Validado y aprobado conforme por el solicitante."
        msg_flash = f"✅ Ticket #{ticket.id} validado y cerrado exitosamente como Resuelto."
        cat_flash = "success"
    else:
        ticket.estado = "Requiere Ajustes"
        ticket.validado_por_solicitante = False
        ticket.fecha_cierre = None
        ticket.notas_validacion = comentario or "Se requiere revisar algunos detalles adicionales."
        msg_flash = f"🔄 Se solicitaron ajustes en el Ticket #{ticket.id}. El responsable ha sido notificado."
        cat_flash = "info"

    if ticket.local_id:
        db.session.add(BitacoraCliente(
            local_id=ticket.local_id,
            user_id=current_user.id,
            tipo="Ticket",
            titulo=f"Validación de Ticket #{ticket.id}: «{ticket.estado}»",
            detalle=f"Comentario de {current_user.nombre.split()[0]}: {ticket.notas_validacion}"
        ))

    db.session.commit()
    flash(msg_flash, cat_flash)

    next_url = request.form.get("next_url")
    if next_url:
        return redirect(next_url)
    return redirect(url_for("ti_bp.tickets"))


@ti_bp.route("/tickets/<int:ticket_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def eliminar_ticket(ticket_id):
    """Eliminación definitiva de un ticket (restringido únicamente al rol admin)."""
    ticket = TicketCambio.query.get_or_404(ticket_id)
    id_ticket = ticket.id

    # Eliminar archivos adjuntos del servidor si existen
    upload_folder = current_app.config.get("TICKETS_UPLOAD_FOLDER")
    if upload_folder:
        for adj in ticket.adjuntos:
            ruta = adj.get("ruta")
            if ruta:
                archivo_path = os.path.join(upload_folder, ruta)
                if os.path.exists(archivo_path):
                    try:
                        os.remove(archivo_path)
                    except OSError:
                        pass

    db.session.delete(ticket)
    db.session.commit()

    flash(f"Ticket #{id_ticket} eliminado correctamente del sistema.", "success")
    return redirect(url_for("ti_bp.tickets"))


@ti_bp.route("/conexiones")
@login_required
@ti_required
def conexiones():
    """Centro de conexiones de sistemas: Uptime, URLs y acceso a servidores."""
    locales = Local.query.order_by(Local.nombre_marca).all()
    return render_template("ti/conexiones.html", locales=locales)
