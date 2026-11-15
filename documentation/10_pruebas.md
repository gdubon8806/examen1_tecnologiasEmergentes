# 10. Plan y resultados de pruebas

Dos tipos de evidencia: **automática** (se regenera con un comando) y **manual** (capturas tomadas durante la demostración). Las columnas «Resultado» y «Evidencia» se completan al ejecutar; no se registran resultados que no se hayan obtenido.

## Pruebas automáticas
| Comando | Qué demuestra | Reporte generado |
|---|---|---|
| `python tests/run_all.py` | 5 suites sin base de datos (limpieza, API, ML, alertas, asistente) | `documentation/tests/unit_test_results.md` |
| `python tests/e2e_check.py` | Verificación de punta a punta contra la base real (conteos, totales, duplicados, SCD2, auditoría, ML, alertas, oportunidad, API) | `documentation/tests/e2e_results.md` |
| `python generative_ai/evaluate_assistant.py` | 18 preguntas al asistente con contraste SQL independiente | `documentation/genai/assistant_test_results.md` |
| `python etl/profile_data.py raw` / `clean` | Calidad antes y después | `documentation/quality/profile_raw.csv`, `profile_clean.csv` |
| `python machine-learning/train_forecast.py` | Baseline, división temporal y métricas | `documentation/ml/model_report.md` |

## Plan de pruebas de la guía
| Prueba | Qué debe demostrarse | Cómo se ejecuta | Resultado esperado | Evidencia (completar) |
|---|---|---|---|---|
| Carga inicial | Se extrae y carga el conjunto acordado con conteos | `extract_to_raw.py`, `clean_raw_to_clean.py`, `load_dw.py` | `OK` por tabla; conteos en consola y en `audit.etl_run` | Captura de consola + `SELECT * FROM audit.etl_run` |
| Carga incremental | Se detectan cambios sin duplicar | `05_demo_source_changes.sql` y luego `run_pipeline.py` | `nuevas 1`/`modificadas 1` en la extracción; `insertadas 1`, `actualizadas 1` en `FactSales` | Consola + consultas 1 y 5 de `07_evidence_queries.sql` |
| Idempotencia | Reejecutar no duplica ni altera | `run_pipeline.py` dos veces sin cambios | `insertadas 0` en el DW; `filas = líneas distintas` | Consola + consulta 6 de `07_evidence_queries.sql` |
| Nulos y duplicados | Reglas aplicadas y documentadas | `test_cleaning_rules.py`; `profile_data.py` | Pruebas pasan; nulos `NO aplica/pendiente` conservados | Salida de pruebas + CSV de perfilado |
| Integridad | Huérfanos detectados y política aplicada | reglas `ORPHAN_*`; consulta de cuarentena | huérfanos en cuarentena o 0 | `SELECT failed_rule, COUNT(*) FROM audit.quarantine GROUP BY failed_rule` |
| Recuperación | Falla controlada y reintento sin inconsistencias | `06_demo_recovery.sql` (paso A) → pipeline falla → paso B → pipeline OK | `FAILED` con detalle; watermark sin cambio; luego `SUCCESS` sin duplicados | Capturas de consola y de `audit.etl_run` |
| Reconciliación | Conteos y medidas entre capas | `04_reconciliation.sql`; `e2e_check.py` | diferencia 0; ventas netas iguales (total y por año) | Capturas de los 5 resultados |
| Dashboard | KPIs = SQL independiente | consulta SQL sobre el origen con las mismas fechas | ventas, órdenes, unidades y clientes idénticos | Captura del dashboard + captura de SSMS |
| ML | Baseline, evaluación en datos no usados, límites | `train_forecast.py` | tabla de MAE/RMSE/MAPE del modelo y 3 baselines + veredicto | `model_report.md` |
| GenAI | Respuestas contrastadas; rechaza lo no respaldado | `evaluate_assistant.py` | 18/18 con esperado = obtenido | `assistant_test_results.md` |
| Alertas | Disparo, no disparo, registro y entrega | `alert_engine.py` (varias formas) | no se dispara / se dispara / no duplica; entregas en `alerts.delivery` | Consola + `SELECT * FROM alerts.alert` / `alerts.delivery` |
| Punta a punta | Flujo completo hasta el resultado visible | `e2e_check.py` + demo en vivo | sin `FALLA` | `e2e_results.md` + video |

## Pruebas de rendimiento y seguridad
| Prueba | Cómo | Evidencia |
|---|---|---|
| Tiempo de respuesta de las consultas principales | usar el dashboard con filtros combinados | `backend/logs/response_times.csv` (resumir con media y máximo por ruta) |
| Filtros combinados y periodos sin datos | fechas de 2030; grupo + territorio | captura del aviso «sin datos» |
| Sin credenciales expuestas | `F12` → *Network* en el navegador | captura sin contraseñas ni tokens de base de datos |
| Acceso sin sesión | abrir `/api/kpis` sin token | respuesta `401` |
| Mínimo privilegio | intentar `DELETE` con `api_reader` en SSMS | permiso denegado |
| Repositorio sin secretos | `python tools/make_submission_zip.py` | mensaje «No se detectaron secretos evidentes» |

## Evidencias aceptables (checklist)
- [ ] Logs con identificador de proceso (`audit.etl_run`)
- [ ] Consultas SQL reproducibles y resultados (reconciliación)
- [ ] Reportes de calidad antes y después (CSV de perfilado)
- [ ] Capturas de la aplicación con datos del entorno de prueba
- [ ] Resultados de pruebas automatizadas (`unit_test_results.md`, `e2e_results.md`)
- [ ] Métricas de evaluación y configuración del modelo (`model_report.md`)
- [ ] Registro de alertas y evidencia de entrega
- [ ] Video de ejecución y demostración en vivo
