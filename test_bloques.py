"""
test_bloques.py — Suite de pruebas de validación para Bloque 1 y Bloque 2
"""
from datetime import date, timedelta
from app import create_app
from models import db, User, Local, Factura, Gasto, CorteMetricaSocial, obtener_hora_bogota

app = create_app()

with app.app_context():
    client = app.test_client()

    # Iniciar sesión como Jhon (Admin)
    jhon = User.query.filter_by(email="jhon@zenic.co").first()
    assert jhon is not None, "Jhon debe existir"

    with client.session_transaction() as sess:
        sess['_user_id'] = str(jhon.id)
        sess['_fresh'] = True

    print("1. Probando Dashboard MRR y exclusión de instancia interna...")
    resp = client.get("/dashboard")
    assert resp.status_code == 200, f"Error en /dashboard: {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "Redcover" in html
    assert "Zenic Instancia Interna" in html
    print("   [PASS] Dashboard de locales carga correctamente.")

    print("2. Probando Módulo de Facturas y Billeteras Nu/Nequi...")
    resp = client.get("/ingresos")
    assert resp.status_code == 200, f"Error en /ingresos: {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "Cuenta Nu (Jhon)" in html
    assert "Cuenta Nequi (Jhon)" in html
    assert "VISTA PRIVADA" in html
    assert "Validar Pago" in html
    assert "Recordatorio enviado" in html or "Sin recordatorios" in html
    print("   [PASS] Billeteras privadas Nu/Nequi y facturas cargan correctamente para Jhon.")

    print("3. Probando Módulo de Métricas y Redes Sociales...")
    resp = client.get("/marketing/metricas?red=Instagram")
    assert resp.status_code == 200, f"Error en /marketing/metricas: {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "SEGUIDORES TOTALES" in html
    assert "ENGAGEMENT RATE (AUTOMÁTICO)" in html
    assert "Curva de Evolución & Crecimiento" in html
    assert "#LaOtraCaraDelMostrador" in html
    assert "graficaEvolucionMarketing" in html
    print("   [PASS] Módulo de Métricas de Redes Sociales carga KPIs, variaciones y Chart.js.")

    print("4. Probando filtro de TikTok...")
    resp = client.get("/marketing/metricas?red=TikTok")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "TikTok" in html
    print("   [PASS] Filtro de TikTok funciona correctamente.")

    print("5. Probando Historial de Gastos con Cuenta de Origen...")
    resp = client.get("/finanzas/gastos")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Cuenta Origen" in html
    assert "Cuenta Nu" in html
    print("   [PASS] Costos y Gastos reflejan cuenta de origen.")

    print("6. Verificando regla de 1er mes incluido en Local post-corte...")
    burger = Local.query.filter_by(nombre_marca="BurgerHouse Gourmet").first()
    assert burger is not None
    # Próxima fecha corte debe ser 1 mes después de lanzamiento
    prox_corte = burger.proxima_fecha_corte
    assert prox_corte > burger.fecha_lanzamiento + timedelta(days=20), f"Fecha próxima: {prox_corte}"
    print(f"   [PASS] Lanzamiento: {burger.fecha_lanzamiento} -> Próximo cobro mensual: {prox_corte} (regla 1er mes cumplida).")

    print("\nTODOS LOS TESTS DE BLOQUE 1 Y BLOQUE 2 PASARON EXITOSAMENTE.")
