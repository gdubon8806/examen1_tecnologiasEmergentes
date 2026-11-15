# 12. Guion del video (5 minutos) y demo en vivo

## Antes de grabar (checklist)
- [ ] Docker Desktop abierto y contenedor `dp_sqlserver` corriendo.
- [ ] `.venv` activo en una PowerShell dentro de `data-platform` (fuente grande, ventana limpia).
- [ ] Servidor arrancado (`python -m uvicorn backend.app.main:app --port 8000`) y sesión iniciada en http://localhost:8000.
- [ ] Si usas Ollama: haz una pregunta de prueba **antes** de grabar para que el modelo esté cargado.
- [ ] SSMS conectado (`localhost,1434`) con `04_reconciliation.sql` y `07_evidence_queries.sql` abiertos y la base `AnalyticsDW` seleccionada.
- [ ] Ya existe una alerta lista para mostrar, o el comando para crearla en una línea: `python notifications/alert_engine.py --simulate-drop 30`.
- [ ] Cerrar notificaciones y pestañas con datos personales. **No mostrar el archivo `.env`, contraseñas ni tokens.**
- [ ] Grabar con audio claro y pantalla legible (zoom del navegador al 110–125%).
- [ ] Ensayar una vez cronometrado.

## Guion por tiempos
| Tiempo | Qué se muestra | Qué se dice (ideas) |
|---|---|---|
| **0:00–0:40** | Diagrama de `02_arquitectura.md` (puede abrirse en VS Code/GitHub) | «Convertimos una base transaccional de ventas (WideWorldImporters) en una plataforma de analítica: ETL en Python, staging raw/clean, Data Warehouse estrella en SQL Server, dashboard con API segura, modelo de pronóstico, asistente de IA y alertas. Todo reproducible con Docker y scripts.» |
| **0:40–1:30** | PowerShell: `python etl/run_pipeline.py`; luego SSMS: `SELECT TOP 10 * FROM audit.etl_run ORDER BY start_time DESC` y `SELECT failed_rule, COUNT(*) FROM audit.quarantine GROUP BY failed_rule` | «Extracción incremental con watermark, limpieza con reglas y cuarentena, carga del DW. Cada paso queda auditado con conteos y estado. Si lo repito, no duplica (idempotente).» |
| **1:30–2:15** | SSMS: resultados de `04_reconciliation.sql` (diferencia = 0, ventas por año) y `SELECT … FROM dw.DimCustomer` de un cliente con 2 versiones | «Grano: una fila por línea de orden. Origen = DW + cuarentena y las ventas netas coinciden. El cliente cambió de categoría y se guardó la historia (SCD Tipo 2).» |
| **2:15–3:00** | Dashboard, pestaña *Ventas*: KPIs, cambiar fechas, filtrar por un grupo, clic en un mes, tabla paginada; mostrar «datos actualizados» | «Cinco KPIs validados contra SQL independiente, filtros, comparación con el periodo anterior y drill-down. El navegador solo habla con la API; la API usa un usuario de solo lectura.» |
| **3:00–3:45** | Pestaña *Predicción (ML)*; tabla de métricas | «Pronóstico mensual con tendencia y estacionalidad, división por tiempo y prueba usada una sola vez. Lo comparo con baselines: [decir el veredicto real]. Está marcado como predicción, con versión del modelo, fecha y horizonte.» |
| **3:45–4:25** | Pestaña *Asistente (IA)*: 1) «¿Cuáles fueron las ventas del último trimestre?» 2) «¿Cuáles fueron las ventas en 2030?» | «El asistente no ejecuta SQL libre: usa consultas aprobadas. Separa hechos e interpretación y verifica cifras. Cuando no hay datos, lo dice.» |
| **4:25–5:00** | Pestaña *Alertas*: abrir una alerta, mostrar detalle y entregas; cambiar su estado; cierre | «Regla de ventas y regla basada en la predicción, sin duplicados y con registro de entrega. [Si fue simulada, decirlo.] Funciona: ETL, DW, dashboard, ML, asistente y alertas. Limitaciones: por lotes (no tiempo real), pocos meses de historia, login de un usuario.» |

## Frases que conviene decir (y que la guía valora)
- «El evento de alerta es **simulado** para la demo» (si lo es).
- «Esta cifra es una **predicción**, no un dato histórico.»
- «El pipeline es por lotes; no es tiempo real.»
- «Si una carga falla, se deshace y se reintenta sin inconsistencias» (mostrar la falla controlada si cabe, o mencionarla).

## Demo en vivo (si se pide)
1. Ejecutar un lote de prueba: `python etl/run_pipeline.py`.
2. Mostrar el dashboard y una consulta analítica (reconciliación o KPI vs SQL).
3. Mostrar una predicción con versión identificable (pestaña Predicción o `ml.forecast_sales`).
4. Hacer una pregunta al asistente.
5. Disparar una alerta de prueba y mostrar registro: `python notifications/alert_engine.py --simulate-drop 30` y la pestaña Alertas.
6. Explicar la recuperación de una ejecución fallida: «`audit.etl_run` muestra `FAILED` con el error; el watermark no avanzó; corrijo la causa y repito el pipeline».

## Plan B si algo falla durante la demo
- SQL Server caído → `docker compose up -d` y esperar 1–2 minutos.
- Asistente lento → cambiar a `LLM_PROVIDER=none` y reiniciar la API (responde al instante).
- Sin internet → los gráficos no cargan (CDN); tener capturas listas.
- Tener a mano las capturas y los reportes de `documentation/` como respaldo.
