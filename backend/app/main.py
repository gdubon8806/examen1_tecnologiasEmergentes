"""
API del dashboard (FastAPI). El navegador NUNCA habla con SQL Server: solo con esta API,
que consulta el Data Warehouse con un usuario de solo lectura y consultas parametrizadas.
Ejecutar desde la carpeta data-platform:
    uvicorn backend.app.main:app --port 8000
y abrir http://localhost:8000
"""
import csv
import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import queries as q
from .db import get_engine
from .security import make_token, same_text, verify_token
from generative_ai.assistant import answer_question
from generative_ai.llm import get_provider
from generative_ai.sqldb import SqlDb

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "backend" / "logs"
log = logging.getLogger("api")

DASH_USER = os.environ["DASH_USER"]
DASH_PASSWORD = os.environ["DASH_PASSWORD"]
SECRET = os.environ["API_SECRET_KEY"]
PROVIDER = get_provider()          # None = asistente sin modelo de lenguaje (solo reglas)

app = FastAPI(title="Plataforma de Analitica de Ventas", docs_url="/api/docs", openapi_url="/api/openapi.json")


# ---------- utilidades ----------
def run(sql: str, params: dict | None = None) -> list[dict]:
    with get_engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params or {})]


def one(sql: str, params: dict | None = None) -> dict:
    rows = run(sql, params)
    return rows[0] if rows else {}


def execute(sql: str, params: dict | None = None) -> int:
    with get_engine().begin() as conn:
        return conn.execute(text(sql), params or {}).rowcount


_log_lock = threading.Lock()


def log_timing(path: str, status: int, ms: float):
    """Tiempos de respuesta por endpoint (evidencia de rendimiento)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file = LOG_DIR / "response_times.csv"
    with _log_lock:
        new = not file.exists()
        with file.open("a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["timestamp", "path", "status", "ms"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), path, status, round(ms)])


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    response.headers["X-Response-ms"] = f"{ms:.0f}"
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/docs"):
        log_timing(request.url.path, response.status_code, ms)
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Error no controlado en %s", request.url.path)   # detalle solo en el servidor
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


# ---------- autenticacion ----------
class LoginIn(BaseModel):
    username: str
    password: str


def current_user(authorization: str | None = Header(default=None)) -> str:
    if authorization and authorization.startswith("Bearer "):
        user = verify_token(authorization[7:], SECRET)
        if user:
            return user
    raise HTTPException(status_code=401, detail="No autenticado")


@app.post("/api/login")
def login(body: LoginIn):
    if not (same_text(body.username, DASH_USER) and same_text(body.password, DASH_PASSWORD)):
        time.sleep(0.7)   # frena la fuerza bruta
        raise HTTPException(status_code=401, detail="Usuario o contrasena incorrectos")
    return {"token": make_token(body.username, SECRET), "user": body.username}


@app.get("/api/health")
def health():
    try:
        run("SELECT 1 AS ok")
        return {"status": "ok"}
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


# ---------- filtros comunes ----------
def filters(date_from: date | None = None, date_to: date | None = None,
            category: str | None = Query(None, max_length=100),
            product_group: str | None = Query(None, max_length=100),
            territory: str | None = Query(None, max_length=100)) -> dict:
    return {"date_from": date_from, "date_to": date_to, "category": category,
            "product_group": product_group, "territory": territory}


# ---------- endpoints de negocio (datos HISTORICOS del Data Warehouse) ----------
@app.get("/api/meta")
def meta(user: str = Depends(current_user)):
    rng = one("""SELECT MIN(d.[Date]) AS date_min, MAX(d.[Date]) AS date_max
                 FROM dw.FactSales f JOIN dw.DimDate d ON d.DateKey = f.DateKey""")
    last = one("""SELECT TOP 1 end_time FROM audit.etl_run
                  WHERE pipeline_name = 'load_fact_sales' AND status = 'SUCCESS'
                  ORDER BY end_time DESC""")
    return {
        "categories": [r["v"] for r in run(
            "SELECT DISTINCT CustomerCategory AS v FROM dw.DimCustomer WHERE CustomerKey <> -1 ORDER BY 1")],
        "product_groups": [r["v"] for r in run(
            "SELECT DISTINCT ProductGroup AS v FROM dw.DimProduct WHERE ProductKey <> -1 ORDER BY 1")],
        "territories": [r["v"] for r in run(
            "SELECT DISTINCT SalesTerritory AS v FROM dw.DimCustomer WHERE CustomerKey <> -1 ORDER BY 1")],
        "date_min": rng.get("date_min"), "date_max": rng.get("date_max"),
        "last_update": last.get("end_time"),
    }


@app.get("/api/kpis")
def kpis(f: dict = Depends(filters), user: str = Depends(current_user)):
    current = q.shape_kpis(one(*q.kpi_query(f)))
    result = {"current": current, "previous": None, "delta_pct": {}, "previous_period": None}
    if f["date_from"] and f["date_to"]:
        pf, pt = q.previous_period(f["date_from"], f["date_to"])
        previous = q.shape_kpis(one(*q.kpi_query({**f, "date_from": pf, "date_to": pt})))
        result["previous"] = previous
        result["previous_period"] = {"date_from": pf, "date_to": pt}
        result["delta_pct"] = {k: q.pct_change(current[k], previous[k]) for k in current}
    return result


@app.get("/api/trend")
def trend(f: dict = Depends(filters), user: str = Depends(current_user)):
    return run(*q.trend_query(f))


@app.get("/api/sales/by/{dimension}")
def sales_by(dimension: str, f: dict = Depends(filters), limit: int = Query(10, ge=1, le=50),
             user: str = Depends(current_user)):
    if dimension not in q.DIMENSIONS:
        raise HTTPException(status_code=404, detail="Dimension no disponible")
    return run(*q.dimension_query(dimension, f, limit))


@app.get("/api/sales/detail")
def sales_detail(f: dict = Depends(filters), page: int = Query(1, ge=1),
                 page_size: int = Query(15, ge=1, le=100), user: str = Depends(current_user)):
    total = one(*q.count_query(f)).get("total", 0)
    rows = run(*q.detail_query(f, page, page_size))
    return {"total": total, "page": page, "page_size": page_size, "rows": rows}


# ---------- vista operativa (monitoreo del ETL) ----------
@app.get("/api/ops/etl")
def ops_etl(user: str = Depends(current_user)):
    runs = run("""SELECT TOP 25 start_time, end_time, pipeline_name, target_object, status,
                         rows_read, rows_inserted, rows_updated, rows_rejected,
                         DATEDIFF(SECOND, start_time, end_time) AS seconds,
                         LEFT(error_detail, 300) AS error_detail
                  FROM audit.etl_run ORDER BY start_time DESC""")
    summary = one("""SELECT COUNT(*) AS total_runs,
                            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed_runs,
                            MAX(CASE WHEN status = 'SUCCESS' THEN end_time END) AS last_success
                     FROM audit.etl_run""")
    marks = run("SELECT pipeline_name, last_watermark, updated_at FROM audit.etl_watermark ORDER BY pipeline_name")
    return {"summary": summary, "runs": runs, "watermarks": marks}


# ---------- prediccion (Machine Learning) ----------
@app.get("/api/forecast")
def sales_forecast(user: str = Depends(current_user)):
    """PREDICCION (no es dato historico). Devuelve el modelo activo, sus metricas y el pronostico."""
    model = one("""SELECT TOP 1 model_version, algorithm, trained_at, trained_through, n_months,
                          harmonics, alpha, metrics_json
                   FROM ml.model_registry WHERE is_active = 1 ORDER BY trained_at DESC""")
    if not model:
        return {"model": None}
    detail = json.loads(model.pop("metrics_json") or "{}")
    fc = run("""SELECT horizon_months, target_month, predicted_net_sales, lower_80, upper_80, prediction_date
                FROM ml.forecast_sales
                WHERE model_version = :v AND prediction_date =
                      (SELECT MAX(prediction_date) FROM ml.forecast_sales WHERE model_version = :v)
                ORDER BY target_month""", {"v": model["model_version"]})
    hist = run("""SELECT TOP 24 ym, net_sales FROM dw.vw_monthly_sales
                  WHERE month_start <= :thr ORDER BY month_start DESC""", {"thr": model["trained_through"]})
    return {"model": model, "is_prediction": True, "history": list(reversed(hist)), "forecast": fc,
            "validation": detail.get("validation"), "test": detail.get("test"),
            "splits": detail.get("splits"), "verdict": detail.get("verdict"),
            "best_baseline": detail.get("best_baseline")}


# ---------- alertas ----------
ALERT_STATUSES = {"NUEVA", "ATENDIDA", "DESCARTADA", "RESUELTA"}


class StatusIn(BaseModel):
    status: str


@app.get("/api/alerts")
def list_alerts(status: str | None = Query(None, max_length=12), limit: int = Query(50, ge=1, le=200),
                user: str = Depends(current_user)):
    if status and status not in ALERT_STATUSES:
        raise HTTPException(status_code=400, detail="Estado no valido")
    where = "WHERE status = :status" if status else ""
    params = {"n": limit, **({"status": status} if status else {})}
    try:
        rows = run(f"""SELECT TOP (:n) alert_id, created_at, source_type, severity, indicator, entity, period_label,
                              observed_value, reference_value, threshold_pct, change_pct, is_simulated, status
                       FROM alerts.alert {where} ORDER BY created_at DESC, alert_id DESC""", params)
        counts = {r["status"]: r["n"] for r in run("SELECT status, COUNT(*) AS n FROM alerts.alert GROUP BY status")}
    except Exception:  # noqa: BLE001   (modulo de alertas aun no creado)
        log.exception("alerts no disponible")
        return {"alerts": [], "counts": {}, "setup_needed": True}
    return {"alerts": rows, "counts": counts, "setup_needed": False}


@app.get("/api/alerts/{alert_id}")
def alert_detail(alert_id: int, user: str = Depends(current_user)):
    alert = one("SELECT * FROM alerts.alert WHERE alert_id = :i", {"i": alert_id})
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    deliveries = run("""SELECT channel, status, attempts, last_attempt_at, error_detail
                        FROM alerts.delivery WHERE alert_id = :i ORDER BY channel""", {"i": alert_id})
    return {"alert": alert, "deliveries": deliveries}


@app.patch("/api/alerts/{alert_id}/status")
def alert_set_status(alert_id: int, body: StatusIn, user: str = Depends(current_user)):
    if body.status not in ALERT_STATUSES:
        raise HTTPException(status_code=400, detail="Estado no valido")
    changed = execute("""UPDATE alerts.alert SET status = :s, updated_at = SYSDATETIME(), updated_by = :u
                         WHERE alert_id = :i""", {"s": body.status, "u": user, "i": alert_id})
    if not changed:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    return {"alert_id": alert_id, "status": body.status}


# ---------- asistente de IA generativa ----------
class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


_rate: dict = defaultdict(deque)
_rate_lock = threading.Lock()


def check_rate(user: str, limit: int = 20, window: int = 60):
    """Maximo 'limit' preguntas por usuario cada 'window' segundos."""
    now = time.time()
    with _rate_lock:
        dq = _rate[user]
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            raise HTTPException(status_code=429, detail="Demasiadas preguntas seguidas. Espera un momento.")
        dq.append(now)


def log_assistant(user: str, question: str, res: dict, ms: float):
    """Registro de uso: usuario, pregunta (acotada), estado y herramientas. No guarda resultados."""
    try:
        execute("""INSERT INTO ai.assistant_log (username, question, status, tools, provider, latency_ms, unverified_count)
                   VALUES (:u, :q, :s, :t, :p, :l, :n)""",
                {"u": user[:100], "q": question[:500], "s": res["status"], "t": ",".join(res.get("tools", []))[:200],
                 "p": (res.get("provider") or "")[:60], "l": int(ms), "n": len(res.get("unverified", []))})
    except Exception:  # noqa: BLE001   (el registro nunca debe romper la respuesta)
        log.exception("No se pudo registrar la consulta del asistente")


@app.get("/api/assistant/info")
def assistant_info(user: str = Depends(current_user)):
    return {"provider": PROVIDER.name if PROVIDER else "reglas (sin modelo de lenguaje)",
            "external": bool(PROVIDER and PROVIDER.external)}


@app.post("/api/assistant")
def assistant(body: AskIn, user: str = Depends(current_user)):
    check_rate(user)
    t0 = time.perf_counter()
    try:
        res = answer_question(body.question, {"db": SqlDb(get_engine())}, PROVIDER)
    except Exception:  # noqa: BLE001
        log.exception("Error en el asistente")
        res = {"status": "ERROR", "answer": "Ocurrió un error al consultar los datos. Intenta de nuevo.",
               "facts": [], "assumptions": [], "warnings": [], "sources": [], "unverified": [], "tools": [],
               "is_prediction": False, "provider": None, "interpretation_by": None}
    log_assistant(user, body.question, res, (time.perf_counter() - t0) * 1000)
    return res


# El frontend se sirve desde la misma API (mismo origen: no hace falta CORS). Debe ir al final.
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
