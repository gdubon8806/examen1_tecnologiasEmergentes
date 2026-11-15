# 11. Manual de instalación, despliegue, operación y usuario

## A. Requisitos
- Windows 10/11 con PowerShell (en Linux/Mac los comandos equivalentes son análogos; en Mac con chip Apple, SQL Server en Docker requiere Rosetta).
- Docker Desktop (con WSL 2), Python 3.11 o 3.12, Microsoft ODBC Driver 18 for SQL Server.
- SSMS o DBeaver para consultar la base (opcional pero recomendado). Conexión: `localhost,1434`, usuario `sa`, marcar *Trust server certificate*.
- ~8 GB de RAM libres solo si se usa Ollama (opcional).
- Versiones usadas: SQL Server 2022 Developer (imagen `mcr.microsoft.com/mssql/server:2022-latest`), Python y librerías de `requirements.txt` (pandas, SQLAlchemy, pyodbc, python-dotenv, FastAPI, uvicorn, scikit-learn), Apache ECharts 5.5.1 (CDN).

## B. Instalación y despliegue (desde cero)
Todo desde la carpeta `data-platform`, en PowerShell.

| # | Paso | Comando |
|---|---|---|
| 1 | Configuración | Copiar `.env.example` a `.env` y definir contraseñas (mayúscula, minúscula, número y símbolo) y `API_SECRET_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"`) |
| 2 | SQL Server en Docker + base de origen + esquemas | `Set-ExecutionPolicy -Scope Process Bypass` y `.\setup.ps1` (descarga `WideWorldImporters-Full.bak`, ~120 MB, y puede tardar 5–15 min) |
| 3 | Entorno de Python | `python -m venv .venv` · `.venv\Scripts\Activate.ps1` · `pip install -r requirements.txt` |
| 4 | Carga inicial a `raw` | `python etl/extract_to_raw.py` |
| 5 | Calidad (antes) | `python etl/profile_data.py raw` |
| 6 | Limpieza | `python etl/clean_raw_to_clean.py` |
| 7 | Calidad (después) | `python etl/profile_data.py clean` |
| 8 | Data Warehouse | `python etl/load_dw.py` |
| 9 | Reconciliación | abrir `database/scripts/04_reconciliation.sql` en SSMS y ejecutar |
| 10 | Machine Learning | `python machine-learning/train_forecast.py` y `python machine-learning/predict_forecast.py` |
| 11 | Alertas | `python notifications/alert_engine.py` |
| 12 | Asistente | `python generative_ai/setup_ai.py` |
| 13 | Usuario de solo lectura y permisos | `python etl/create_api_user.py` (se puede repetir; asigna permisos a los esquemas ya creados) |
| 14 | Arrancar la API y el dashboard | `python -m uvicorn backend.app.main:app --port 8000` → http://localhost:8000 |
| 15 | Verificar | `python tests/run_all.py` y `python tests/e2e_check.py` |

Los archivos `database/scripts/01`…`10` están numerados en orden lógico; los ejecutan los scripts de Python/PowerShell (no se corren a mano, salvo `04`, `05`, `06` y `07`, que son para SSMS).

**Puertos y volúmenes:** SQL Server `1434` (host) → `1433` (contenedor); volumen Docker `sqldata`; las carpetas `database/backups` y `database/scripts` se montan de solo lectura. **Dependencias:** Docker corriendo antes de cualquier script de Python. Comando de Compose manual: `docker compose up -d`.

**Reiniciar todo desde cero:** `docker compose down -v` (borra el volumen) y repetir desde el paso 2.

## C. Operación diaria
| Tarea | Comando |
|---|---|
| Arrancar SQL Server | Abrir Docker Desktop; si el contenedor está apagado, `docker compose up -d` |
| Actualizar los datos | `python etl/run_pipeline.py` |
| Renovar predicciones | `python machine-learning/predict_forecast.py` |
| Evaluar alertas | `python notifications/alert_engine.py` |
| Reentrenar el modelo (meses nuevos) | `python machine-learning/train_forecast.py` y luego `predict_forecast.py` |
| Revisar la salud del proceso | pestaña *Operación (ETL)* o `SELECT TOP 30 * FROM audit.etl_run ORDER BY start_time DESC` |
| Cambiar el motor del asistente | `.env` → `LLM_PROVIDER=none|ollama|openai|anthropic` y reiniciar la API |
| Programar | Programador de tareas de Windows ejecutando `run_pipeline.py`, `predict_forecast.py` y `alert_engine.py` en secuencia |

## D. Recuperación
| Situación | Qué hacer |
|---|---|
| Un paso del pipeline falló | Leer `audit.etl_run` (`status = FAILED`, `error_detail`). Corregir la causa y **volver a ejecutar** `run_pipeline.py`: es idempotente y el watermark no avanzó |
| El DW quedó en mal estado | `python etl/load_dw.py --reset` borra `dw.*` y el watermark y recarga desde `clean` |
| `clean` o `raw` sospechosos | Repetir `extract_to_raw.py` (copia completa) y `clean_raw_to_clean.py` |
| Se perdió el contenedor o el volumen | `docker compose down -v` y repetir la instalación (paso 2 en adelante) |
| Restauración de WideWorldImporters atascada | Cancelar (`KILL <session_id>`), `DROP DATABASE` de la base a medias y volver a ejecutar `setup.ps1` |
| Correo de alertas falló | Corregir `.env` y volver a ejecutar `alert_engine.py`: reintenta los `FAILED` |

## E. Manual de usuario del dashboard
Ingresar a http://localhost:8000 con el usuario y la contraseña definidos en `.env` (`DASH_USER`, `DASH_PASSWORD`).

- **Ventas:** filtros de fecha y de categoría de cliente, grupo de producto y territorio (el botón *Restablecer* vuelve al último año de datos). Cinco KPIs con variación contra el periodo anterior. **Clic en un mes o en una barra** para filtrar (drill-down); las etiquetas con × quitan filtros. Tabla de detalle paginada. Arriba aparece la fecha de la última carga.
- **Predicción (ML):** histórico y predicción de los próximos meses (marcada como **PREDICCIÓN**), rango del 80%, métricas en datos de prueba y limitaciones.
- **Alertas:** lista con gravedad y origen; clic en una fila para ver el detalle y las entregas; botones para marcarla atendida, descartada o resuelta. El número rojo indica alertas nuevas.
- **Asistente (IA):** escribir una pregunta o usar los ejemplos. La respuesta separa *hechos consultados*, *predicción* e *interpretación generada*, y muestra supuestos, advertencias y el respaldo (herramienta y periodo).
- **Operación (ETL):** últimas ejecuciones, fallas, estado y watermarks.

## F. Solución de problemas
| Síntoma | Causa probable |
|---|---|
| `ModuleNotFoundError` | Falta activar `.venv` o faltan los `__init__.py` en `backend`, `backend/app` y `generative_ai` |
| `docker` no se reconoce | Docker Desktop no está abierto o falta reiniciar sesión |
| SQL Server no arranca | Contraseña `sa` sin complejidad; ver `docker logs dp_sqlserver` |
| El dashboard abre pero sin datos | SQL Server apagado; probar `http://localhost:8000/api/health` |
| Pestaña Predicción/Alertas con error de permisos | Repetir `python etl/create_api_user.py` |
| Gráficos no aparecen | Sin internet (ECharts se carga desde un CDN) |
| Asistente lento o con error | Ollama apagado o poca RAM; usar `LLM_PROVIDER=none` |
