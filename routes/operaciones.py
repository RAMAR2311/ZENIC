import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from models import db, Personal, ActivoFijo, User, TicketCambio, ContenidoMarketing, obtener_hora_bogota
from decorators import operaciones_finanzas_required

operaciones_bp = Blueprint("operaciones_bp", __name__)

ROLES_SISTEMA_VALIDOS = {"admin", "operaciones_finanzas", "ti", "marketing"}


@operaciones_bp.route("/personal", methods=["GET", "POST"])
@login_required
@operaciones_finanzas_required
def personal():
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        cargo = (request.form.get("cargo") or "").strip()
        telefono = (request.form.get("telefono") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        rol_sistema = (request.form.get("rol_sistema") or "").strip()
        password = request.form.get("password") or ""

        if not nombre or not cargo:
            flash("El nombre y el cargo son obligatorios.", "error")
            return redirect(url_for("operaciones_bp.personal"))

        user_vinculado = None

        # Si se seleccionó un rol para acceso al sistema
        if rol_sistema in ROLES_SISTEMA_VALIDOS:
            if not email:
                flash("Para asignar un rol de acceso al sistema es obligatorio ingresar un correo electrónico.", "error")
                return redirect(url_for("operaciones_bp.personal"))

            user_existente = User.query.filter_by(email=email).first()
            if user_existente:
                user_existente.nombre = nombre
                user_existente.rol = rol_sistema
                if password.strip():
                    user_existente.password_hash = generate_password_hash(password.strip())
                user_vinculado = user_existente
            else:
                if not password.strip():
                    flash("Debes asignar una contraseña para crear el nuevo usuario del sistema.", "error")
                    return redirect(url_for("operaciones_bp.personal"))
                nuevo_usuario = User(
                    nombre=nombre,
                    email=email,
                    password_hash=generate_password_hash(password.strip()),
                    rol=rol_sistema,
                )
                db.session.add(nuevo_usuario)
                db.session.flush()  # Obtener ID del usuario recién creado
                user_vinculado = nuevo_usuario

        nuevo = Personal(
            nombre=nombre,
            cargo=cargo,
            telefono=telefono or None,
            email=email or None,
            user_id=user_vinculado.id if user_vinculado else None,
        )
        db.session.add(nuevo)
        db.session.commit()

        if user_vinculado:
            flash(f"Empleado '{nombre}' registrado con acceso al sistema (Rol: {rol_sistema}).", "success")
        else:
            flash(f"Empleado '{nombre}' registrado exitosamente.", "success")
        return redirect(url_for("operaciones_bp.personal"))

    empleados = Personal.query.order_by(Personal.nombre).all()
    return render_template("operaciones/personal.html", empleados=empleados)


@operaciones_bp.route("/personal/<int:personal_id>/editar", methods=["POST"])
@operaciones_bp.route("/personal/<int:personal_id>/acceso", methods=["POST"])
@login_required
@operaciones_finanzas_required
def editar_personal(personal_id):
    """Permite editar todos los datos del empleado, su rol de acceso y su contraseña."""
    empleado = Personal.query.get_or_404(personal_id)

    nombre = (request.form.get("nombre") or empleado.nombre).strip()
    cargo = (request.form.get("cargo") or empleado.cargo).strip()
    telefono = (request.form.get("telefono") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    estado = (request.form.get("estado") or empleado.estado).strip()
    rol_sistema = (request.form.get("rol_sistema") or "").strip()
    password = (request.form.get("password") or "").strip()

    if not nombre or not cargo:
        flash("El nombre y el cargo no pueden estar vacíos.", "error")
        return redirect(url_for("operaciones_bp.personal"))

    empleado.nombre = nombre
    empleado.cargo = cargo
    empleado.telefono = telefono or None
    empleado.email = email or None
    empleado.estado = estado

    if rol_sistema in ROLES_SISTEMA_VALIDOS:
        if not email:
            flash("El empleado necesita un correo electrónico para poder ingresar al sistema.", "error")
            return redirect(url_for("operaciones_bp.personal"))

        # Verificar si el email ya pertenece a otro usuario distinto
        otro_usuario = User.query.filter(User.email == email, User.id != (empleado.user_id or 0)).first()
        if otro_usuario and empleado.usuario and otro_usuario.id != empleado.usuario.id:
            flash(f"El correo '{email}' ya está en uso por otro usuario del sistema.", "error")
            return redirect(url_for("operaciones_bp.personal"))

        usuario = empleado.usuario or otro_usuario
        if usuario:
            usuario.nombre = nombre
            usuario.email = email
            usuario.rol = rol_sistema
            if password:
                usuario.password_hash = generate_password_hash(password)
            empleado.user_id = usuario.id
        else:
            if not password:
                flash("Debes definir una contraseña inicial para habilitar el acceso al sistema.", "error")
                return redirect(url_for("operaciones_bp.personal"))
            nuevo_usuario = User(
                nombre=nombre,
                email=email,
                password_hash=generate_password_hash(password),
                rol=rol_sistema,
            )
            db.session.add(nuevo_usuario)
            db.session.flush()
            empleado.user_id = nuevo_usuario.id

        db.session.commit()
        flash(f"Empleado '{empleado.nombre}' actualizado correctamente.", "success")
    else:
        # Si se selecciona "Sin acceso al sistema" y tenía usuario vinculado
        if empleado.usuario:
            if empleado.usuario.id == current_user.id:
                flash("No puedes revocar el acceso al sistema de tu propio usuario activo.", "error")
                return redirect(url_for("operaciones_bp.personal"))
            usuario_antiguo = empleado.usuario
            empleado.user_id = None
            db.session.delete(usuario_antiguo)
        db.session.commit()
        flash(f"Datos de '{empleado.nombre}' actualizados correctamente.", "success")

    return redirect(url_for("operaciones_bp.personal"))


@operaciones_bp.route("/personal/<int:personal_id>/eliminar", methods=["POST"])
@login_required
@operaciones_finanzas_required
def eliminar_personal(personal_id):
    """Elimina un registro de personal y su usuario de acceso asociado (si no es el usuario actual)."""
    empleado = Personal.query.get_or_404(personal_id)

    if empleado.user_id and empleado.user_id == current_user.id:
        flash("No puedes eliminar tu propio perfil de usuario con el que tienes sesión iniciada.", "error")
        return redirect(url_for("operaciones_bp.personal"))

    nombre_eliminado = empleado.nombre
    usuario_asociado = empleado.usuario

    # Desvincular equipos asignados para no romper llaves foráneas
    for equipo in empleado.equipos:
        equipo.personal_id = None

    db.session.delete(empleado)

    # Si tenía usuario del sistema asociado, limpiar referencias y eliminarlo
    if usuario_asociado and usuario_asociado.id != current_user.id:
        TicketCambio.query.filter_by(asignado_id=usuario_asociado.id).update({"asignado_id": None})
        ContenidoMarketing.query.filter_by(autor_id=usuario_asociado.id).update({"autor_id": None})
        # Solo eliminar el usuario si no tiene tickets solicitados o notificaciones históricas críticas
        if not usuario_asociado.tickets_solicitados and not usuario_asociado.notificaciones_enviadas:
            db.session.delete(usuario_asociado)

    db.session.commit()
    flash(f"Empleado '{nombre_eliminado}' eliminado correctamente.", "success")
    return redirect(url_for("operaciones_bp.personal"))


@operaciones_bp.route("/equipos", methods=["GET", "POST"])
@login_required
def equipos():
    if request.method == "POST":
        descripcion = request.form.get("descripcion")
        valor = request.form.get("valor")
        imei = request.form.get("imei")
        personal_id = request.form.get("personal_id")

        documento = request.files.get("documento_entrega")
        filename = None
        if documento and documento.filename != "":
            filename = secure_filename(documento.filename)
            # Agregar un prefijo para evitar colisiones
            filename = f"{obtener_hora_bogota().strftime('%Y%m%d%H%M%S')}_{filename}"
            documento.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))

        if descripcion and valor:
            p_id = int(personal_id) if personal_id else None
            nuevo = ActivoFijo(
                descripcion=descripcion,
                valor=float(valor),
                imei=imei,
                personal_id=p_id,
                documento_ruta=filename,
            )
            db.session.add(nuevo)
            db.session.commit()
            flash("Equipo registrado correctamente.", "success")
        return redirect(url_for("operaciones_bp.equipos"))

    equipos_list = ActivoFijo.query.order_by(ActivoFijo.fecha_adquisicion.desc()).all()
    empleados = Personal.query.filter_by(estado="Activo").all()

    total_equipos = sum(float(e.valor) for e in equipos_list)

    return render_template("operaciones/equipos.html", equipos=equipos_list, empleados=empleados, total_equipos=total_equipos)
