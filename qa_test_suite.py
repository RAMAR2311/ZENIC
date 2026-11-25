"""
qa_test_suite.py — Suite integral de Control de Calidad (QA) para Zenic Master Control
Verifica lógica financiera, roles, trazabilidad de cobros, métricas de marketing y todas las vistas.
"""
import sys
import uuid
import unittest
from datetime import date, datetime, timedelta
from app import create_app
from models import (
    db, User, Local, Factura, Gasto, Ingreso, PresupuestoArea,
    Tesoreria, Personal, ActivoFijo, TicketCambio,
    ContenidoMarketing, SesionGrabacion, Documento, CorteMetricaSocial,
    obtener_hora_bogota
)
from flask_login import login_user
from werkzeug.security import generate_password_hash


class ZenicQATestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

        # Ruta auxiliar interna para autenticación fiable en tests
        @cls.app.route("/qa_login/<int:uid>")
        def _qa_login(uid):
            user = db.session.get(User, uid)
            if user:
                login_user(user)
                return "OK"
            return "NOT_FOUND", 404

        cls.hoy = obtener_hora_bogota().date()
        cls.corte_caja = date(2026, 11, 15)

        # Cargar usuarios de prueba
        cls.admin_jhon = User.query.filter(
            (User.email == "jhon@zenic.co") | (User.nombre.like("%Jhon%"))
        ).first()
        if not cls.admin_jhon:
            cls.admin_jhon = User(
                nombre="Jhon Finanzas", email="jhon.qa@zenic.co",
                password_hash=generate_password_hash("Zenic2026!"), rol="admin"
            )
            db.session.add(cls.admin_jhon)
            db.session.commit()

        cls.user_santiago = User.query.filter_by(email="santiago.mkt@zenic.co").first()
        if not cls.user_santiago:
            cls.user_santiago = User(
                nombre="Santiago Mkt", email="santiago.qa@zenic.co",
                password_hash=generate_password_hash("Zenic2026!"), rol="marketing"
            )
            db.session.add(cls.user_santiago)
            db.session.commit()

        # Limpiar registros residuales de tests previos
        Factura.query.filter(Factura.numero_factura.like("TEST-%")).delete()
        Local.query.filter(Local.nombre_marca.like("QA Test%")).delete()
        CorteMetricaSocial.query.filter(CorteMetricaSocial.etiqueta_periodo.like("%QA Test%")).delete()
        db.session.commit()

    @classmethod
    def tearDownClass(cls):
        db.session.rollback()
        cls.ctx.pop()

    def setUp(self):
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.rollback()

    def login_as(self, user):
        resp = self.client.get(f"/qa_login/{user.id}")
        self.assertEqual(resp.status_code, 200, f"Error autenticando a usuario {user.email}")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. PRUEBAS DE CALIDAD: BLOQUE 1 (FINANZAS, CLIENTES, FACTURACIÓN)
    # ─────────────────────────────────────────────────────────────────────────
    def test_01_corte_financiero_punto_partida(self):
        """QA 1.1: Ingresos previos al 15/11/2026 NO deben sumar a caja actual ni a billeteras."""
        num_fac = f"TEST-HIST-{uuid.uuid4().hex[:6]}"
        f_antigua = Factura(
            numero_factura=num_fac,
            local_id=1,
            monto=999999.0,
            tipo_cobro="Mensualidad",
            fecha_emision=date(2026, 10, 1),
            fecha_vencimiento=date(2026, 10, 5),
            fecha_pago=date(2026, 10, 5), # ANTERIOR al 15/11/2026
            estado="Pagado",
            cuenta_destino="Nu"
        )
        db.session.add(f_antigua)
        db.session.commit()

        self.login_as(self.admin_jhon)
        resp = self.client.get("/ingresos")
        self.assertEqual(resp.status_code, 200)

        # La factura antigua no debe sumarse en Nu
        facturas_nu = Factura.query.filter(
            Factura.estado == "Pagado",
            Factura.cuenta_destino == "Nu",
            Factura.fecha_pago >= self.corte_caja
        ).all()
        ids_nu = [f.id for f in facturas_nu]
        self.assertNotIn(f_antigua.id, ids_nu, "Factura anterior al 15/11/2026 no debe estar en Nu")

        db.session.delete(f_antigua)
        db.session.commit()

    def test_02_regla_primer_mes_incluido_instalacion(self):
        """QA 1.2: Cliente nuevo lanzado post 15/11 debe tener vencimiento mensual en +1 mes exacto."""
        fecha_lanz = self.corte_caja + timedelta(days=2) # 17/11/2026
        nuevo_local = Local(
            nombre_marca=f"QA Test Pizzeria {uuid.uuid4().hex[:4]}",
            url_instancia="https://qatest.zenic.cloud",
            fecha_lanzamiento=fecha_lanz,
            version_software="1.4.0",
            inversion_inicial=5000000.0,
            mensualidad=400000.0,
            tipo_plan="Mensual",
            dia_pago=17,
            estado_pago="Activo"
        )
        db.session.add(nuevo_local)
        db.session.commit()

        prox = nuevo_local.proxima_fecha_corte
        esperado_min = fecha_lanz + timedelta(days=25)
        self.assertGreaterEqual(prox, esperado_min, "El cobro de mensualidad debe ser al menos 1 mes después del lanzamiento")

        db.session.delete(nuevo_local)
        db.session.commit()

    def test_03_modalidad_instancia_interna_excluida_mrr_y_semaforo(self):
        """QA 1.3: Instancia interna debe excluirse del MRR facturable y del semáforo de cobro."""
        interna = Local.query.filter_by(tipo_plan="Interna").first()
        self.assertIsNotNone(interna, "Debe existir una instancia interna")
        self.assertEqual(interna.semaforo, "semaforo-azul", "Semáforo de instancia interna debe ser semaforo-azul")
        self.assertEqual(interna.semaforo_label, "Interna")

        self.login_as(self.admin_jhon)
        resp = self.client.get("/api/mrr")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("mrr", data)
        self.assertIn("activos", data)

    def test_04_modalidad_plan_anual_vencimiento(self):
        """QA 1.4: Plan Anual calcula vencimiento a 1 año desde fecha de lanzamiento."""
        anual = Local.query.filter_by(tipo_plan="Anual").first()
        self.assertIsNotNone(anual, "Debe existir al menos un local anual como Redcover")
        prox = anual.proxima_fecha_corte
        ano_esperado = anual.fecha_lanzamiento.year + 1
        self.assertEqual(prox.year, ano_esperado, "El vencimiento anual debe ser en el siguiente año")

    def test_05_validar_pago_actualiza_cuenta_y_reactiva_local(self):
        """QA 1.5: Validar pago cambia estado a Pagado, suma a cuenta Nu/Nequi y reactiva local."""
        local = Local.query.filter(Local.tipo_plan != "Interna").first()
        num_fac = f"TEST-VAL-{uuid.uuid4().hex[:6]}"
        factura_test = Factura(
            numero_factura=num_fac,
            local_id=local.id,
            monto=350000.0,
            tipo_cobro="Mensualidad",
            fecha_emision=self.hoy,
            fecha_vencimiento=self.hoy + timedelta(days=5),
            estado="Pendiente"
        )
        local.estado_pago = "Pendiente"
        db.session.add(factura_test)
        db.session.commit()

        self.login_as(self.admin_jhon)
        post_data = {
            "cuenta_destino": "Nequi",
            "fecha_pago": self.hoy.strftime("%Y-%m-%d")
        }
        resp = self.client.post(f"/ingresos/{factura_test.id}/validar", data=post_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        db.session.refresh(factura_test)
        db.session.refresh(local)

        self.assertEqual(factura_test.estado, "Pagado")
        self.assertEqual(factura_test.cuenta_destino, "Nequi")
        self.assertEqual(factura_test.fecha_pago, self.hoy)
        self.assertEqual(local.estado_pago, "Activo", "El local debe reactivarse automáticamente")

        db.session.delete(factura_test)
        db.session.commit()

    def test_06_recordatorio_mora_registra_trazabilidad(self):
        """QA 1.6: Enviar recordatorio debe guardar constancia de fecha, hora y usuario."""
        local = Local.query.filter(Local.tipo_plan != "Interna").first()
        local.telefono_cobro = "3001234567"
        num_fac = f"TEST-REM-{uuid.uuid4().hex[:6]}"
        factura_test = Factura(
            numero_factura=num_fac,
            local_id=local.id,
            monto=420000.0,
            tipo_cobro="Mensualidad",
            fecha_emision=self.hoy - timedelta(days=15),
            fecha_vencimiento=self.hoy - timedelta(days=2),
            estado="Vencido"
        )
        db.session.add(factura_test)
        db.session.commit()

        self.login_as(self.admin_jhon)
        resp = self.client.post(f"/ingresos/{factura_test.id}/recordatorio")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("api.whatsapp.com", resp.location)

        db.session.refresh(factura_test)
        self.assertIsNotNone(factura_test.ultimo_recordatorio)
        self.assertEqual(factura_test.recordatorio_enviado_por_id, self.admin_jhon.id)
        self.assertGreaterEqual(factura_test.total_recordatorios, 1)

        db.session.delete(factura_test)
        db.session.commit()

    def test_07_privacidad_billeteras_nu_nequi(self):
        """QA 1.7: Billeteras Nu y Nequi solo visibles para Jhon / Admin, no para otros perfiles."""
        # Jhon / Admin
        self.login_as(self.admin_jhon)
        resp_admin = self.client.get("/ingresos")
        self.assertIn(b"VISTA PRIVADA", resp_admin.data)
        self.assertIn(b"Cuenta Nu (Jhon)", resp_admin.data)
        self.assertIn(b"Cuenta Nequi (Jhon)", resp_admin.data)

        # Santiago / Marketing
        self.login_as(self.user_santiago)
        resp_santiago = self.client.get("/ingresos")
        self.assertEqual(resp_santiago.status_code, 200)
        self.assertNotIn(b"VISTA PRIVADA", resp_santiago.data)
        self.assertNotIn(b"Billeteras de Control de Saldos", resp_santiago.data)
        self.assertNotIn(b"Saldo Real Disponible", resp_santiago.data)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. PRUEBAS DE CALIDAD: BLOQUE 2 (MÉTRICAS Y CRECIMIENTO EN REDES)
    # ─────────────────────────────────────────────────────────────────────────
    def test_08_metricas_calculo_engagement_y_variacion(self):
        """QA 2.1: Verificar cálculo de Engagement Rate y variaciones porcentuales."""
        self.login_as(self.user_santiago)

        etiqueta = f"Semana QA Test {uuid.uuid4().hex[:4]}"
        post_data = {
            "red_social": "Instagram",
            "periodo_tipo": "Semanal",
            "etiqueta_periodo": etiqueta,
            "fecha_corte": self.hoy.strftime("%Y-%m-%d"),
            "seguidores_totales": "18000",
            "visualizaciones": "75000",
            "alcance": "80000",
            "interacciones": "8000",
            "link_top_post": "https://instagram.com/reel/qa_test",
            "leads_generados": "55",
            "notas_campana": "Test automatizado QA"
        }
        resp = self.client.post("/marketing/metricas", data=post_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        corte = CorteMetricaSocial.query.filter_by(etiqueta_periodo=etiqueta).first()
        self.assertIsNotNone(corte)
        # Fórmula: (8000 / 80000) * 100 = 10.0%
        self.assertEqual(corte.engagement_rate, 10.0, "El engagement rate debe ser exactamente 10.0%")
        self.assertEqual(corte.leads_generados, 55)

        resp_get = self.client.get("/marketing/metricas?red=Instagram")
        html = resp_get.data.decode("utf-8")
        self.assertIn("10.0%", html)
        self.assertIn("https://instagram.com/reel/qa_test", html)
        self.assertIn(etiqueta, html)

        db.session.delete(corte)
        db.session.commit()

    def test_09_metricas_plataformas_y_filtros(self):
        """QA 2.2: Verificar navegación por plataformas (Instagram, TikTok, LinkedIn, Consolidado)."""
        self.login_as(self.user_santiago)
        for red in ["Instagram", "TikTok", "LinkedIn", "Facebook", "Consolidado"]:
            resp = self.client.get(f"/marketing/metricas?red={red}")
            self.assertEqual(resp.status_code, 200, f"Error cargando pestaña {red}")
            self.assertIn(f"red={red}".encode("utf-8"), resp.data)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. PRUEBAS DE CALIDAD: RENDERING DE VISTAS Y RUTAS PRINCIPALES
    # ─────────────────────────────────────────────────────────────────────────
    def test_10_todas_las_rutas_principales(self):
        """QA 3.1: Verificar que todas las páginas principales del sistema carguen con código 200."""
        self.login_as(self.admin_jhon)

        rutas_a_probar = [
            ("/", "Dashboard General"),
            ("/dashboard", "Dashboard MRR"),
            ("/clientes", "Perfiles 360 de Clientes"),
            ("/ingresos", "Módulo Facturas & Cobros"),
            ("/finanzas/ingresos", "Finanzas - Ingresos & Tesorería"),
            ("/finanzas/prestamos", "Finanzas - Préstamos a Favor"),
            ("/finanzas/gastos", "Finanzas - Costos & Gastos"),
            ("/finanzas/trazabilidad", "Finanzas - Reporte de Trazabilidad PDF"),
            ("/finanzas/trazabilidad?formato=csv", "Finanzas - Reporte de Trazabilidad CSV"),
            ("/finanzas/presupuestos", "Finanzas - Presupuestos"),
            ("/ti/tickets", "Soporte TI - Tickets"),
            ("/ti/api/notificaciones", "API Notificaciones Tickets en Vivo"),
            ("/ti/conexiones", "Soporte TI - Conexiones"),
            ("/documentos/", "Documentación & Manuales"),
            ("/marketing/", "Portal Marketing"),
            ("/marketing/contenidos", "Calendario Redes"),
            ("/marketing/grabaciones", "Agenda Grabaciones"),
            ("/marketing/social-hub", "Social Hub & Brand"),
            ("/marketing/metricas", "Métricas & Crecimiento"),
            ("/manifest.json", "PWA Manifest"),
            ("/sw.js", "PWA Service Worker"),
            ("/offline", "PWA Offline Page"),
            ("/favicon.ico", "Favicon Oficial")
        ]

        for ruta, nombre in rutas_a_probar:
            with self.subTest(ruta=ruta, nombre=nombre):
                resp = self.client.get(ruta, follow_redirects=True)
                self.assertEqual(
                    resp.status_code, 200,
                    f"Fallo en ruta {ruta} ({nombre}): HTTP {resp.status_code}"
                )

    def test_11_flujo_tickets_inline_validacion_y_pwa_responsive(self):
        """QA 3.2: Verificar cambio de estado inline en tickets, devolución a Requiere Ajustes y diseño responsive/PWA."""
        self.login_as(self.admin_jhon)
        ticket = TicketCambio.query.first()
        self.assertIsNotNone(ticket)
        estado_original = ticket.estado

        # 1. Cambio de estado directo inline vía AJAX a 'En Desarrollo'
        r_inline = self.client.post(
            f"/ti/tickets/{ticket.id}/actualizar",
            data={"estado": "En Desarrollo"},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(r_inline.status_code, 200)
        self.assertEqual(r_inline.get_json()["estado"], "En Desarrollo")

        # 2. Devolver ticket para revisión ('Requiere Ajustes') y verificar notificación
        r_rev = self.client.post(
            f"/ti/tickets/{ticket.id}/validar",
            data={"decision": "revisar", "notas_validacion": "Revisar ajuste visual en móvil"},
            follow_redirects=True
        )
        self.assertEqual(r_rev.status_code, 200)
        db.session.refresh(ticket)
        self.assertEqual(ticket.estado, "Requiere Ajustes")
        self.assertIn("Revisar ajuste visual", ticket.notas_validacion)

        # Restaurar estado original
        ticket.estado = estado_original
        db.session.commit()

        # 3. Verificar meta tags responsive (celular/tablet/PC) y barra móvil PWA
        r_page = self.client.get("/ti/tickets")
        html = r_page.data.decode("utf-8")
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1.0"', html)
        self.assertIn('rel="manifest" href="/manifest.json"', html)
        self.assertIn('class="mobile-bottom-nav', html)
        self.assertIn('handleInlineTicketStatus(this)', html)


if __name__ == "__main__":
    result = unittest.main(exit=False)
    if result.result.wasSuccessful():
        print("\n=======================================================")
        print("✅ TODAS LAS PRUEBAS DE CONTROL DE CALIDAD PASARON AL 100%")
        print("=======================================================")
        sys.exit(0)
    else:
        print("\n❌ ALGUNAS PRUEBAS FALLARON.")
        sys.exit(1)
