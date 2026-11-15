"""
Reglas de alerta (funciones puras, sin base de datos: faciles de probar).
Cada regla devuelve un diccionario con 'triggered' (True/False) y todos los campos de la alerta,
o None si no hay referencia suficiente para comparar.
"""
import pandas as pd


def pct_change(observed: float, reference: float):
    return None if not reference else (observed - reference) / reference * 100


def reference_avg(series: pd.Series, month, n: int = 3):
    """Promedio de los n meses ANTERIORES a 'month' (None si no hay suficientes)."""
    prev = series[series.index < pd.Timestamp(month)].tail(n)
    return float(prev.mean()) if len(prev) == n else None


def severity_for(change_pct: float, threshold_pct: float) -> str:
    return "ALTA" if -change_pct >= 2 * threshold_pct else "MEDIA"


def _money(v: float) -> str:
    return f"{v:,.0f} USD"


def evaluate_sales_drop(series: pd.Series, month, threshold_pct: float, simulate_drop_pct: float = 0.0):
    """Regla de negocio: ventas del mes vs promedio de los 3 meses anteriores."""
    month = pd.Timestamp(month)
    if month not in series.index:
        raise ValueError(f"El mes {month:%Y-%m} no esta en la serie de meses completos")
    reference = reference_avg(series, month)
    if reference is None:
        return None
    observed = float(series[month]) * (1 - simulate_drop_pct / 100)
    change = pct_change(observed, reference)
    simulated = simulate_drop_pct > 0
    triggered = change is not None and change <= -threshold_pct
    label = f"{month:%Y-%m}"
    return {
        "triggered": triggered, "rule_code": "SALES_DROP", "source_type": "RULE",
        "event_key": f"SALES_DROP|{label}" + ("|SIM" if simulated else ""),
        "severity": severity_for(change, threshold_pct) if triggered else None,
        "indicator": "Ventas netas mensuales", "entity": "Total empresa",
        "period_label": label, "reference_label": "Promedio de los 3 meses anteriores",
        "observed_value": round(observed, 2), "reference_value": round(reference, 2),
        "threshold_pct": float(threshold_pct), "change_pct": round(change, 1), "model_version": None,
        "is_simulated": simulated,
        "explanation": (("EVENTO SIMULADO para la demo. " if simulated else "") +
                        f"Las ventas netas de {label} fueron {_money(observed)}, {abs(change):.1f}% "
                        f"{'por debajo' if change < 0 else 'por encima'} del promedio de los 3 meses anteriores "
                        f"({_money(reference)}). El umbral de la regla es una caida de {threshold_pct:g}%."),
        "recommended_action": ("Revisar en el dashboard que categorias, territorios o clientes explican la caida; "
                               "confirmar que no hubo fallas de carga de datos y evaluar acciones comerciales."),
    }


def evaluate_forecast_drop(series: pd.Series, target_month, predicted: float, model_version: str,
                           threshold_pct: float):
    """Regla basada en Machine Learning: prediccion vs promedio de los ultimos 3 meses reales."""
    if len(series) < 3:
        return None
    reference = float(series.tail(3).mean())
    change = pct_change(float(predicted), reference)
    triggered = change is not None and change <= -threshold_pct
    label = f"{pd.Timestamp(target_month):%Y-%m}"
    return {
        "triggered": triggered, "rule_code": "FORECAST_DROP", "source_type": "ML",
        "event_key": f"FORECAST_DROP|{model_version}|{label}",
        "severity": severity_for(change, threshold_pct) if triggered else None,
        "indicator": "Ventas netas pronosticadas", "entity": "Total empresa",
        "period_label": label, "reference_label": "Promedio de los ultimos 3 meses reales",
        "observed_value": round(float(predicted), 2), "reference_value": round(reference, 2),
        "threshold_pct": float(threshold_pct), "change_pct": round(change, 1), "model_version": model_version,
        "is_simulated": False,
        "explanation": (f"PREDICCION del modelo {model_version}: ventas netas de {label} estimadas en "
                        f"{_money(predicted)}, {abs(change):.1f}% {'por debajo' if change < 0 else 'por encima'} "
                        f"del promedio de los ultimos 3 meses reales ({_money(reference)}). "
                        f"Umbral de la regla: {threshold_pct:g}%."),
        "recommended_action": ("Tomar la prediccion como senal temprana (tiene margen de error): revisar el plan de "
                               "compras e inventario y vigilar las ventas reales del mes."),
    }
