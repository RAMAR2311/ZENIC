# Guía de Ejecución Local - Zenic Master Control

Este proyecto ha quedado completamente configurado y listo para ejecutarse en tu máquina local.

---

## 🚀 Inicio Rápido (1 Clic)

Simplemente ejecuta el archivo:
- **`run.bat`** (haciendo doble clic o ejecutándolo desde la consola)

O desde PowerShell / Terminal:
```powershell
.\venv\Scripts\python.exe app.py
```

Luego abre tu navegador en:
👉 **[http://127.0.0.1:5050](http://127.0.0.1:5050)**

---

## 🔑 Credenciales de Acceso

- **Correo:** `admin@zenic.co`
- **Contraseña:** `Zenic2026!`

---

## ⚙️ Configuración y Variables de Entorno (`.env`)

El archivo [`.env`](file:///C:/ZENIC-main/.env) ya está creado y configurado con:

```env
SECRET_KEY=zenic-master-dev-key-2026
ZENIC_VAULT_KEY=W_xjkl0fH5G2giHZFcXnnhklpe8QoP_9O1ngrqUJzcM=
DATABASE_URL=sqlite:///zenic_master.db
ENABLE_SCHEDULER=true
FLASK_DEBUG=1
```

### ¿Deseas usar PostgreSQL en lugar de SQLite?
1. Asegúrate de tener el servicio de PostgreSQL iniciado y la base de datos `ZenicMaster` creada.
2. En el archivo `.env`, cambia la línea `DATABASE_URL`:
   ```env
   DATABASE_URL=postgresql://postgres:admin123@localhost:5432/ZenicMaster
   ```
3. Ejecuta la inicialización:
   ```powershell
   .\venv\Scripts\python.exe reset_db.py
   ```

---

## 🔄 Reiniciar o Recrear la Base de Datos

Si en algún momento deseas limpiar la base de datos y recrear el usuario administrador inicial, corre:

```powershell
.\venv\Scripts\python.exe reset_db.py
```
*(El script detecta automáticamente si estás usando SQLite o PostgreSQL)*.

---

## 📦 Estructura del Entorno

- **`venv\`**: Entorno virtual con Python 3.14 y todas las dependencias instaladas (`Flask`, `SQLAlchemy`, `Flask-Login`, `cryptography`, `psycopg2-binary`, etc.).
- **`zenic_master.db`**: Base de datos SQLite inicializada con el usuario administrador.
- **`static/uploads/`**: Carpetas para documentos y tickets de soporte.
