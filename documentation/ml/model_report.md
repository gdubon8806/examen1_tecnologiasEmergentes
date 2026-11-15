# Modelo de pronostico de ventas mensuales

- **Version:** sales_ridge_20261115_110217
- **Problema:** pronosticar las ventas netas mensuales (regresion sobre serie de tiempo).
- **Decision que apoya:** planificar inventario/compras y detectar caidas de ventas (alertas).
- **Datos:** `dw.vw_monthly_sales` (Data Warehouse), 41 meses completos
  (2013-01 a 2016-05). El ultimo mes se excluye si esta incompleto.
- **Algoritmo:** Ridge (regresion lineal regularizada) con tendencia + estacionalidad
  (1 armonicos), alpha = 10.0. Escalador ajustado solo con entrenamiento.
- **Variables:** solo derivadas de la fecha (tendencia y senos/cosenos del mes). Sin fuga de datos.

## Division temporal (nunca aleatoria)
| Conjunto | Periodo |
|---|---|
| Entrenamiento | 2013-01 a 2015-05 (29 meses) |
| Validacion (elegir hiperparametros) | 2015-06 a 2015-11 (6 meses) |
| Prueba (usada una sola vez) | 2015-12 a 2016-05 (6 meses) |

## Resultados en PRUEBA (datos no usados para entrenar ni para elegir el modelo)
| Modelo / baseline | MAE | RMSE | MAPE |
|---|---|---|---|
| modelo | 181,473 | 250,207 | 4.1% |
| naive_ultimo_valor | 473,594 | 527,100 | 9.9% |
| naive_estacional | 250,980 | 307,404 | 5.3% |
| promedio_entrenamiento | 450,538 | 499,526 | 9.4% |

**Conclusion:** El modelo mejora al mejor baseline (naive_estacional) en 27.7% de MAE en la prueba.

## Limitaciones
- Pocos meses de historia: la estimacion es inestable y el periodo de prueba es corto (6 meses).
- Solo usa tendencia y estacionalidad: no conoce promociones, precios, inventario ni eventos externos.
- El intervalo del 80 % es aproximado (supone errores normales con la RMSE de la prueba).
- Datos de ejemplo (WideWorldImporters): sirven para demostrar el proceso, no para decisiones reales.
- Reentrenar cada vez que se carguen meses nuevos; vigilar que el error en produccion no crezca.
