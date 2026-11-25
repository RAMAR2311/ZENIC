"""
seed_ficticios.py -- Genera datos de prueba realistas para Zenic Master Control.
Incluye Locales clientes, Facturas, Finanzas (Ingresos/Gastos), Personal,
Equipos, Tickets de TI, Campañas de Marketing y Notificaciones.
"""
import os
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from models import (
    db, User, Local, Factura, Ingreso, Gasto, PresupuestoArea,
    Tesoreria, Personal, ActivoFijo, TicketCambio,
    ContenidoMarketing, SesionGrabacion, Notificacion, Documento, obtener_hora_bogota
)
from werkzeug.security import generate_password_hash
from crypto_utils import encrypt_password

app = create_app()

with app.app_context():
    print("Iniciando inyeccion de datos ficticios...")
    hoy = obtener_hora_bogota().date()
    mes_actual = hoy.month
    ano_actual = hoy.year

    # 1. Usuarios adicionales
    usuarios_data = [
        {"nombre": "Carlos Medina (TI Lead)", "email": "carlos.ti@zenic.co", "rol": "ti", "pass": "Zenic2026!"},
        {"nombre": "Laura Gomez (Marketing)", "email": "laura.mkt@zenic.co", "rol": "marketing", "pass": "Zenic2026!"},
        {"nombre": "Andres Rios (Operaciones)", "email": "andres.ops@zenic.co", "rol": "operaciones_finanzas", "pass": "Zenic2026!"},
        {"nombre": "Jhon (Operaciones & Finanzas)", "email": "operaciones@zenic.co", "rol": "operaciones_finanzas", "pass": "Zenic2026!"},
    ]
    users_map = {}
    master_admin = User.query.filter_by(email="admin@zenic.co").first()
    if not master_admin:
        master_admin = User(
            nombre="Master Admin - Zenic S.A.S.",
            email="admin@zenic.co",
            password_hash=generate_password_hash("Zenic2026!"),
            rol="admin"
        )
        db.session.add(master_admin)
        db.session.commit()
    users_map["admin"] = master_admin

    for u in usuarios_data:
        usr = User.query.filter_by(email=u["email"]).first()
        if not usr:
            usr = User(
                nombre=u["nombre"],
                email=u["email"],
                password_hash=generate_password_hash(u["pass"]),
                rol=u["rol"]
            )
            db.session.add(usr)
            db.session.commit()
        users_map[u["rol"]] = usr
    print("[OK] Usuarios creados/verificados.")

    # 2. Locales / Instancias de Clientes
    locales_data = [
        {
            "nombre_marca": "Tekfix Girardot",
            "url_instancia": "https://tekfix.zenic.cloud",
            "fecha_lanzamiento": hoy - timedelta(days=120),
            "version_software": "1.3.4",
            "inversion_inicial": 8500000.00,
            "mensualidad": 450000.00,
            "dia_pago": 5,
            "estado_pago": "Activo",
            "email_raw": "admin@tekfix.co",
            "pass_raw": "TekfixSecure2026",
            "is_online": True,
        },
        {
            "nombre_marca": "Sarotex Medellín",
            "url_instancia": "https://sarotex.zenic.cloud",
            "fecha_lanzamiento": hoy - timedelta(days=90),
            "version_software": "1.3.2",
            "inversion_inicial": 12000000.00,
            "mensualidad": 650000.00,
            "dia_pago": min(hoy.day + 2, 28), # Por vencer (semáforo amarillo)
            "estado_pago": "Activo",
            "email_raw": "gerencia@sarotex.com",
            "pass_raw": "SaroTex!9921",
            "is_online": True,
        },
        {
            "nombre_marca": "ElectroFast Cali",
            "url_instancia": "https://electrofast.zenic.cloud",
            "fecha_lanzamiento": hoy - timedelta(days=60),
            "version_software": "1.2.9",
            "inversion_inicial": 6500000.00,
            "mensualidad": 380000.00,
            "dia_pago": 1,
            "estado_pago": "Pendiente", # Semáforo rojo
            "email_raw": "admin@electrofast.co",
            "pass_raw": "Electro#2026",
            "is_online": True,
        },
        {
            "nombre_marca": "Mundo Móvil Bogotá",
            "url_instancia": "https://mundomovil.zenic.cloud",
            "fecha_lanzamiento": hoy - timedelta(days=200),
            "version_software": "1.1.0",
            "inversion_inicial": 9000000.00,
            "mensualidad": 500000.00,
            "dia_pago": 15,
            "estado_pago": "Suspendido", # Semáforo rojo
            "email_raw": "contacto@mundomovil.com",
            "pass_raw": "MundoClave88*",
            "is_online": False,
        },
        {
            "nombre_marca": "NovaTech Barranquilla",
            "url_instancia": "https://novatech.zenic.cloud",
            "fecha_lanzamiento": hoy - timedelta(days=40),
            "version_software": "1.4.0",
            "inversion_inicial": 11000000.00,
            "mensualidad": 700000.00,
            "dia_pago": 25,
            "estado_pago": "Activo",
            "email_raw": "ti@novatech.co",
            "pass_raw": "NovaTechSafe_1",
            "is_online": True,
        },
        {
            "nombre_marca": "UrbanStyle Bucaramanga",
            "url_instancia": "https://urbanstyle.zenic.cloud",
            "fecha_lanzamiento": hoy - timedelta(days=15),
            "version_software": "1.4.0",
            "inversion_inicial": 7800000.00,
            "mensualidad": 420000.00,
            "dia_pago": 20,
            "estado_pago": "Activo",
            "email_raw": "soporte@urbanstyle.com.co",
            "pass_raw": "Urban2026Style",
            "is_online": True,
        },
    ]

    locales_creados = []
    for l_data in locales_data:
        loc = Local.query.filter_by(nombre_marca=l_data["nombre_marca"]).first()
        if not loc:
            loc = Local(
                nombre_marca=l_data["nombre_marca"],
                url_instancia=l_data["url_instancia"],
                fecha_lanzamiento=l_data["fecha_lanzamiento"],
                fecha_inicio_facturacion=date(2026, 11, 15),
                version_software=l_data["version_software"],
                inversion_inicial=l_data["inversion_inicial"],
                mensualidad=l_data["mensualidad"],
                dia_pago=l_data["dia_pago"],
                telefono_cobro="3105551234",
                estado_pago=l_data["estado_pago"],
                boveda_email=encrypt_password(l_data["email_raw"]),
                boveda_password=encrypt_password(l_data["pass_raw"]),
                is_online=l_data["is_online"],
                last_checked=obtener_hora_bogota(),
            )
            db.session.add(loc)
            db.session.commit()
        locales_creados.append(loc)
    print(f"[OK] {len(locales_creados)} Locales creados/verificados.")

    # 3. Facturas
    if Factura.query.count() == 0 and locales_creados:
        facturas_data = [
            {"num": "FAC-2026-001", "local": locales_creados[0], "monto": 450000, "emision": hoy - timedelta(days=25), "vence": hoy - timedelta(days=5), "pago": hoy - timedelta(days=6), "estado": "Pagado", "obs": "Pago vía transferencia Bancolombia"},
            {"num": "FAC-2026-002", "local": locales_creados[1], "monto": 650000, "emision": hoy - timedelta(days=10), "vence": hoy + timedelta(days=2), "pago": None, "estado": "Pendiente", "obs": "Corte de mensualidad correspondiente al mes actual"},
            {"num": "FAC-2026-003", "local": locales_creados[2], "monto": 380000, "emision": hoy - timedelta(days=35), "vence": hoy - timedelta(days=15), "pago": None, "estado": "Vencido", "obs": "Segundo aviso de mora enviado"},
            {"num": "FAC-2026-004", "local": locales_creados[4], "monto": 700000, "emision": hoy - timedelta(days=5), "vence": hoy + timedelta(days=15), "pago": hoy - timedelta(days=2), "estado": "Pagado", "obs": "Pago anticipado recibido"},
            {"num": "FAC-2026-005", "local": locales_creados[5], "monto": 420000, "emision": hoy - timedelta(days=2), "vence": hoy + timedelta(days=18), "pago": None, "estado": "Pendiente", "obs": "Primera mensualidad tras lanzamiento"},
        ]
        for f in facturas_data:
            fac = Factura(
                numero_factura=f["num"],
                local_id=f["local"].id,
                monto=f["monto"],
                fecha_emision=f["emision"],
                fecha_vencimiento=f["vence"],
                fecha_pago=f["pago"],
                estado=f["estado"],
                observaciones=f["obs"]
            )
            db.session.add(fac)
        db.session.commit()
        print("[OK] Facturas de prueba creadas.")

    # 4. Presupuestos por Área
    areas = [
        {"nombre": "Tecnología e Infraestructura", "limite": 6500000.00},
        {"nombre": "Marketing y Publicidad", "limite": 4000000.00},
        {"nombre": "Operaciones", "limite": 3500000.00},
        {"nombre": "Administración", "limite": 2500000.00},
    ]
    presupuestos_map = {}
    for a in areas:
        pres = PresupuestoArea.query.filter_by(nombre_area=a["nombre"], mes=mes_actual, ano=ano_actual).first()
        if not pres:
            pres = PresupuestoArea(
                nombre_area=a["nombre"],
                mes=mes_actual,
                ano=ano_actual,
                limite_gastos=a["limite"]
            )
            db.session.add(pres)
            db.session.commit()
        presupuestos_map[a["nombre"]] = pres
    print("[OK] Presupuestos por área verificados.")

    # 5. Ingresos y Gastos
    if Ingreso.query.count() == 0:
        ingresos_data = [
            {"desc": "Implementación y despliegue CRM Tekfix", "monto": 4500000, "fecha": hoy - timedelta(days=12), "cat": "Implementación"},
            {"desc": "Capacitación de equipo Sarotex", "monto": 1200000, "fecha": hoy - timedelta(days=8), "cat": "Servicios"},
            {"desc": "Desarrollo módulo a la medida para NovaTech", "monto": 3000000, "fecha": hoy - timedelta(days=3), "cat": "Desarrollo"},
            {"desc": "Consultoría de seguridad cloud", "monto": 1800000, "fecha": hoy - timedelta(days=1), "cat": "Consultoría"},
        ]
        for ing in ingresos_data:
            db.session.add(Ingreso(descripcion=ing["desc"], monto=ing["monto"], fecha=ing["fecha"], categoria=ing["cat"]))
        db.session.commit()
        print("[OK] Ingresos ficticios creados.")

    if Gasto.query.count() == 0:
        gastos_data = [
            {"desc": "Servidores AWS y base de datos RDS", "monto": 1450000, "fecha": hoy - timedelta(days=10), "cat": "Servidores", "tipo": "Costo Directo", "area": "Tecnología e Infraestructura"},
            {"desc": "Campañas Meta Ads (Instagram/FB)", "monto": 1200000, "fecha": hoy - timedelta(days=7), "cat": "Publicidad", "tipo": "Costo Indirecto", "area": "Marketing y Publicidad"},
            {"desc": "Suscripción OpenAI API & herramientas IA", "monto": 350000, "fecha": hoy - timedelta(days=5), "cat": "Software", "tipo": "Costo Directo", "area": "Tecnología e Infraestructura"},
            {"desc": "Servicio de internet fibra óptica oficina", "monto": 220000, "fecha": hoy - timedelta(days=4), "cat": "Servicios Básicos", "tipo": "Gasto Administrativo", "area": "Administración"},
            {"desc": "Cafetería y suministros de oficina", "monto": 180000, "fecha": hoy - timedelta(days=2), "cat": "Oficina", "tipo": "Gasto Administrativo", "area": "Operaciones"},
        ]
        for g in gastos_data:
            pres = presupuestos_map.get(g["area"])
            db.session.add(Gasto(
                descripcion=g["desc"],
                monto=g["monto"],
                fecha=g["fecha"],
                categoria=g["cat"],
                tipo_costo=g["tipo"],
                presupuesto_id=pres.id if pres else None
            ))
        db.session.commit()
        print("[OK] Gastos ficticios creados.")

    # 6. Tesorería
    tesoreria = Tesoreria.query.first()
    if not tesoreria:
        tesoreria = Tesoreria(saldo_banco=24500000.00, caja_menor=1850000.00)
        db.session.add(tesoreria)
    else:
        tesoreria.saldo_banco = 24500000.00
        tesoreria.caja_menor = 1850000.00
    db.session.commit()
    print("[OK] Tesorería actualizada ($24.500.000 banco / $1.850.000 caja menor).")

    # 7. Personal (Operaciones)
    personal_data = [
        {"nom": "Carlos Medina", "cargo": "Ingeniero DevOps / Lead TI", "tel": "3124567890", "email": "carlos.ti@zenic.co", "user": users_map.get("ti")},
        {"nom": "Laura Gómez", "cargo": "Directora Creativa & Marketing", "tel": "3159876543", "email": "laura.mkt@zenic.co", "user": users_map.get("marketing")},
        {"nom": "Andrés Ríos", "cargo": "Coordinador de Operaciones", "tel": "3181122334", "email": "andres.ops@zenic.co", "user": users_map.get("operaciones")},
        {"nom": "Mariana Castro", "cargo": "Soporte Técnico Nivel 2", "tel": "3004455667", "email": "mariana.soporte@zenic.co", "user": None},
    ]
    personal_creado = []
    for p in personal_data:
        empl = Personal.query.filter_by(email=p["email"]).first()
        if not empl:
            empl = Personal(
                nombre=p["nom"],
                cargo=p["cargo"],
                telefono=p["tel"],
                email=p["email"],
                estado="Activo",
                fecha_ingreso=hoy - timedelta(days=180),
                user_id=p["user"].id if p["user"] else None
            )
            db.session.add(empl)
            db.session.commit()
        personal_creado.append(empl)
    print(f"[OK] {len(personal_creado)} Empleados verificados.")

    # 8. Activos Fijos (Equipos)
    if ActivoFijo.query.count() == 0 and personal_creado:
        activos_data = [
            {"desc": "MacBook Pro M2 16GB / 512GB", "val": 7200000, "imei": "C02G40XYZM2", "empl": personal_creado[0]},
            {"desc": "Laptop Dell XPS 15 i7 32GB RAM", "val": 6500000, "imei": "DL-XPS15-9921", "empl": personal_creado[1]},
            {"desc": "Monitor Dell UltraSharp 27 pulgadas 4K", "val": 2100000, "imei": "MN-DEL4K-7712", "empl": personal_creado[0]},
            {"desc": "Smartphone Samsung Galaxy S23 (Línea Soporte)", "val": 3200000, "imei": "358941092837192", "empl": personal_creado[3]},
            {"desc": "iPad Pro 11 M2 + Apple Pencil", "val": 4800000, "imei": "AP-IPD11-4821", "empl": personal_creado[1]},
        ]
        for a in activos_data:
            db.session.add(ActivoFijo(
                descripcion=a["desc"],
                valor=a["val"],
                imei=a["imei"],
                personal_id=a["empl"].id,
                fecha_adquisicion=hoy - timedelta(days=90)
            ))
        db.session.commit()
        print("[OK] Activos fijos asignados.")

    # 9. Tickets de TI
    if TicketCambio.query.count() == 0 and locales_creados:
        ti_tickets = [
            {
                "local": locales_creados[0],
                "titulo": "Optimización de consultas en reporte de ventas mensuales",
                "desc": "El cliente reporta que al descargar el PDF consolidado del mes toma más de 15 segundos.",
                "cat": "Error de Sistema",
                "prioridad": "Media",
                "estado": "En Desarrollo",
                "solicitante": users_map["admin"],
                "asignado": users_map.get("ti"),
            },
            {
                "local": locales_creados[1],
                "titulo": "Integración con pasarela de pagos Wompi",
                "desc": "Solicitud para habilitar botón de pago directo por PSE y tarjetas para Sarotex.",
                "cat": "Nueva Función",
                "prioridad": "Alta",
                "estado": "Pendiente",
                "solicitante": users_map["admin"],
                "asignado": users_map.get("ti"),
            },
            {
                "local": locales_creados[4],
                "titulo": "Actualización a versión 1.4.0 completada",
                "desc": "Se desplegó el parche de seguridad y la sincronización en tiempo real de inventarios.",
                "cat": "Despliegue",
                "prioridad": "Urgente",
                "estado": "Resuelto",
                "solicitante": users_map["admin"],
                "asignado": users_map.get("ti"),
            },
            {
                "local": locales_creados[2],
                "titulo": "Revisión de webhook de facturación electrónica DIAN",
                "desc": "Verificar certificado digital y llaves criptográficas antes del fin de mes.",
                "cat": "Soporte",
                "prioridad": "Urgente",
                "estado": "Pendiente",
                "solicitante": users_map["admin"],
                "asignado": None,
            },
        ]
        for t in ti_tickets:
            db.session.add(TicketCambio(
                local_id=t["local"].id,
                titulo=t["titulo"],
                descripcion=t["desc"],
                categoria=t["cat"],
                prioridad=t["prioridad"],
                estado=t["estado"],
                solicitante_id=t["solicitante"].id,
                asignado_id=t["asignado"].id if t["asignado"] else None
            ))
        db.session.commit()
        print("[OK] Tickets de soporte TI creados.")

    # 10. Marketing (Contenidos y Grabaciones)
    if ContenidoMarketing.query.count() == 0:
        contenidos = [
            {
                "titulo": "Reel: 3 razones por las que tu ferretería pierde dinero sin un CRM",
                "red": "Instagram",
                "formato": "Reel",
                "estado": "Listo para Grabar",
                "fecha": hoy + timedelta(days=2),
                "copy": "¿Sigues anotando ventas en cuaderno? Descubre cómo Zenic automatiza tu inventario en tiempo real.",
                "autor": users_map.get("marketing")
            },
            {
                "titulo": "TikTok: Cómo emitir facturas en menos de 10 segundos",
                "red": "TikTok",
                "formato": "TikTok",
                "estado": "Idea",
                "fecha": hoy + timedelta(days=5),
                "copy": "Demostración rápida de la velocidad del punto de venta POS Zenic.",
                "autor": users_map.get("marketing")
            },
            {
                "titulo": "Carrusel LinkedIn: Caso de éxito Tekfix (+35% margen operativo)",
                "red": "LinkedIn",
                "formato": "Carrusel",
                "estado": "Aprobado",
                "fecha": hoy + timedelta(days=1),
                "copy": "Conoce cómo Tekfix centralizó 3 sucursales con nuestra plataforma en la nube.",
                "autor": users_map.get("marketing")
            },
            {
                "titulo": "Historia: Novedades de la actualización v1.4.0",
                "red": "Instagram",
                "formato": "Historia",
                "estado": "Publicado",
                "fecha": hoy - timedelta(days=2),
                "copy": "¡Ya está disponible la nueva versión con modo oscuro y alertas automáticas!",
                "autor": users_map.get("marketing")
            },
        ]
        for c in contenidos:
            db.session.add(ContenidoMarketing(
                titulo=c["titulo"],
                red_social=c["red"],
                formato=c["formato"],
                estado=c["estado"],
                fecha_programada=c["fecha"],
                copy=c["copy"],
                autor_id=c["autor"].id if c["autor"] else None
            ))
        db.session.commit()
        print("[OK] Contenidos de marketing creados.")

    if SesionGrabacion.query.count() == 0:
        db.session.add(SesionGrabacion(
            titulo="Rodaje de testimonios y tomas de apoyo en Tekfix Girardot",
            fecha_grabacion=datetime.now() + timedelta(days=3, hours=10),
            locacion="Local Cliente (Girardot)",
            objetivo="Capturar video del cajero operando el POS y entrevista al administrador.",
            participantes="Laura Gómez, Carlos Medina, Gerente Tekfix",
            equipos_requeridos="Cámara Sony FX3, Lente 24-70mm, Micrófono inalámbrico Rode, Kit de luces LED",
            estado="Programada"
        ))
        db.session.commit()
        print("[OK] Sesión de grabación agendada.")

    # 11. Notificaciones
    if Notificacion.query.count() == 0 and locales_creados:
        db.session.add(Notificacion(
            user_id=master_admin.id,
            titulo="Mantenimiento preventivo programado",
            mensaje="Este domingo entre las 02:00 y las 04:00 AM realizaremos actualización de infraestructura sin afectación a datos.",
            tipo="info",
            destinos="Todos los locales activos",
            resultados='{"status": "delivered", "count": 5}',
        ))
        db.session.add(Notificacion(
            user_id=master_admin.id,
            titulo="Aviso de facturación mensual",
            mensaje="Se han generado las facturas correspondientes al ciclo actual. Por favor verificar soportes.",
            tipo="warning",
            destinos="Locales por vencer",
            resultados='{"status": "delivered", "count": 2}',
        ))
        db.session.commit()
        print("[OK] Notificaciones de auditoría creadas.")

    # 12. Gestión Documental & Manuales
    if Documento.query.count() == 0 and locales_creados:
        upload_dir = app.config.get("UPLOAD_FOLDER")
        os.makedirs(upload_dir, exist_ok=True)
        docs_demo = [
            {
                "titulo": "Arquitectura Cloud & Especificación de Infraestructura Zenic",
                "desc": "Diagrama de topología AWS RDS, EC2, políticas de seguridad y bóveda criptográfica.",
                "tipo": "zenic",
                "cat": "Arquitectura e Infraestructura",
                "ver": "2.1",
                "local": None,
                "filename": "arquitectura_zenic_v2.pdf",
                "content": b"%PDF-1.4 Zenic Cloud Architecture Specs"
            },
            {
                "titulo": "Política de Seguridad, Bóveda Fernet y Gestión de Accesos",
                "desc": "Directrices para custodia de contraseñas de instancias clientes y rotación de llaves.",
                "tipo": "zenic",
                "cat": "Políticas Corporativas",
                "ver": "1.0",
                "local": None,
                "filename": "politica_seguridad_zenic.pdf",
                "content": b"%PDF-1.4 Zenic Security Policy"
            },
            {
                "titulo": "RUT Actualizado 2026 — Tekfix Girardot",
                "desc": "Registro Único Tributario con actividad económica y responsabilidad de IVA.",
                "tipo": "cliente",
                "cat": "RUT y Tributario",
                "ver": "2026",
                "local": locales_creados[0],
                "filename": "rut_tekfix_2026.pdf",
                "content": b"%PDF-1.4 RUT Tekfix Girardot"
            },
            {
                "titulo": "Cámara de Comercio Vigente — Tekfix Girardot",
                "desc": "Certificado de existencia y representación legal con vigencia menor a 30 días.",
                "tipo": "cliente",
                "cat": "Cámara de Comercio",
                "ver": "2026",
                "local": locales_creados[0],
                "filename": "camara_comercio_tekfix.pdf",
                "content": b"%PDF-1.4 Camara Comercio Tekfix"
            },
            {
                "titulo": "Contrato de Licenciamiento de Software y SLA — Sarotex Medellín",
                "desc": "Contrato firmado digitalmente con cláusulas de soporte, disponibilidad y mensualidad.",
                "tipo": "cliente",
                "cat": "Contrato de Servicios",
                "ver": "1.0",
                "local": locales_creados[1],
                "filename": "contrato_sarotex_zenic.pdf",
                "content": b"%PDF-1.4 Contrato Sarotex Zenic"
            },
            {
                "titulo": "Manual de Usuario: Módulo POS y Punto de Venta",
                "desc": "Guía paso a paso para cajeros: apertura de caja, facturación rápida, devoluciones y cierre.",
                "tipo": "manual",
                "cat": "Manual de Usuario POS",
                "ver": "1.4",
                "local": None,
                "filename": "manual_usuario_pos_zenic.pdf",
                "content": b"%PDF-1.4 Manual POS Zenic"
            },
            {
                "titulo": "Guía de Facturación Electrónica DIAN y Resolución de Contingencias",
                "desc": "Manual técnico para emisión de XML, firma digital y manejo de errores de validación previa.",
                "tipo": "manual",
                "cat": "Facturación Electrónica DIAN",
                "ver": "1.2",
                "local": None,
                "filename": "guia_facturacion_electronica_dian.pdf",
                "content": b"%PDF-1.4 Guia Facturacion DIAN"
            },
            {
                "titulo": "Manual de Despliegue de Instancia CRM y Uptime Monitor",
                "desc": "Procedimiento para aprovisionar un nuevo local en subdominio y enlazar webhook.",
                "tipo": "manual",
                "cat": "Técnico / Infraestructura",
                "ver": "1.0",
                "local": None,
                "filename": "manual_despliegue_instancias.pdf",
                "content": b"%PDF-1.4 Manual Despliegue Zenic"
            }
        ]
        for item in docs_demo:
            f_path = os.path.join(upload_dir, item["filename"])
            if not os.path.exists(f_path):
                with open(f_path, "wb") as f:
                    f.write(item["content"])
            db.session.add(Documento(
                titulo=item["titulo"],
                descripcion=item["desc"],
                tipo=item["tipo"],
                categoria=item["cat"],
                version=item["ver"],
                local_id=item["local"].id if item["local"] else None,
                archivo_ruta=item["filename"],
                archivo_nombre_original=item["filename"],
                archivo_tamano=len(item["content"]),
                archivo_extension="pdf",
                autor_id=master_admin.id
            ))
        db.session.commit()
        print("[OK] Documentación corporativa, legal de clientes y manuales inicializados.")

    print("\n===========================================================")
    print("DATOS FICTICIOS INYECTADOS EXITOSAMENTE.")
    print("Ya puedes explorar el panel con información completa.")
    print("===========================================================")
