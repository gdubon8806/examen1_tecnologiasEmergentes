# 7. Machine Learning: pronóstico de ventas mensuales

> Los números definitivos (métricas, periodos, conclusión) los genera el entrenamiento en
> `documentation/ml/model_report.md` y `documentation/ml/experiments.csv`. Este documento explica el diseño.

## Problema y decisión
- **Problema:** regresión sobre serie de tiempo: ventas netas mensuales de los próximos 3 meses.
- **Usuario y decisión:** planificación de compras e inventario y detección temprana de caídas (alimenta la regla de alerta `FORECAST_DROP`).
- **Variable objetivo:** suma mensual de `FactSales.NetAmount`, de la vista `dw.vw_monthly_sales`.

## Datos
Vista analítica controlada `dw.vw_monthly_sales`. Se excluye el último mes si está incompleto (por ejemplo, un solo día de datos) y se exige que no falten meses intermedios; si faltan, el entrenamiento se detiene con un error claro en vez de fabricar valores.

## Variables (sin fuga de datos)
Solo se derivan **de la fecha**: tendencia (meses desde el inicio) y estacionalidad (senos y cosenos del mes, 0–2 armónicos). Ninguna usa ventas del futuro ni del periodo de prueba, de modo que no hay *data leakage*. No hay imputación: no existen faltantes en estas variables.

## Validación (siempre por tiempo)
| Conjunto | Uso |
|---|---|
| Entrenamiento | Ajustar los modelos (los meses más antiguos) |
| Validación (6 meses) | Elegir armónicos y `alpha`: 15 configuraciones |
| Prueba (6 meses) | **Se usa una sola vez**, tras elegir el modelo, reentrenado con entrenamiento + validación |
| Final | Reentrenado con todos los meses completos para pronosticar |

El escalador de variables se ajusta solo con los datos de entrenamiento (dentro del *pipeline*).

## Algoritmo y baselines
- **Modelo:** Ridge (regresión lineal regularizada) con tendencia + estacionalidad. Es simple e interpretable, apropiado para tan pocos meses.
- **Baselines:** (1) último valor, (2) mismo mes del año anterior, (3) promedio del entrenamiento. El modelo debe compararse contra ellos; **si no los supera, el reporte lo dice** y esa es una conclusión válida.
- **Métricas:** MAE, RMSE y MAPE.
- **Intervalo del 80%:** `predicción ± 1,2816 × RMSE de prueba`; es una aproximación (supone errores normales).

## Versionado y trazabilidad
- Modelo guardado en `machine-learning/models/<version>.joblib` y registrado en `ml.model_registry` (versión, fecha, datos hasta, hiperparámetros, métricas del modelo y del mejor baseline, `metrics_json`).
- Predicciones en `ml.forecast_sales`: versión del modelo, **fecha de predicción**, **horizonte** y `is_prediction = 1`. Repetir la predicción el mismo día no duplica filas.
- En el dashboard, la pestaña *Predicción (ML)* muestra el aviso «PREDICCIÓN», las métricas en datos no usados para entrenar y las limitaciones.

## Ejecución
```
python machine-learning/train_forecast.py     # entrena, evalúa, registra, genera el reporte
python machine-learning/predict_forecast.py   # genera y guarda las predicciones (programable)
python tests/test_forecast_lib.py             # 9 pruebas con datos sintéticos
```

## Limitaciones y sesgos
- ~41 meses de historia y 6 de prueba: estimaciones inestables.
- Solo tendencia y estacionalidad: no conoce promociones, precios, inventario ni eventos externos.
- Los datos son de ejemplo (2013–2016) y sintéticos; sirven para demostrar el proceso.
- Intervalo aproximado.
- Sesgo: la serie es agregada para toda la empresa; no mide error por territorio ni por producto.

## Reentrenamiento y monitoreo
Reentrenar cada vez que se carguen meses nuevos (`train_forecast.py`). Monitorear el error real contra la predicción cuando el mes se cierre; si el error en producción supera claramente el de prueba, reentrenar o revisar el modelo.
