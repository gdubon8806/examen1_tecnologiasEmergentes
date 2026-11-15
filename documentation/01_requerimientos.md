# 1. Requerimientos

## Alcance
Proceso de negocio principal: **ventas** (WideWorldImporters). Plataforma de extremo a extremo: origen relacional → staging → Data Warehouse dimensional → dashboard, Machine Learning, asistente de IA generativa y alertas.

## Preguntas analíticas
1. ¿Cuánto se vendió por mes, trimestre y año, y cómo cambia frente al periodo anterior?
2. ¿Qué grupos de producto, categorías de cliente y territorios crecen o caen?
3. ¿Quiénes son los clientes y productos con más ventas?
4. ¿Cuántas órdenes, unidades y clientes activos hay y cuál es el ticket promedio?
5. ¿Cómo se esperan las ventas de los próximos meses?
6. ¿Hay caídas de ventas que requieran atención?
7. ¿Qué tan actualizados y confiables son los datos?

## Requerimientos funcionales
| ID | Requerimiento | Dónde se cumple |
|---|---|---|
| RF-01 | Extraer datos de la base relacional (carga inicial e incremental) | `etl/extract_to_raw.py`, `etl/extract_incremental.py` |
| RF-02 | Conservar datos originales y datos depurados por separado (raw / clean) | esquemas `raw`, `clean` |
| RF-03 | Perfilar, limpiar, validar y enviar rechazos a cuarentena con la regla que falló | `etl/cleaning_rules.py`, `audit.quarantine` |
| RF-04 | Modelo dimensional (estrella) con claves sustitutas, SCD 1 y SCD 2 | `database/scripts/03_create_dw_model.sql` |
| RF-05 | Auditar cada ejecución (conteos, estado, error, watermark) | `audit.etl_run`, `audit.etl_watermark` |
| RF-06 | Dashboard web con 5 KPIs, filtros, tendencias, comparación de periodos, drill-down, tabla paginada | `frontend/index.html`, `backend/` |
| RF-07 | Autenticación para el dashboard y la API | `POST /api/login` |
| RF-08 | Modelo de Machine Learning con baseline, división temporal, versión y predicciones guardadas | `machine-learning/` |
| RF-09 | Mostrar predicciones identificadas como tales | pestaña *Predicción (ML)* |
| RF-10 | Asistente de IA generativa con consultas controladas y respuestas respaldadas | `generative_ai/` |
| RF-11 | Alertas por regla de negocio y por predicción, con estado, sin duplicados y con registro de entrega | `notifications/` |
| RF-12 | Vista operativa del pipeline (ejecuciones, fallas, watermarks) | pestaña *Operación (ETL)* |
| RF-13 | Reejecución idempotente y recuperación ante fallas | transacciones + upsert + watermark |

## Requerimientos no funcionales
| ID | Requerimiento | Cómo se cumple |
|---|---|---|
| RNF-01 | Reproducibilidad | Docker Compose + scripts numerados + `README.md` |
| RNF-02 | Seguridad | secretos en `.env` (fuera de Git); usuario `api_reader` de mínimo privilegio; consultas parametrizadas; el navegador nunca habla con SQL Server |
| RNF-03 | Trazabilidad | columnas `_execution_id`, `_loaded_at`, `_clean_execution_id`; `audit.*` |
| RNF-04 | Calidad de datos | reglas documentadas y probadas; perfilado antes/después |
| RNF-05 | Rendimiento medible | cabecera `X-Response-ms` y `backend/logs/response_times.csv` |
| RNF-06 | Privacidad en IA | solo cifras agregadas al modelo; sin desglose por cliente con servicios externos; registro de consultas sin resultados |
| RNF-07 | Usabilidad | estados de carga/error/sin datos; diseño adaptable a pantallas pequeñas |
| RNF-08 | Mantenibilidad | lógica en módulos y scripts; pruebas automáticas (`tests/`) |
| RNF-09 | Costo | todo local y gratuito (ver sección de costos del README) |

## Fuera de alcance (limitaciones declaradas)
- Alta disponibilidad, balanceo y cifrado extremo a extremo (HTTPS) no se implementan.
- Login de un solo usuario definido en `.env` (suficiente para la demo).
- Procesamiento en tiempo real: no existe; el pipeline es por lotes (ver `02_arquitectura.md`).
- Las compras e inventario del origen no se modelan; el foco es ventas.
