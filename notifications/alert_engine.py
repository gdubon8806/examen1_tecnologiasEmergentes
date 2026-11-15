"""
Motor de alertas: evalua reglas, crea alertas SIN duplicados y las entrega.
Canales: dashboard (siempre) y correo SMTP (opcional, si hay SMTP_HOST y ALERT_EMAIL_TO en .env).
Uso (desde data-platform, con el entorno virtual activo):
  python notifications/alert_engine.py                      evalua el ultimo mes completo y la prediccion
  python notifications/alert_engine.py --scan               muestra la variacion de todos los meses (no crea alertas)
  python notifications/alert_engine.py --month 2015-12      evalua un mes historico (reproduccion con datos reales)
  python notifications/alert_engine.py --threshold 5        cambia el umbral solo para esta corrida
  python notifications/alert_engine.py --simulate-drop 30   evento SIMULADO: ultimo mes con 30% menos de ventas
"""
import argparse
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
from sqlalchemy import text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (ROOT / "etl", ROOT / "machine-learning", HERE):
    sys.path.insert(0, str(p))

from extract_to_raw import make_engine   # noqa: E402
from forecast_lib import complete_monthly_series   # noqa: E402
from load_dw import run_script   # noqa: E402
import alert_rules as R   # noqa: E402

SQL = ROOT / "database" / "scripts" / "09_create_alerts.sql"
MAX_EMAIL_ATTEMPTS = 5


# ---------- datos ----------
def load_series(engine):
    try:
        df = pd.read_sql(text("SELECT month_start, net_sales, last_day_with_data FROM dw.vw_monthly_sales "
                              "ORDER BY month_start"), engine)
    except Exception as exc:  # noqa: BLE001
        sys.exit("No se pudo leer dw.vw_monthly_sales. Ejecuta antes machine-learning/train_forecast.py\n" + str(exc))
    return complete_monthly_series(df, pd.to_datetime(df["last_day_with_data"]).max())


def get_rule(engine, code):
    with engine.connect() as c:
        row = c.execute(text("SELECT threshold_pct, is_active FROM alerts.alert_rule WHERE rule_code = :c"),
                        {"c": code}).fetchone()
    return (float(row[0]), bool(row[1])) if row else (15.0, True)


def latest_forecast(engine):
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT TOP 1 f.model_version, f.target_month, f.predicted_net_sales
            FROM ml.forecast_sales f
            JOIN ml.model_registry m ON m.model_version = f.model_version AND m.is_active = 1
            WHERE f.prediction_date = (SELECT MAX(prediction_date) FROM ml.forecast_sales
                                       WHERE model_version = f.model_version)
            ORDER BY f.horizon_months""")).fetchone()
    return row


# ---------- alertas ----------
def insert_alert(engine, a):
    """Inserta la alerta si su event_key no existe. Devuelve alert_id o None (ya existia)."""
    sql = """
    IF NOT EXISTS (SELECT 1 FROM alerts.alert WHERE event_key = :event_key)
        INSERT INTO alerts.alert (event_key, rule_code, source_type, severity, indicator, entity, period_label,
            reference_label, observed_value, reference_value, threshold_pct, change_pct, model_version,
            explanation, recommended_action, is_simulated)
        OUTPUT inserted.alert_id
        VALUES (:event_key, :rule_code, :source_type, :severity, :indicator, :entity, :period_label,
            :reference_label, :observed_value, :reference_value, :threshold_pct, :change_pct, :model_version,
            :explanation, :recommended_action, :is_simulated)"""
    with engine.begin() as c:
        res = c.execute(text(sql), {**a, "is_simulated": int(a["is_simulated"])})
        row = res.fetchone() if res.returns_rows else None
        if row is None:
            return None
        c.execute(text("""INSERT INTO alerts.delivery (alert_id, channel, status, attempts, last_attempt_at)
                          VALUES (:i, 'DASHBOARD', 'SENT', 1, SYSDATETIME())"""), {"i": row[0]})
        return int(row[0])


def smtp_config():
    host, to = os.getenv("SMTP_HOST"), os.getenv("ALERT_EMAIL_TO")
    if not host or not to:
        return None
    return {"host": host, "port": int(os.getenv("SMTP_PORT", "587")), "user": os.getenv("SMTP_USER"),
            "password": os.getenv("SMTP_PASSWORD"), "to": to}


def send_email(cfg, alert):
    msg = EmailMessage()
    sim = " (SIMULADA)" if alert["is_simulated"] else ""
    origin = {"RULE": "regla de negocio", "ML": "modelo de Machine Learning", "AI": "IA generativa"}[alert["source_type"]]
    msg["Subject"] = f"[ALERTA {alert['severity']}]{sim} {alert['indicator']} - {alert['period_label']}"
    msg["From"] = cfg["user"] or "alertas@localhost"
    msg["To"] = cfg["to"]
    msg.set_content(
        f"Alerta #{alert['alert_id']} - {alert['created_at']}\nOrigen: {origin}\n"
        f"Indicador: {alert['indicator']} ({alert['entity']})\nPeriodo: {alert['period_label']}\n"
        f"Valor: {alert['observed_value']:,.0f} | Referencia: {alert['reference_value']:,.0f} "
        f"({alert['reference_label']}) | Umbral: {alert['threshold_pct']:g}%\n\n"
        f"{alert['explanation']}\n\nAccion recomendada: {alert['recommended_action']}\n")
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as s:
        if cfg["port"] != 25:
            s.starttls()
        if cfg["user"] and cfg["password"]:
            s.login(cfg["user"], cfg["password"])
        s.send_message(msg)


def email_attempt(engine, cfg, alert_id):
    """Un intento de envio; deja constancia (SENT/FAILED, intentos, error) en alerts.delivery."""
    with engine.connect() as c:
        r = c.execute(text("""SELECT alert_id, created_at, source_type, severity, indicator, entity, period_label,
                                     reference_label, observed_value, reference_value, threshold_pct, explanation,
                                     recommended_action, is_simulated FROM alerts.alert WHERE alert_id = :i"""),
                      {"i": alert_id}).fetchone()
    alert = dict(r._mapping)
    alert["observed_value"], alert["reference_value"] = float(alert["observed_value"]), float(alert["reference_value"])
    status, error = "SENT", None
    try:
        send_email(cfg, alert)
    except Exception as exc:  # noqa: BLE001
        status, error = "FAILED", f"{type(exc).__name__}: {exc}"[:500]
    with engine.begin() as c:
        upd = c.execute(text("""UPDATE alerts.delivery SET status = :s, attempts = attempts + 1,
                                last_attempt_at = SYSDATETIME(), error_detail = :e
                                WHERE alert_id = :i AND channel = 'EMAIL'"""),
                        {"s": status, "e": error, "i": alert_id})
        if upd.rowcount == 0:
            c.execute(text("""INSERT INTO alerts.delivery (alert_id, channel, status, attempts, last_attempt_at, error_detail)
                              VALUES (:i, 'EMAIL', :s, 1, SYSDATETIME(), :e)"""), {"i": alert_id, "s": status, "e": error})
    return status, error


def retry_failed_emails(engine, cfg):
    with engine.connect() as c:
        ids = [r[0] for r in c.execute(text("""SELECT alert_id FROM alerts.delivery WHERE channel = 'EMAIL'
                                               AND status = 'FAILED' AND attempts < :m"""), {"m": MAX_EMAIL_ATTEMPTS})]
    for i in ids:
        status, error = email_attempt(engine, cfg, i)
        print(f"  reintento de correo (alerta #{i}): {status}" + (f" - {error}" if error else ""))


# ---------- ejecucion ----------
def report(title, a):
    if a is None:
        print(f"  {title}: sin referencia suficiente, no se evalua")
    else:
        verdict = "SE DISPARA" if a["triggered"] else "no se dispara"
        print(f"  {title}: valor {a['observed_value']:,.0f} vs referencia {a['reference_value']:,.0f} "
              f"-> {a['change_pct']:+.1f}% (umbral -{a['threshold_pct']:g}%) -> {verdict}")


def handle(engine, a, cfg):
    if not a or not a["triggered"]:
        return
    alert_id = insert_alert(engine, a)
    if alert_id is None:
        print(f"    ya existia una alerta para este evento ({a['event_key']}): NO se duplica")
        return
    print(f"    ALERTA #{alert_id} creada [{a['severity']}] y entregada al dashboard")
    if cfg:
        status, error = email_attempt(engine, cfg, alert_id)
        print(f"    correo: {status}" + (f" - {error}" if error else ""))


def scan(series, threshold):
    print(f"{'Mes':<8}{'Ventas':>14}{'Referencia(3m)':>16}{'Cambio':>9}")
    for m in series.index:
        ref = R.reference_avg(series, m)
        if ref is None:
            continue
        ch = R.pct_change(series[m], ref)
        print(f"{m:%Y-%m}".ljust(8) + f"{series[m]:>14,.0f}{ref:>16,.0f}{ch:>8.1f}%"
              + ("   <-- ALERTA" if ch <= -threshold else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--month")
    ap.add_argument("--threshold", type=float)
    ap.add_argument("--simulate-drop", type=float, default=0.0)
    args = ap.parse_args()

    engine = make_engine("AnalyticsDW")
    run_script(engine, SQL)
    series = load_series(engine)
    thr_sales, active_sales = get_rule(engine, "SALES_DROP")
    thr_sales = args.threshold if args.threshold is not None else thr_sales
    if args.scan:
        return scan(series, thr_sales)

    cfg = smtp_config()
    print("Canales: dashboard" + (f" + correo ({cfg['to']})" if cfg else " (correo no configurado)"))
    month = pd.Timestamp(args.month + "-01") if args.month else series.index[-1]
    if active_sales:
        print(f"Regla SALES_DROP sobre {month:%Y-%m}" + (f" [SIMULADO: -{args.simulate_drop:g}%]" if args.simulate_drop else ""))
        a = R.evaluate_sales_drop(series, month, thr_sales, args.simulate_drop)
        report("ventas vs promedio 3 meses previos", a)
        handle(engine, a, cfg)

    thr_ml, active_ml = get_rule(engine, "FORECAST_DROP")
    thr_ml = args.threshold if args.threshold is not None else thr_ml
    fc = None if args.month else latest_forecast(engine)
    if active_ml and fc is not None:
        print(f"Regla FORECAST_DROP sobre la prediccion de {pd.Timestamp(fc[1]):%Y-%m} (modelo {fc[0]})")
        a = R.evaluate_forecast_drop(series, fc[1], float(fc[2]), fc[0], thr_ml)
        report("prediccion vs promedio 3 meses reales", a)
        handle(engine, a, cfg)
    elif not args.month:
        print("Regla FORECAST_DROP: no hay prediccion (ejecuta machine-learning/predict_forecast.py)")

    if cfg:
        retry_failed_emails(engine, cfg)
    print("Listo. Revisa la pestaña Alertas del dashboard.")


if __name__ == "__main__":
    main()
