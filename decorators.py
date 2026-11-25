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
    Todos los perfiles autenticados (admin, operaciones_finanzas, ti, marketing)
    pueden acceder para ver sus tickets asignados, cambiar estado, dejar comentarios
    de solución y validar los tickets que crearon/asignaron.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
