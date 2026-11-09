"""
decorators.py — Decoradores de Permisos y Control de Acceso (RBAC)
==================================================================
Roles vigentes en Zenic Master Control:
  - 'admin': Acceso total
  - 'marketing': Portal de contenidos, grabaciones y redes sociales
  - 'ti': Módulo de conexiones, bóveda de clientes y tickets de cambios
  - 'operaciones_finanzas': Clientes, facturación, tesorería, gastos y emisión de tickets
"""

from functools import wraps
from flask import abort
from flask_login import current_user


def admin_required(f):
    """Acceso exclusivo para el administrador."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def marketing_required(f):
    """Acceso permitido para Marketing y Administradores."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ["marketing", "admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def ti_required(f):
    """Acceso permitido para TI / Soporte y Administradores."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ["ti", "admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def operaciones_finanzas_required(f):
    """Acceso permitido para Operaciones & Finanzas y Administradores."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ["operaciones_finanzas", "admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def tickets_access_required(f):
    """
    Acceso al módulo de tickets:
    - TI y Admin gestionan y resuelven.
    - Operaciones_finanzas crea y consulta solicitudes de sus clientes.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ["ti", "operaciones_finanzas", "admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
