"""
seed_bloques.py — Inyección y validación de datos para Bloque 1 (Facturación/Cuentas) y Bloque 2 (Métricas Redes)
"""
from datetime import date, datetime, timedelta
from app import create_app
from models import (
    db, User, Local, Factura, Gasto, CorteMetricaSocial, obtener_hora_bogota
)
from werkzeug.security import generate_password_hash
from crypto_utils import encrypt_password

app = create_app()

with app.app_context():
    print("Iniciando inyeccion de datos de Bloque 1 y Bloque 2...")
    hoy = obtener_hora_bogota().date()
    fecha_corte_caja = date(2026, 11, 15)

    # 1. Usuarios clave
    usuarios = [
        {"nombre": "Jhon Validador (Finanzas)", "email": "jhon@zenic.co", "rol": "admin", "pass": "Zenic2026!"},
        {"nombre": "Santiago Marketing", "email": "santiago.mkt@zenic.co", "rol": "marketing", "pass": "Zenic2026!"},
        {"nombre": "Marlon Ramirez", "email": "marlon@zenic.co", "rol": "admin", "pass": "Zenic2026!"},
        {"nombre": "Miguel Angel", "email": "miguel@zenic.co", "rol": "admin", "pass": "Zenic2026!"}
    ]
    u_map = {}
    for u in usuarios:
        user = User.query.filter_by(email=u["email"]).first()
        if not user:
            user = User(
                nombre=u["nombre"],
                email=u["email"],
                password_hash=generate_password_hash(u["pass"]),
                rol=u["rol"]
            )
            db.session.add(user)
            db.session.commit()
        u_map[u["email"]] = user
    print("[OK] Usuarios verificados.")

    # 2. Locales especiales
    # A) Instancia Interna (sistema.zenic.com.co) -> Excluida de MRR y semáforo
    zenic_interno = Local.query.filter_by(url_instancia="https://sistema.zenic.com.co").first()
    if not zenic_interno:
        zenic_interno = Local(
            nombre_marca="Zenic Instancia Interna (Operativo)",
            url_instancia="https://sistema.zenic.com.co",
            fecha_lanzamiento=date(2026, 10, 1),
            version_software="2.0.0",
            inversion_inicial=0,
            mensualidad=0,
            valor_anualidad=0,
            tipo_plan="Interna",
            dia_pago=1,
            telefono_cobro="3000000000",
            estado_pago="Activo",
            boveda_email=encrypt_password("admin@zenic.com.co"),
            boveda_password=encrypt_password("ZenicInternal2026!"),
            is_online=True
        )
        db.session.add(zenic_interno)
        db.session.commit()
    print("[OK] Instancia interna de Zenic verificada.")

    # B) Cliente Plan Anual (Redcover)
    redcover = Local.query.filter_by(nombre_marca="Redcover").first()
    if not redcover:
        redcover = Local(
            nombre_marca="Redcover",
            url_instancia="https://redcover.zenic.cloud",
            fecha_lanzamiento=date(2026, 10, 10),
            fecha_inicio_facturacion=date(2027, 10, 10),
            version_software="1.4.2",
            inversion_inicial=12000000.0,
            mensualidad=541666.67,
            valor_anualidad=6500000.0,
            tipo_plan="Anual",
            dia_pago=10,
            telefono_cobro="3158889900",
            estado_pago="Activo",
            boveda_email=encrypt_password("contacto@redcover.co"),
            boveda_password=encrypt_password("RedCoverSecure!"),
            is_online=True
        )
        db.session.add(redcover)
        db.session.commit()
    print("[OK] Cliente Redcover (Plan Anual) verificado.")

    # C) Cliente Nuevo post 15/11/2026 (ej. Lanzado hoy) con cobro de instalación
    nuevo_cliente = Local.query.filter_by(nombre_marca="BurgerHouse Gourmet").first()
    if not nuevo_cliente:
        nuevo_cliente = Local(
            nombre_marca="BurgerHouse Gourmet",
            url_instancia="https://burgerhouse.zenic.cloud",
            fecha_lanzamiento=fecha_corte_caja + timedelta(days=1), # 16/11/2026
            fecha_inicio_facturacion=date(2026, 12, 16),
            version_software="1.4.0",
            inversion_inicial=4500000.0,
            mensualidad=480000.0,
            tipo_plan="Mensual",
            dia_pago=16,
            telefono_cobro="3207771234",
            estado_pago="Activo",
            boveda_email=encrypt_password("admin@burgerhouse.co"),
            boveda_password=encrypt_password("Burger2026!"),
            is_online=True
        )
        db.session.add(nuevo_cliente)
        db.session.commit()

        # Generar factura de instalación pendiente post 15/11/2026
        fact_inst = Factura(
            numero_factura="INST-2611-0001",
            local_id=nuevo_cliente.id,
            monto=4500000.0,
            tipo_cobro="Instalación",
            fecha_emision=fecha_corte_caja + timedelta(days=1),
            fecha_vencimiento=fecha_corte_caja + timedelta(days=6),
            estado="Pendiente",
            observaciones="Inversión inicial / Instalación física y despliegue en la nube (cubre 1er mes)"
        )
        db.session.add(fact_inst)
        db.session.commit()
    print("[OK] Cliente post-corte con instalación automática verificado.")

    # 3. Facturas validadas en Nu y Nequi (>= 15/11/2026)
    sarotex = Local.query.filter_by(nombre_marca="Sarotex Medellín").first()
    tekfix = Local.query.filter_by(nombre_marca="Tekfix Girardot").first()

    if sarotex:
        # Factura validada en Nu
        f_nu = Factura.query.filter_by(numero_factura="INV-2611-0002").first()
        if not f_nu:
            f_nu = Factura(
                numero_factura="INV-2611-0002",
                local_id=sarotex.id,
                monto=650000.0,
                tipo_cobro="Mensualidad",
                fecha_emision=fecha_corte_caja,
                fecha_vencimiento=fecha_corte_caja + timedelta(days=5),
                fecha_pago=fecha_corte_caja + timedelta(days=1),
                estado="Pagado",
                cuenta_destino="Nu",
                validado_por_id=u_map["jhon@zenic.co"].id,
                observaciones="Mensualidad validada por Jhon en Nu Bank."
            )
            db.session.add(f_nu)

    if tekfix:
        # Factura validada en Nequi
        f_nequi = Factura.query.filter_by(numero_factura="INV-2611-0003").first()
        if not f_nequi:
            f_nequi = Factura(
                numero_factura="INV-2611-0003",
                local_id=tekfix.id,
                monto=450000.0,
                tipo_cobro="Mensualidad",
                fecha_emision=fecha_corte_caja,
                fecha_vencimiento=fecha_corte_caja + timedelta(days=5),
                fecha_pago=fecha_corte_caja + timedelta(days=2),
                estado="Pagado",
                cuenta_destino="Nequi",
                validado_por_id=u_map["jhon@zenic.co"].id,
                observaciones="Mensualidad validada por Jhon en Nequi."
            )
            db.session.add(f_nequi)

    # Factura vencida con recordatorio para probar trazabilidad
    fast = Local.query.filter_by(nombre_marca="ElectroFast Cali").first()
    if fast:
        f_mora = Factura.query.filter_by(numero_factura="INV-2611-0004").first()
        if not f_mora:
            f_mora = Factura(
                numero_factura="INV-2611-0004",
                local_id=fast.id,
                monto=380000.0,
                tipo_cobro="Mensualidad",
                fecha_emision=fecha_corte_caja - timedelta(days=10),
                fecha_vencimiento=fecha_corte_caja + timedelta(days=1),
                estado="Vencido",
                ultimo_recordatorio=datetime.now() - timedelta(hours=3),
                recordatorio_enviado_por_id=u_map["jhon@zenic.co"].id,
                total_recordatorios=1,
                observaciones="Mensualidad en mora con recordatorio preventivo enviado."
            )
            db.session.add(f_mora)

    # 4. Gastos descontados de Nu y Nequi (>= 15/11/2026)
    gasto_nu = Gasto.query.filter_by(descripcion="Licencia Servidores Cloud AWS").first()
    if not gasto_nu:
        gasto_nu = Gasto(
            descripcion="Licencia Servidores Cloud AWS",
            monto=180000.0,
            fecha=fecha_corte_caja + timedelta(days=1),
            categoria="Tecnología",
            tipo_costo="Costo Directo",
            cuenta_origen="Nu"
        )
        db.session.add(gasto_nu)

    gasto_nequi = Gasto.query.filter_by(descripcion="Insumos de Oficina y Envíos").first()
    if not gasto_nequi:
        gasto_nequi = Gasto(
            descripcion="Insumos de Oficina y Envíos",
            monto=95000.0,
            fecha=fecha_corte_caja + timedelta(days=2),
            categoria="Operativo",
            tipo_costo="Gasto Administrativo",
            cuenta_origen="Nequi"
        )
        db.session.add(gasto_nequi)

    db.session.commit()
    print("[OK] Facturación, Billeteras Nu/Nequi y Gastos vinculados.")

    # 5. Bloque 2: Métricas de Crecimiento & Redes Sociales (Cortes periódicos para Santiago)
    if CorteMetricaSocial.query.count() == 0:
        cortes_instagram = [
            {
                "red_social": "Instagram",
                "periodo_tipo": "Semanal",
                "etiqueta_periodo": "Semana 43 - Lanzamiento #LaOtraCaraDelMostrador",
                "fecha_corte": date(2026, 10, 26),
                "seguidores_totales": 12450,
                "visualizaciones": 28500,
                "alcance": 32400,
                "interacciones": 2250,
                "link_top_post": "https://www.instagram.com/reel/DBa123Demo/",
                "leads_generados": 14,
                "notas_campana": "Inicio de la campaña mostrando el detrás de escena de los restaurantes clientes."
            },
            {
                "red_social": "Instagram",
                "periodo_tipo": "Semanal",
                "etiqueta_periodo": "Semana 44 - Caso Éxito Sarotex",
                "fecha_corte": date(2026, 11, 2),
                "seguidores_totales": 13200,
                "visualizaciones": 38900,
                "alcance": 41200,
                "interacciones": 3150,
                "link_top_post": "https://www.instagram.com/reel/DBb456Demo/",
                "leads_generados": 22,
                "notas_campana": "Reel testimonial con el administrador de Sarotex hablando de reducción de pérdidas."
            },
            {
                "red_social": "Instagram",
                "periodo_tipo": "Semanal",
                "etiqueta_periodo": "Semana 45 - Viral Mostrador #2",
                "fecha_corte": date(2026, 11, 9),
                "seguidores_totales": 14600,
                "visualizaciones": 54200,
                "alcance": 58300,
                "interacciones": 4820,
                "link_top_post": "https://www.instagram.com/reel/DBc789Demo/",
                "leads_generados": 35,
                "notas_campana": "Contenido humorístico / dolor real del mesero cerrando caja en Excel."
            },
            {
                "red_social": "Instagram",
                "periodo_tipo": "Semanal",
                "etiqueta_periodo": "Semana 46 - Cierre Quincenal Noviembre",
                "fecha_corte": date(2026, 11, 16),
                "seguidores_totales": 16180,
                "visualizaciones": 69400,
                "alcance": 72500,
                "interacciones": 6410,
                "link_top_post": "https://www.instagram.com/reel/DBd012Demo/",
                "leads_generados": 48,
                "notas_campana": "Carrusel técnico de arquitectura y 3 reels con alta retención en los primeros 3 segundos."
            }
        ]

        cortes_tiktok = [
            {
                "red_social": "TikTok",
                "periodo_tipo": "Semanal",
                "etiqueta_periodo": "Semana 45 - TikTok Humor POS",
                "fecha_corte": date(2026, 11, 9),
                "seguidores_totales": 4800,
                "visualizaciones": 45000,
                "alcance": 39000,
                "interacciones": 3400,
                "link_top_post": "https://www.tiktok.com/@zenic.app/video/730000001",
                "leads_generados": 8,
                "notas_campana": "Formato rápido y audio viral en tendencia."
            },
            {
                "red_social": "TikTok",
                "periodo_tipo": "Semanal",
                "etiqueta_periodo": "Semana 46 - TikTok #LaOtraCaraDelMostrador",
                "fecha_corte": date(2026, 11, 16),
                "seguidores_totales": 6250,
                "visualizaciones": 82000,
                "alcance": 68000,
                "interacciones": 6100,
                "link_top_post": "https://www.tiktok.com/@zenic.app/video/730000002",
                "leads_generados": 19,
                "notas_campana": "Hook potente con audio en tendencia sobre el inventario a medianoche."
            }
        ]

        santiago = u_map["santiago.mkt@zenic.co"]
        for c in cortes_instagram + cortes_tiktok:
            db.session.add(CorteMetricaSocial(
                red_social=c["red_social"],
                periodo_tipo=c["periodo_tipo"],
                etiqueta_periodo=c["etiqueta_periodo"],
                fecha_corte=c["fecha_corte"],
                seguidores_totales=c["seguidores_totales"],
                visualizaciones=c["visualizaciones"],
                alcance=c["alcance"],
                interacciones=c["interacciones"],
                link_top_post=c["link_top_post"],
                leads_generados=c["leads_generados"],
                notas_campana=c["notas_campana"],
                autor_id=santiago.id
            ))
        db.session.commit()
        print("[OK] Cortes periódicos de Instagram y TikTok insertados.")

    print("\n===========================================================")
    print("TODOS LOS DATOS DE BLOQUE 1 Y BLOQUE 2 QUEDARON LISTOS.")
    print("===========================================================")
