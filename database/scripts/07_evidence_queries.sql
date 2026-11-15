-- CONSULTAS DE EVIDENCIA (ejecutar en SSMS despues del pipeline)
USE AnalyticsDW;
GO
-- 1) Ultimas ejecuciones (estado, conteos, watermark, errores)
SELECT TOP 30 start_time, pipeline_name, target_object, status, rows_read, rows_inserted,
       rows_updated, rows_rejected, watermark_start, watermark_end, error_detail
FROM audit.etl_run ORDER BY start_time DESC;

-- 2) Watermarks vigentes
SELECT * FROM audit.etl_watermark;

-- 3) SCD Tipo 2: historial del cliente que cambio de categoria
SELECT CustomerKey, CustomerID, CustomerName, CustomerCategory, ValidFrom, ValidTo, IsCurrent
FROM dw.DimCustomer
WHERE CustomerID IN (SELECT CustomerID FROM dw.DimCustomer GROUP BY CustomerID HAVING COUNT(*) > 1)
ORDER BY CustomerID, ValidFrom;

-- 4) Ventas de ese cliente por version: lo viejo conserva la categoria vieja, lo nuevo la nueva
SELECT dc.CustomerKey, dc.CustomerCategory, dc.IsCurrent, COUNT(*) AS lineas, SUM(f.NetAmount) AS ventas_netas
FROM dw.FactSales f JOIN dw.DimCustomer dc ON dc.CustomerKey = f.CustomerKey
WHERE dc.CustomerID IN (SELECT CustomerID FROM dw.DimCustomer GROUP BY CustomerID HAVING COUNT(*) > 1)
GROUP BY dc.CustomerKey, dc.CustomerCategory, dc.IsCurrent ORDER BY dc.CustomerKey;

-- 5) Fila nueva y fila modificada en el DW
SELECT TOP 3 OrderLineID, OrderID, DateKey, Quantity, NetAmount, LoadedAt, UpdatedAt
FROM dw.FactSales ORDER BY OrderLineID DESC;
SELECT OrderLineID, Quantity, NetAmount, LoadedAt, UpdatedAt FROM dw.FactSales WHERE OrderLineID = 1;

-- 6) No hay llaves de negocio duplicadas en el hecho
SELECT COUNT(*) AS filas, COUNT(DISTINCT OrderLineID) AS lineas_distintas FROM dw.FactSales;
GO
