# Verificación de punta a punta

Ejecutado: 2026-11-15 14:04

| Comprobación | Resultado | Detalle |
|---|---|---|
| Conteo de filas: origen = DW + cuarentena | PASA | origen 231,413 = dw 231,413 + cuarentena 0 (diferencia 0) |
| Ventas netas: origen vs DW | PASA | ventas netas origen 177,635,956.40 vs dw 177,635,956.40 |
| Sin duplicados en FactSales | PASA | 231,413 filas, 231,413 líneas distintas |
| Hechos con dimensión desconocida | PASA | 0 hechos con cliente/producto desconocido |
| SCD Tipo 2: una sola versión vigente por cliente | PASA | clientes con 2+ versiones vigentes: 0; clientes con historial (SCD2): 1 |
| Última ejecución de cada proceso exitosa | PASA | 26 procesos; última ejecución fallida en: ninguno |
| Watermark de la carga incremental | PASA | watermark de FactSales: 2026-11-15 00:58:10.513333 |
| Modelo de ML activo y predicciones | PASA | modelo activo: sales_ridge_20261115_110217; predicciones guardadas: 3 |
| Alertas y entregas registradas | PASA | 1 alertas, 1 entregas registradas |
| Registro de consultas del asistente | PASA | 6 consultas registradas |
| Oportunidad de los datos | INFO | última carga exitosa hace 1140 minutos (oportunidad de los datos) |
| API en línea (opcional) | OMITIDA | el servidor no está corriendo (arráncalo para esta comprobación) |