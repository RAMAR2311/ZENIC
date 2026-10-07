"""
crypto_utils.py — Módulo de Bóveda Segura | Zenic Master Control
=================================================================
Usa encriptación simétrica Fernet (AES-128 CBC + HMAC-SHA256) de la
librería `cryptography`. La llave maestra vive ÚNICAMENTE en la
variable de entorno ZENIC_VAULT_KEY; nunca se escribe en el código.

Si la variable no existe, se genera automáticamente en el primer arranque
y se imprime para que la pegues en tu .env — GUÁRDALA, si la pierdes
no podrás desencriptar las contraseñas existentes.

Uso:
    from crypto_utils import encrypt_password, decrypt_password

    cifrado = encrypt_password("miContraseña123")
    original = decrypt_password(cifrado)
"""

import os
import base64
from cryptography.fernet import Fernet


def _get_or_create_key() -> bytes:
    """
    Obtiene la clave Fernet desde la variable de entorno ZENIC_VAULT_KEY.
    Si no existe, genera una nueva y la imprime para que el operador la guarde.
    """
    raw_key = os.environ.get("ZENIC_VAULT_KEY", "").strip()
    if raw_key:
        # Validar que sea una clave Fernet válida (URL-safe base64 de 32 bytes)
        try:
            decoded = base64.urlsafe_b64decode(raw_key + "==")
            assert len(decoded) == 32
            return raw_key.encode()
        except Exception:
            raise ValueError(
                "❌ ZENIC_VAULT_KEY inválida. Debe ser una clave Fernet (44 chars base64-url-safe)."
            )
    else:
        new_key = Fernet.generate_key()
        sep = "=" * 60
        print("\n" + sep)
        print("[AVISO] ZENIC VAULT KEY no encontrada. Se genero una nueva:")
        print(f"    ZENIC_VAULT_KEY={new_key.decode()}")
        print("    Agregala a tu archivo .env AHORA para no perder datos.")
        print(sep + "\n")
        return new_key


# Instancia singleton del cifrador
_fernet = Fernet(_get_or_create_key())


def encrypt_password(plain_text: str) -> str:
    """
    Cifra una contraseña en texto plano y devuelve el token encriptado
    como string (para guardar en la base de datos).
    """
    if not plain_text:
        return ""
    return _fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_password(token: str) -> str:
    """
    Descifra un token previamente encriptado con encrypt_password().
    Devuelve el texto original o cadena vacía si el token es inválido/vacío.
    """
    if not token:
        return ""
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return "⚠️ Error al descifrar"
