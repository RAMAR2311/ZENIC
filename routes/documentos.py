"""
routes/documentos.py — Módulo de Gestión Documental | Zenic Master Control
==========================================================================
Almacena y gestiona:
1. Documentación interna de Zenic (procesos, arquitectura, actas).
2. Documentación legal de clientes (RUT, Cámara de Comercio, Contratos, etc.).
3. Manuales y guías técnicas de sistemas (POS, Facturación Electrónica, etc.).
"""

import os
from datetime import datetime
from werkzeug.utils import secure_filename

from flask import (
    Blueprint, render_template, request, flash,
    redirect, url_for, send_from_directory, current_app, abort
)
from flask_login import login_required, current_user
from models import db, Documento, Local, obtener_hora_bogota

documentos_bp = Blueprint("documentos_bp", __name__, url_prefix="/documentos")

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "csv",
    "ppt", "pptx", "txt", "zip", "rar", "7z",
    "png", "jpg", "jpeg", "webp", "svg"
}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@documentos_bp.route("/")
@login_required
def index():
    """Listado principal con filtros por tipo, local, categoría y búsqueda."""
    tipo_filtro = request.args.get("tipo", "").strip()
    local_filtro = request.args.get("local_id", "").strip()
    categoria_filtro = request.args.get("categoria", "").strip()
    busqueda = request.args.get("q", "").strip()

    query = Documento.query

    if tipo_filtro:
        query = query.filter(Documento.tipo == tipo_filtro)
    if local_filtro:
        query = query.filter(Documento.local_id == int(local_filtro))
    if categoria_filtro:
        query = query.filter(Documento.categoria == categoria_filtro)
    if busqueda:
        termino = f"%{busqueda}%"
        query = query.filter(
            (Documento.titulo.ilike(termino)) |
            (Documento.descripcion.ilike(termino)) |
            (Documento.categoria.ilike(termino))
        )

    documentos = query.order_by(Documento.fecha_creacion.desc()).all()
    locales = Local.query.order_by(Local.nombre_marca).all()

    # Métricas para las tarjetas de resumen
    total_documentos = Documento.query.count()
    total_zenic = Documento.query.filter_by(tipo="zenic").count()
    total_clientes = Documento.query.filter_by(tipo="cliente").count()
    total_manuales = Documento.query.filter_by(tipo="manual").count()

    # Categorías distintas existentes para sugerir
    categorias_existentes = [
        c[0] for c in db.session.query(Documento.categoria).distinct().all() if c[0]
    ]

    return render_template(
        "documentos/index.html",
        documentos=documentos,
        locales=locales,
        total_documentos=total_documentos,
        total_zenic=total_zenic,
        total_clientes=total_clientes,
        total_manuales=total_manuales,
        tipo_filtro=tipo_filtro,
        local_filtro=local_filtro,
        categoria_filtro=categoria_filtro,
        busqueda=busqueda,
        categorias_existentes=categorias_existentes,
    )


@documentos_bp.route("/nuevo", methods=["POST"])
@login_required
def nuevo_documento():
    """Crea un nuevo registro documental con archivo físico o enlace externo."""
    titulo = request.form.get("titulo", "").strip()
    tipo = request.form.get("tipo", "zenic").strip()
    categoria = request.form.get("categoria", "General").strip() or "General"
    descripcion = request.form.get("descripcion", "").strip()
    version = request.form.get("version", "1.0").strip() or "1.0"
    enlace_externo = request.form.get("enlace_externo", "").strip()
    local_id_raw = request.form.get("local_id")

    local_id = int(local_id_raw) if local_id_raw and local_id_raw.isdigit() else None

    if not titulo:
        flash("El título del documento es obligatorio.", "danger")
        return redirect(url_for("documentos_bp.index"))

    archivo = request.files.get("archivo")
    archivo_ruta = None
    archivo_nombre_original = None
    archivo_tamano = 0
    archivo_extension = None

    if archivo and archivo.filename:
        if not allowed_file(archivo.filename):
            flash(
                "Tipo de archivo no permitido. Formatos aceptados: PDF, Office, Imágenes y Archivos ZIP/RAR.",
                "danger",
            )
            return redirect(url_for("documentos_bp.index"))

        original_sec = secure_filename(archivo.filename)
        extension = original_sec.rsplit(".", 1)[1].lower() if "." in original_sec else ""
        nombre_guardado = f"doc_{int(datetime.now().timestamp())}_{original_sec}"

        carpeta_destino = current_app.config.get("UPLOAD_FOLDER")
        os.makedirs(carpeta_destino, exist_ok=True)
        ruta_completa = os.path.join(carpeta_destino, nombre_guardado)

        archivo.save(ruta_completa)
        tamano = os.path.getsize(ruta_completa) if os.path.exists(ruta_completa) else 0

        archivo_ruta = nombre_guardado
        archivo_nombre_original = original_sec
        archivo_tamano = tamano
        archivo_extension = extension

    if not archivo_ruta and not enlace_externo:
        flash("Debes adjuntar un archivo o suministrar un enlace externo.", "warning")
        return redirect(url_for("documentos_bp.index"))

    doc = Documento(
        titulo=titulo,
        tipo=tipo,
        categoria=categoria,
        descripcion=descripcion,
        local_id=local_id,
        version=version,
        enlace_externo=enlace_externo or None,
        archivo_ruta=archivo_ruta,
        archivo_nombre_original=archivo_nombre_original,
        archivo_tamano=archivo_tamano,
        archivo_extension=archivo_extension,
        autor_id=current_user.id,
    )

    db.session.add(doc)
    db.session.commit()
    flash(f"Documento «{doc.titulo}» guardado exitosamente.", "success")
    return redirect(url_for("documentos_bp.index", tipo=tipo if tipo else ""))


@documentos_bp.route("/<int:doc_id>/descargar")
@login_required
def descargar_documento(doc_id):
    """Descarga el archivo físico adjunto."""
    doc = Documento.query.get_or_404(doc_id)
    if not doc.archivo_ruta:
        flash("Este registro no contiene un archivo físico descargable.", "warning")
        return redirect(url_for("documentos_bp.index"))

    carpeta = current_app.config.get("UPLOAD_FOLDER")
    nombre_descarga = doc.archivo_nombre_original or doc.archivo_ruta
    return send_from_directory(
        carpeta,
        doc.archivo_ruta,
        as_attachment=True,
        download_name=nombre_descarga,
    )


@documentos_bp.route("/<int:doc_id>/ver")
@login_required
def ver_archivo(doc_id):
    """Visualización en línea para navegadores (PDF o imágenes)."""
    doc = Documento.query.get_or_404(doc_id)
    if doc.enlace_externo and not doc.archivo_ruta:
        return redirect(doc.enlace_externo)

    if not doc.archivo_ruta:
        flash("No hay archivo para previsualizar.", "warning")
        return redirect(url_for("documentos_bp.index"))

    carpeta = current_app.config.get("UPLOAD_FOLDER")
    return send_from_directory(
        carpeta,
        doc.archivo_ruta,
        as_attachment=False,
    )


@documentos_bp.route("/<int:doc_id>/editar", methods=["POST"])
@login_required
def editar_documento(doc_id):
    """Actualiza metadatos y opcionalmente reemplaza el archivo."""
    doc = Documento.query.get_or_404(doc_id)

    titulo = request.form.get("titulo", "").strip()
    tipo = request.form.get("tipo", doc.tipo).strip()
    categoria = request.form.get("categoria", doc.categoria).strip()
    descripcion = request.form.get("descripcion", "").strip()
    version = request.form.get("version", doc.version).strip()
    enlace_externo = request.form.get("enlace_externo", "").strip()
    local_id_raw = request.form.get("local_id")

    if titulo:
        doc.titulo = titulo
    doc.tipo = tipo
    doc.categoria = categoria or "General"
    doc.descripcion = descripcion
    doc.version = version or "1.0"
    doc.enlace_externo = enlace_externo or None
    doc.local_id = int(local_id_raw) if local_id_raw and local_id_raw.isdigit() else None

    # Si suben un nuevo archivo para reemplazar
    archivo = request.files.get("archivo")
    if archivo and archivo.filename:
        if allowed_file(archivo.filename):
            carpeta_destino = current_app.config.get("UPLOAD_FOLDER")
            # Eliminar archivo antiguo si existía
            if doc.archivo_ruta:
                ruta_antigua = os.path.join(carpeta_destino, doc.archivo_ruta)
                if os.path.exists(ruta_antigua):
                    try:
                        os.remove(ruta_antigua)
                    except Exception:
                        pass

            original_sec = secure_filename(archivo.filename)
            extension = original_sec.rsplit(".", 1)[1].lower() if "." in original_sec else ""
            nombre_guardado = f"doc_{int(datetime.now().timestamp())}_{original_sec}"
            ruta_completa = os.path.join(carpeta_destino, nombre_guardado)
            archivo.save(ruta_completa)

            doc.archivo_ruta = nombre_guardado
            doc.archivo_nombre_original = original_sec
            doc.archivo_tamano = os.path.getsize(ruta_completa)
            doc.archivo_extension = extension

    doc.fecha_actualizacion = obtener_hora_bogota()
    db.session.commit()
    flash(f"Documento «{doc.titulo}» actualizado correctamente.", "success")
    return redirect(url_for("documentos_bp.index"))


@documentos_bp.route("/<int:doc_id>/eliminar", methods=["POST"])
@login_required
def eliminar_documento(doc_id):
    """Elimina el registro y el archivo físico del disco."""
    doc = Documento.query.get_or_404(doc_id)
    titulo = doc.titulo

    # Eliminar archivo del sistema de archivos
    if doc.archivo_ruta:
        carpeta = current_app.config.get("UPLOAD_FOLDER")
        ruta_archivo = os.path.join(carpeta, doc.archivo_ruta)
        if os.path.exists(ruta_archivo):
            try:
                os.remove(ruta_archivo)
            except Exception:
                pass

    db.session.delete(doc)
    db.session.commit()
    flash(f"Documento «{titulo}» eliminado correctamente.", "success")
    return redirect(url_for("documentos_bp.index"))
