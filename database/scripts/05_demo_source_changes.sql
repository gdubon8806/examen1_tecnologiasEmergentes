-- DEMO: simula actividad nueva en el sistema de ventas (ORIGEN). Ejecutar en SSMS.
-- Los datos creados quedan marcados como DEMO / simulados (la guia pide identificarlos).
USE WideWorldImporters;
GO
DECLARE @cust INT = (SELECT TOP 1 CustomerID FROM Sales.Orders ORDER BY OrderID);

-- 1) Orden NUEVA con una linea (fecha dentro del rango del calendario del DW)
DECLARE @t TABLE (OrderID INT);
INSERT INTO Sales.Orders (CustomerID, SalespersonPersonID, ContactPersonID, OrderDate,
                          ExpectedDeliveryDate, IsUndersupplyBackordered, Comments, LastEditedBy)
OUTPUT inserted.OrderID INTO @t
SELECT TOP 1 CustomerID, SalespersonPersonID, ContactPersonID, '2016-06-01', '2016-06-02', 0,
       N'DEMO simulada - carga incremental', LastEditedBy
FROM Sales.Orders WHERE CustomerID = @cust ORDER BY OrderID;

INSERT INTO Sales.OrderLines (OrderID, StockItemID, Description, PackageTypeID, Quantity,
                              UnitPrice, TaxRate, PickedQuantity, LastEditedBy)
SELECT TOP 1 (SELECT OrderID FROM @t), StockItemID, N'DEMO simulada - carga incremental',
       PackageTypeID, 10, UnitPrice, TaxRate, 0, LastEditedBy
FROM Sales.OrderLines ORDER BY OrderLineID;

-- 2) Linea EXISTENTE modificada (cambia la cantidad)
UPDATE Sales.OrderLines SET Quantity = Quantity + 5, LastEditedWhen = SYSUTCDATETIME()
WHERE OrderLineID = 1;

-- 3) Cambio de categoria de un cliente (para el SCD Tipo 2): el mismo cliente de la orden nueva
UPDATE Sales.Customers SET CustomerCategoryID = CASE WHEN CustomerCategoryID = 4 THEN 5 ELSE 4 END
WHERE CustomerID = @cust;

SELECT @cust AS cliente_modificado, (SELECT OrderID FROM @t) AS orden_nueva;
GO
