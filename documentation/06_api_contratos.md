# 6. API y contratos de datos

Base: `http://localhost:8000`. Documentación interactiva generada por FastAPI: `/api/docs`. Todas las rutas (salvo `login` y `health`) requieren `Authorization: Bearer <token>`.

## Convenciones
- **Filtros comunes** (opcionales): `date_from`, `date_to` (`YYYY-MM-DD`), `category`, `product_group`, `territory` (texto exacto, máx. 100).
- Todo el SQL está **parametrizado**; los nombres de columna dinámicos salen de listas blancas.
- Cada respuesta incluye la cabecera `X-Response-ms`; los tiempos se registran en `backend/logs/response_times.csv`.
- Errores: `400` parámetro inválido · `401` sin sesión/expirada · `404` no existe · `422` validación · `429` demasiadas preguntas · `500` error interno (detalle solo en el servidor) · `503` base de datos no disponible.

## Endpoints
| Método y ruta | Descripción | Respuesta (resumen) |
|---|---|---|
| `POST /api/login` | Cuerpo `{username, password}` | `{token, user}` (token firmado, 8 h) |
| `GET /api/health` | Comprueba la conexión a la base | `{status: "ok"}` |
| `GET /api/meta` | Valores de filtros y rango de fechas | `{categories[], product_groups[], territories[], date_min, date_max, last_update}` |
| `GET /api/kpis` + filtros | 5 KPIs y variación vs. periodo anterior de igual duración (si hay `date_from` y `date_to`) | `{current{net_sales, orders, units, customers, avg_ticket}, previous, delta_pct{}, previous_period}` |
| `GET /api/trend` + filtros | Ventas por mes | `[{ym, sales, units}]` |
| `GET /api/sales/by/{dimension}` + filtros, `limit` (1–50) | `dimension` ∈ `product_group`, `customer_category`, `territory`, `customer` | `[{label, sales, units}]` |
| `GET /api/sales/detail` + filtros, `page`, `page_size` (≤ 100) | Líneas de venta paginadas | `{total, page, page_size, rows[{order_id, order_line_id, order_date, customer, category, product, product_group, quantity, unit_price, net_amount}]}` |
| `GET /api/forecast` | **Predicción** (no histórico) del modelo activo | `{model, is_prediction: true, history[], forecast[], validation, test, splits, verdict, best_baseline}` |
| `GET /api/alerts` + `status`, `limit` | Lista de alertas y conteo por estado | `{alerts[], counts{}, setup_needed}` |
| `GET /api/alerts/{id}` | Detalle y entregas | `{alert{…}, deliveries[]}` |
| `PATCH /api/alerts/{id}/status` | Cuerpo `{status}` ∈ NUEVA, ATENDIDA, DESCARTADA, RESUELTA | `{alert_id, status}` |
| `GET /api/assistant/info` | Motor del asistente | `{provider, external}` |
| `POST /api/assistant` | Cuerpo `{question}` (1–500 caracteres; 20/min por usuario) | ver `08_ia_generativa.md` |
| `GET /api/ops/etl` | Vista operativa | `{summary{total_runs, failed_runs, last_success}, runs[], watermarks[]}` |

## Contrato de datos del dashboard
| Elemento | Fuente | Definición |
|---|---|---|
| Ventas netas | `SUM(dw.FactSales.NetAmount)` | `Quantity × UnitPrice`, sin impuestos |
| Órdenes | `COUNT(DISTINCT OrderID)` | |
| Unidades | `SUM(Quantity)` | |
| Ticket promedio | Ventas netas ÷ órdenes | ratio, se recalcula |
| Clientes activos | `COUNT(DISTINCT CustomerID)` | clientes con compras en el periodo |
| Periodo anterior | misma duración, terminando el día antes de `date_from` | |

Cada KPI tiene responsable lógico (equipo de ventas), granularidad (línea de orden agregada), filtros (fecha, categoría de cliente, grupo de producto, territorio) y fuente (`dw.FactSales`). Se **valida** contra consultas SQL independientes sobre el origen (ver `10_pruebas.md`).

## Seguridad de la API
- Usuario de base de datos `api_reader`: lectura sobre `dw`, `ml`, `alerts` y `audit.etl_run/etl_watermark`; `UPDATE` solo de `status, updated_at, updated_by` en `alerts.alert`; `INSERT` en `ai.assistant_log`.
- Sin credenciales en el frontend; el token se guarda en `sessionStorage` y expira.
- El navegador nunca se conecta a SQL Server.
