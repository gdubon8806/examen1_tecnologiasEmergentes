-- DEMO DE RECUPERACION: provoca una falla controlada en la carga de FactSales. Ejecutar en SSMS.
USE AnalyticsDW;
GO
-- PASO A (ANTES de correr el pipeline): crea una regla que las filas nuevas incumplen
ALTER TABLE dw.FactSales WITH NOCHECK ADD CONSTRAINT CK_demo_falla CHECK (Quantity < 5);
GO

-- PASO B (DESPUES de ver el pipeline fallar y de mostrar audit.etl_run): quita la regla
-- y vuelve a correr el pipeline. Debe terminar bien, sin duplicados.
-- ALTER TABLE dw.FactSales DROP CONSTRAINT CK_demo_falla;
GO
