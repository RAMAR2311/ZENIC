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

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort, current_app
from flask_login import login_required, current_user

from models import db, TicketCambio, Local, User, obtener_hora_bogota
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
    """Creación de un nuevo ticket de soporte por parte de Operaciones o Admin con soporte de múltiples adjuntos multimedia."""
    titulo = request.form.get("titulo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    local_id = request.form.get("local_id")
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
        categoria=categoria,
        prioridad=prioridad,
        solicitante_id=current_user.id,
        estado="Pendiente",
        adjunto_ruta=adjunto_ruta,
        adjunto_tipo=adjunto_tipo
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
