# Plataforma Integral de Ingeniería de Datos y Analítica Inteligente

Proyecto de extremo a extremo: **base transaccional → ETL → staging → Data Warehouse → dashboard, Machine Learning, IA generativa y alertas**, sobre un caso de **ventas** (base de ejemplo WideWorldImporters).

```
WideWorldImporters ─► ETL (Python) ─► raw ─► clean ─► Data Warehouse (estrella, SQL Server)
                                                          ├─► API FastAPI ─► Dashboard web
                                                          ├─► Modelo de pronóstico (ML)
                                                          ├─► Alertas (regla y predicción)
                                                          └─► Asistente de IA (consultas aprobadas)
```

## 1. Qué necesitas instalar (una sola vez)

| Programa | Para qué sirve | Notas |
|---|---|---|
| **Docker Desktop** | Ejecuta SQL Server en un contenedor (no hay que instalar SQL Server) | Debe estar **abierto y en verde** ("Engine running") cada vez que uses el proyecto. En Windows, con WSL 2 |
| **Python 3.11 o 3.12** | Ejecuta el ETL, la API, el modelo y las alertas | Marca «Add Python to PATH» al instalar |
| **Microsoft ODBC Driver 18 for SQL Server** | Permite que Python hable con SQL Server | Descárgalo de la página de Microsoft |
| **Git** | Para clonar el repositorio | git-scm.com |
| SSMS o DBeaver *(opcional)* | Ventana para mirar la base de datos | Conexión: `localhost,1434`, usuario `sa`, marcar *Trust server certificate* |
| Ollama *(opcional)* | Modelo de lenguaje local para el asistente | Sin él, el asistente funciona igual con reglas |

> **Mac con chip Apple:** SQL Server en Docker necesita activar Rosetta (Docker Desktop → Settings → General → *Use Rosetta*). Los comandos de abajo son de PowerShell; en Mac/Linux usa `./setup.sh` y `source .venv/bin/activate`.

## 2. Instalación desde cero (primera vez)

Todos los comandos se ejecutan en **PowerShell, dentro de la carpeta del proyecto**.

**Paso 1. Descargar el proyecto**
```powershell
git clone https://github.com/<usuario>/data-platform.git
cd data-platform
```

**Paso 2. Crear tu archivo de configuración.** El `.env` no viene en el repositorio (guarda contraseñas). Se crea a partir de la plantilla:
```powershell
copy .env.example .env
```
Ábrelo con el Bloc de notas y define:
- `MSSQL_SA_PASSWORD`: contraseña de SQL Server (mayúscula, minúscula, número y símbolo; mínimo 8).
- `API_DB_PASSWORD`: contraseña del usuario de solo lectura de la API (mismas reglas, sin comillas simples).
- `DASH_USER` y `DASH_PASSWORD`: usuario y contraseña con los que entrarás al dashboard.
- `API_SECRET_KEY`: una cadena larga aleatoria. Genérala con:
  ```powershell
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- Deja `LLM_PROVIDER=none` si no usarás un modelo de lenguaje.

**Paso 3. Levantar SQL Server y la base de ejemplo** *(Docker debe estar abierto)*
```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```
Descarga WideWorldImporters (~120 MB), crea el contenedor, restaura la base y crea la base `AnalyticsDW` con sus esquemas. **Puede tardar entre 5 y 15 minutos** y la restauración no muestra progreso: es normal. Termina con un mensaje de «LISTO».

**Paso 4. Crear el entorno de Python**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Sabrás que está activo cuando veas `(.venv)` al inicio de la línea. **Hay que activarlo cada vez que abras una PowerShell nueva.**

**Paso 5. Cargar y transformar los datos**
```powershell
python etl/extract_to_raw.py          # copia las 10 tablas del origen a raw
python etl/profile_data.py raw        # perfilado de calidad ANTES de limpiar
python etl/clean_raw_to_clean.py      # limpieza; rechazados a cuarentena
python etl/profile_data.py clean      # perfilado DESPUÉS de limpiar
python etl/load_dw.py                 # crea y carga el Data Warehouse
```

**Paso 6. Modelo, alertas y asistente**
```powershell
python machine-learning/train_forecast.py     # entrena y evalúa el modelo (genera documentation/ml/model_report.md)
python machine-learning/predict_forecast.py   # genera y guarda las predicciones
python notifications/alert_engine.py          # evalúa las reglas de alerta
python generative_ai/setup_ai.py              # crea el registro de consultas del asistente
python etl/create_api_user.py                 # crea el usuario de solo lectura y asigna permisos
```

**Paso 7. Arrancar la aplicación**
```powershell
python -m uvicorn backend.app.main:app --port 8000
```
Abre **http://localhost:8000** e inicia sesión con `DASH_USER` y `DASH_PASSWORD`. **No cierres esa ventana:** ahí corre el servidor (se detiene con `Ctrl + C`).

**Paso 8. Verificar que todo funciona**
```powershell
python tests/run_all.py     # pruebas automáticas (no necesitan base de datos)
python tests/e2e_check.py   # verificación de punta a punta contra la base real
```

## 3. Uso diario (después de la instalación)

1. Abre **Docker Desktop** y espera a que el contenedor `dp_sqlserver` esté corriendo (si no, `docker compose up -d`; tarda 1–2 min en estar listo).
2. Abre PowerShell en la carpeta del proyecto y activa el entorno: `.venv\Scripts\Activate.ps1`.
3. Según lo que necesites:

| Tarea | Comando |
|---|---|
| Actualizar los datos con lo nuevo del origen | `python etl/run_pipeline.py` |
| Renovar predicciones | `python machine-learning/predict_forecast.py` |
| Evaluar alertas | `python notifications/alert_engine.py` |
| Reentrenar el modelo (hay meses nuevos) | `python machine-learning/train_forecast.py` y luego `predict_forecast.py` |
| Arrancar el dashboard | `python -m uvicorn backend.app.main:app --port 8000` |

`run_pipeline.py` es el «botón de actualizar»: extrae lo nuevo, limpia y carga el almacén, y se detiene si un paso falla. Es **idempotente**: repetirlo no duplica datos. Solo funciona después de la carga inicial del Paso 5.

## 4. Qué hay en el dashboard

| Pestaña | Contenido |
|---|---|
| **Ventas** | 5 KPIs, filtros, tendencia, gráficos por categoría, drill-down y tabla paginada |
| **Predicción (ML)** | Histórico y pronóstico (marcado como predicción), métricas y limitaciones |
| **Alertas** | Lista, detalle, entregas y cambio de estado |
| **Asistente (IA)** | Preguntas en lenguaje natural con hechos, respaldo y verificación |
| **Operación (ETL)** | Ejecuciones del pipeline, fallas y watermarks |

## 5. Si algo falla

| Síntoma | Causa probable y solución |
|---|---|
| `docker` no se reconoce | Docker Desktop no está instalado o abierto; reinicia la sesión |
| Los scripts fallan al conectarse | SQL Server no está corriendo: abre Docker Desktop, espera 1–2 minutos y reintenta. Revisa `docker logs dp_sqlserver` |
| SQL Server se apaga solo | La contraseña de `MSSQL_SA_PASSWORD` no cumple la complejidad |
| `ModuleNotFoundError` | Falta activar `.venv` (`.venv\Scripts\Activate.ps1`) |
| `ODBC Driver 18` no encontrado | Instala el driver; verifica con `python -c "import pyodbc; print(pyodbc.drivers())"` |
| El dashboard abre pero sin datos | SQL Server apagado; prueba `http://localhost:8000/api/health` |
| Pestaña Predicción o Alertas con error | Repite `python etl/create_api_user.py` (asigna permisos) |
| Los gráficos no aparecen | Sin internet: ECharts se carga desde un CDN |
| Un paso del pipeline falló | Mira `audit.etl_run` o la pestaña *Operación*, corrige y repite `run_pipeline.py` |
| Empezar todo de cero | `docker compose down -v` y repite desde el Paso 3 |

## 6. Estructura del repositorio

```
data-platform/
├── documentation/      informes, diccionarios, arquitectura, pruebas, manuales, guion del video
├── database/           scripts SQL numerados (01…10) y carpeta backups
├── etl/                extracción, limpieza, carga, orquestación, perfilado
├── backend/            API FastAPI
├── frontend/           dashboard (HTML + ECharts)
├── machine-learning/   entrenamiento, predicción, modelos
├── generative_ai/      asistente: herramientas aprobadas, verificación, proveedores
├── notifications/      reglas y motor de alertas
├── tests/              pruebas automáticas y de punta a punta
├── tools/              empaquetado de la entrega sin secretos
├── docker-compose.yml  SQL Server
├── setup.ps1 / setup.sh  arranque del ambiente
├── .env.example        plantilla de configuración (sin secretos)
└── README.md
```

## 7. Documentación

Detalle completo en la carpeta `documentation/`:
`01` requerimientos · `02` arquitectura · `03` fuente y diccionario · `04` modelo dimensional · `05` ETL y calidad · `06` API · `07` Machine Learning · `08` IA generativa · `09` alertas · `10` pruebas · `11` manual de instalación, operación y usuario · `12` guion del video.

## 8. Seguridad

- Las contraseñas viven solo en `.env`, que **no se sube a Git** (está en `.gitignore`). Nunca lo publiques.
- La API usa un usuario de **solo lectura** (`api_reader`); el navegador nunca se conecta a SQL Server.
- Las consultas están parametrizadas y el asistente no ejecuta SQL libre.
- Para entregar un `.zip` sin secretos: `python tools/make_submission_zip.py`.

## 9. Limitaciones conocidas

Procesamiento **por lotes** (no es tiempo real) · el ETL y la administración usan la cuenta `sa` · login de un solo usuario · unos 41 meses de historia para el modelo · no se detectan eliminaciones en el origen · el cliente de cada venta se asigna con la versión vigente al cargar.

## 10. Costos

Todo es local y sin costo de licencias para desarrollo y pruebas (SQL Server Developer, Python, ECharts y Ollama opcional). Un servicio de IA externo tendría costo por uso.
