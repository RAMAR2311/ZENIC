import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required
from models import db, Personal, ActivoFijo, obtener_hora_bogota

operaciones_bp = Blueprint("operaciones_bp", __name__)

@operaciones_bp.route("/personal", methods=["GET", "POST"])
@login_required
def personal():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        cargo = request.form.get("cargo")
        telefono = request.form.get("telefono")
        email = request.form.get("email")
        
        if nombre and cargo:
            nuevo = Personal(nombre=nombre, cargo=cargo, telefono=telefono, email=email)
            db.session.add(nuevo)
            db.session.commit()
            flash("Personal registrado exitosamente.", "success")
        return redirect(url_for("operaciones_bp.personal"))
        
    empleados = Personal.query.order_by(Personal.nombre).all()
    return render_template("operaciones/personal.html", empleados=empleados)


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
        if documento and documento.filename != '':
            filename = secure_filename(documento.filename)
            # Agregar un prefijo para evitar colisiones
            filename = f"{obtener_hora_bogota().strftime('%Y%m%d%H%M%S')}_{filename}"
            documento.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            
        if descripcion and valor:
            p_id = int(personal_id) if personal_id else None
            nuevo = ActivoFijo(
                descripcion=descripcion,
                valor=float(valor),
                imei=imei,
                personal_id=p_id,
                documento_ruta=filename
            )
            db.session.add(nuevo)
            db.session.commit()
            flash("Equipo registrado correctamente.", "success")
        return redirect(url_for("operaciones_bp.equipos"))
        
    equipos_list = ActivoFijo.query.order_by(ActivoFijo.fecha_adquisicion.desc()).all()
    empleados = Personal.query.filter_by(estado="Activo").all()
    
    total_equipos = sum(float(e.valor) for e in equipos_list)
    
    return render_template("operaciones/equipos.html", equipos=equipos_list, empleados=empleados, total_equipos=total_equipos)
