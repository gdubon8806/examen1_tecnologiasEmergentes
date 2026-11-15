-- RECONCILIACION: comparar origen vs staging vs Data Warehouse (ejecutar en SSMS)
USE AnalyticsDW;
GO

-- 1) Conteo de filas por capa (lineas de orden)
SELECT 'origen (WideWorldImporters)' AS capa, COUNT(*) AS filas FROM WideWorldImporters.Sales.OrderLines
UNION ALL SELECT 'raw',        COUNT(*) FROM raw.order_lines
UNION ALL SELECT 'clean',      COUNT(*) FROM clean.order_lines
UNION ALL SELECT 'cuarentena', COUNT(*) FROM audit.quarantine WHERE source_object = 'raw.order_lines'
UNION ALL SELECT 'dw.FactSales', COUNT(*) FROM dw.FactSales;

-- 2) Regla: origen = DW + cuarentena  (diferencia debe ser 0)
SELECT (SELECT COUNT(*) FROM WideWorldImporters.Sales.OrderLines) AS origen,
       (SELECT COUNT(*) FROM dw.FactSales)                        AS dw,
       (SELECT COUNT(*) FROM audit.quarantine WHERE source_object = 'raw.order_lines') AS cuarentena,
       (SELECT COUNT(*) FROM WideWorldImporters.Sales.OrderLines)
         - (SELECT COUNT(*) FROM dw.FactSales)
         - (SELECT COUNT(*) FROM audit.quarantine WHERE source_object = 'raw.order_lines') AS diferencia;

-- 3) Ventas netas totales: origen vs DW
SELECT 'origen' AS capa, SUM(CAST(Quantity AS DECIMAL(18,2)) * UnitPrice) AS ventas_netas
FROM WideWorldImporters.Sales.OrderLines
UNION ALL SELECT 'dw', SUM(NetAmount) FROM dw.FactSales;

-- 4) Ventas netas por ano: origen vs DW
WITH s AS (
    SELECT YEAR(o.OrderDate) AS anio, SUM(CAST(ol.Quantity AS DECIMAL(18,2)) * ol.UnitPrice) AS origen
    FROM WideWorldImporters.Sales.OrderLines ol
    JOIN WideWorldImporters.Sales.Orders o ON o.OrderID = ol.OrderID
    GROUP BY YEAR(o.OrderDate)),
d AS (
    SELECT dd.[Year] AS anio, SUM(f.NetAmount) AS dw
    FROM dw.FactSales f JOIN dw.DimDate dd ON dd.DateKey = f.DateKey
    GROUP BY dd.[Year])
SELECT COALESCE(s.anio, d.anio) AS anio, s.origen, d.dw, s.origen - d.dw AS diferencia
FROM s FULL JOIN d ON s.anio = d.anio
ORDER BY 1;

-- 5) Hechos con dimension desconocida (idealmente 0)
SELECT SUM(CASE WHEN CustomerKey = -1 THEN 1 ELSE 0 END) AS sin_cliente,
       SUM(CASE WHEN ProductKey  = -1 THEN 1 ELSE 0 END) AS sin_producto
FROM dw.FactSales;
GO
