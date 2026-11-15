-- =====================================================================
-- MODELO DIMENSIONAL (esquema estrella) - proceso de negocio: VENTAS
-- GRANO de FactSales: una fila por LINEA DE ORDEN (Sales.OrderLines)
-- Lo ejecuta etl/load_dw.py (separa los lotes por GO). No lo corras con sqlcmd.
-- =====================================================================

-- ---------- DimDate ----------
IF OBJECT_ID('dw.DimDate') IS NULL
CREATE TABLE dw.DimDate (
    DateKey    INT          NOT NULL CONSTRAINT PK_DimDate PRIMARY KEY,   -- yyyymmdd
    [Date]     DATE         NOT NULL CONSTRAINT UQ_DimDate_Date UNIQUE,
    [Day]      TINYINT      NOT NULL,
    DayName    NVARCHAR(20) NOT NULL,
    [Month]    TINYINT      NOT NULL,
    MonthName  NVARCHAR(20) NOT NULL,
    [Quarter]  TINYINT      NOT NULL,
    [Year]     SMALLINT     NOT NULL,
    YearMonth  CHAR(7)      NOT NULL,
    IsWeekend  BIT          NOT NULL
);
GO

-- ---------- DimProduct (SCD Tipo 1: se sobrescribe) ----------
IF OBJECT_ID('dw.DimProduct') IS NULL
BEGIN
    CREATE TABLE dw.DimProduct (
        ProductKey   INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DimProduct PRIMARY KEY,  -- clave sustituta
        StockItemID  INT            NOT NULL,                                          -- clave de negocio
        ProductName  NVARCHAR(200)  NOT NULL,
        Brand        NVARCHAR(100)  NOT NULL,
        Size         NVARCHAR(50)   NOT NULL,
        ProductGroup NVARCHAR(100)  NOT NULL,
        ListPrice    DECIMAL(18,2)  NOT NULL,
        UpdatedAt    DATETIME2(0)   NOT NULL CONSTRAINT DF_DimProduct_Upd DEFAULT SYSDATETIME()
    );
    CREATE UNIQUE INDEX UX_DimProduct_StockItemID ON dw.DimProduct (StockItemID);
    SET IDENTITY_INSERT dw.DimProduct ON;
    INSERT INTO dw.DimProduct (ProductKey, StockItemID, ProductName, Brand, Size, ProductGroup, ListPrice)
    VALUES (-1, -1, N'Desconocido', N'Desconocido', N'Desconocido', N'Desconocido', 0);
    SET IDENTITY_INSERT dw.DimProduct OFF;
END
GO

-- ---------- DimCustomer (SCD Tipo 2: se conserva el historial) ----------
IF OBJECT_ID('dw.DimCustomer') IS NULL
BEGIN
    CREATE TABLE dw.DimCustomer (
        CustomerKey      INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DimCustomer PRIMARY KEY,  -- clave sustituta
        CustomerID       INT            NOT NULL,                                           -- clave de negocio
        CustomerName     NVARCHAR(200)  NOT NULL,          -- Tipo 1 (se sobrescribe)
        CustomerCategory NVARCHAR(100)  NOT NULL,          -- Tipo 2 (crea version nueva)
        City             NVARCHAR(100)  NOT NULL,          -- Tipo 2
        StateProvince    NVARCHAR(100)  NOT NULL,          -- Tipo 2
        SalesTerritory   NVARCHAR(100)  NOT NULL,          -- Tipo 2
        Country          NVARCHAR(100)  NOT NULL,          -- Tipo 2
        ValidFrom        DATETIME2(0)   NOT NULL,
        ValidTo          DATETIME2(0)   NOT NULL,
        IsCurrent        BIT            NOT NULL,
        CreatedAt        DATETIME2(0)   NOT NULL CONSTRAINT DF_DimCustomer_Cre DEFAULT SYSDATETIME()
    );
    -- Solo puede haber UNA version vigente por cliente
    CREATE UNIQUE INDEX UX_DimCustomer_Current ON dw.DimCustomer (CustomerID) WHERE IsCurrent = 1;
    CREATE INDEX IX_DimCustomer_CustomerID ON dw.DimCustomer (CustomerID);
    SET IDENTITY_INSERT dw.DimCustomer ON;
    INSERT INTO dw.DimCustomer (CustomerKey, CustomerID, CustomerName, CustomerCategory, City,
                                StateProvince, SalesTerritory, Country, ValidFrom, ValidTo, IsCurrent)
    VALUES (-1, -1, N'Desconocido', N'Desconocido', N'Desconocido', N'Desconocido',
            N'Desconocido', N'Desconocido', '1900-01-01', '9999-12-31', 1);
    SET IDENTITY_INSERT dw.DimCustomer OFF;
END
GO

-- ---------- FactSales ----------
IF OBJECT_ID('dw.FactSales') IS NULL
BEGIN
    CREATE TABLE dw.FactSales (
        OrderLineID          INT           NOT NULL CONSTRAINT PK_FactSales PRIMARY KEY,  -- llave degenerada (1 fila = 1 linea)
        OrderID              INT           NOT NULL,                                      -- dimension degenerada
        DateKey              INT           NOT NULL CONSTRAINT FK_FactSales_Date     REFERENCES dw.DimDate (DateKey),
        CustomerKey          INT           NOT NULL CONSTRAINT FK_FactSales_Customer REFERENCES dw.DimCustomer (CustomerKey),
        ProductKey           INT           NOT NULL CONSTRAINT FK_FactSales_Product  REFERENCES dw.DimProduct (ProductKey),
        Quantity             INT           NOT NULL,   -- aditiva
        UnitPrice            DECIMAL(18,2) NOT NULL,   -- NO aditiva (no se suma; se promedia o se recalcula)
        TaxRate              DECIMAL(5,2)  NOT NULL,   -- NO aditiva
        NetAmount            DECIMAL(18,2) NOT NULL,   -- aditiva: Quantity * UnitPrice (ventas netas, sin impuesto)
        TaxAmount            DECIMAL(18,2) NOT NULL,   -- aditiva
        GrossAmount          DECIMAL(18,2) NOT NULL,   -- aditiva: NetAmount + TaxAmount
        IsPriceOutlier       BIT           NOT NULL,
        SourceLastEditedWhen DATETIME2(7)  NOT NULL,   -- sirve de watermark
        LoadedAt             DATETIME2(0)  NOT NULL CONSTRAINT DF_FactSales_Loaded  DEFAULT SYSDATETIME(),
        UpdatedAt            DATETIME2(0)  NULL
    );
    CREATE INDEX IX_FactSales_Date     ON dw.FactSales (DateKey);
    CREATE INDEX IX_FactSales_Customer ON dw.FactSales (CustomerKey);
    CREATE INDEX IX_FactSales_Product  ON dw.FactSales (ProductKey);
END
GO

-- =====================================================================
-- PROCEDIMIENTOS DE CARGA (cada uno devuelve: inserted, updated, watermark_start, watermark_end)
-- =====================================================================
CREATE OR ALTER PROCEDURE dw.usp_load_dim_date
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @start DATE, @end DATE, @ins INT = 0;
    SELECT @start = DATEFROMPARTS(YEAR(MIN(OrderDate)), 1, 1),
           @end   = DATEFROMPARTS(YEAR(MAX(OrderDate)), 12, 31)
    FROM clean.orders;

    IF @start IS NOT NULL
    BEGIN
        ;WITH d AS (
            SELECT @start AS dt
            UNION ALL
            SELECT DATEADD(DAY, 1, dt) FROM d WHERE dt < @end
        )
        INSERT INTO dw.DimDate (DateKey, [Date], [Day], DayName, [Month], MonthName,
                                [Quarter], [Year], YearMonth, IsWeekend)
        SELECT YEAR(dt) * 10000 + MONTH(dt) * 100 + DAY(dt), dt, DAY(dt),
               DATENAME(WEEKDAY, dt), MONTH(dt), DATENAME(MONTH, dt),
               DATEPART(QUARTER, dt), YEAR(dt),
               CONCAT(YEAR(dt), '-', RIGHT('0' + CAST(MONTH(dt) AS VARCHAR(2)), 2)),
               CASE WHEN DATEDIFF(DAY, '19000101', dt) % 7 IN (5, 6) THEN 1 ELSE 0 END
        FROM d
        WHERE NOT EXISTS (SELECT 1 FROM dw.DimDate x WHERE x.[Date] = d.dt)
        OPTION (MAXRECURSION 0);
        SET @ins = @@ROWCOUNT;
    END

    SELECT @ins AS inserted, 0 AS updated, CAST(NULL AS DATETIME2(7)) AS watermark_start,
           CAST(NULL AS DATETIME2(7)) AS watermark_end;
END
GO

CREATE OR ALTER PROCEDURE dw.usp_load_dim_product
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @ins INT = 0, @upd INT = 0;

    -- Un producto puede estar en varios grupos: se toma UNO (el de menor ID) para
    -- que el join no multiplique las ventas.
    ;WITH pg AS (
        SELECT StockItemID, MIN(StockGroupID) AS StockGroupID
        FROM clean.stock_item_stock_groups
        GROUP BY StockItemID
    )
    SELECT si.StockItemID, si.StockItemName,
           ISNULL(si.Brand, N'No aplica') AS Brand,
           ISNULL(si.Size,  N'No aplica') AS Size,
           ISNULL(sg.StockGroupName, N'Desconocido') AS ProductGroup,
           CAST(si.UnitPrice AS DECIMAL(18,2)) AS ListPrice
    INTO #p
    FROM clean.stock_items si
    LEFT JOIN pg ON pg.StockItemID = si.StockItemID
    LEFT JOIN clean.stock_groups sg ON sg.StockGroupID = pg.StockGroupID;

    UPDATE d
       SET d.ProductName = p.StockItemName, d.Brand = p.Brand, d.Size = p.Size,
           d.ProductGroup = p.ProductGroup, d.ListPrice = p.ListPrice, d.UpdatedAt = SYSDATETIME()
    FROM dw.DimProduct d
    JOIN #p p ON p.StockItemID = d.StockItemID
    WHERE d.ProductName <> p.StockItemName OR d.Brand <> p.Brand OR d.Size <> p.Size
       OR d.ProductGroup <> p.ProductGroup OR d.ListPrice <> p.ListPrice;
    SET @upd = @@ROWCOUNT;

    INSERT INTO dw.DimProduct (StockItemID, ProductName, Brand, Size, ProductGroup, ListPrice)
    SELECT p.StockItemID, p.StockItemName, p.Brand, p.Size, p.ProductGroup, p.ListPrice
    FROM #p p
    WHERE NOT EXISTS (SELECT 1 FROM dw.DimProduct d WHERE d.StockItemID = p.StockItemID);
    SET @ins = @@ROWCOUNT;

    SELECT @ins AS inserted, @upd AS updated, CAST(NULL AS DATETIME2(7)) AS watermark_start,
           CAST(NULL AS DATETIME2(7)) AS watermark_end;
END
GO

CREATE OR ALTER PROCEDURE dw.usp_load_dim_customer
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @ins INT = 0, @upd INT = 0, @now DATETIME2(0) = SYSDATETIME();

    SELECT c.CustomerID, c.CustomerName,
           ISNULL(cc.CustomerCategoryName, N'Desconocido') AS CustomerCategory,
           ISNULL(ci.CityName, N'Desconocido')             AS City,
           ISNULL(sp.StateProvinceName, N'Desconocido')    AS StateProvince,
           ISNULL(sp.SalesTerritory, N'Desconocido')       AS SalesTerritory,
           ISNULL(co.CountryName, N'Desconocido')          AS Country
    INTO #c
    FROM clean.customers c
    LEFT JOIN clean.customer_categories cc ON cc.CustomerCategoryID = c.CustomerCategoryID
    LEFT JOIN clean.cities ci              ON ci.CityID = c.DeliveryCityID
    LEFT JOIN clean.state_provinces sp     ON sp.StateProvinceID = ci.StateProvinceID
    LEFT JOIN clean.countries co           ON co.CountryID = sp.CountryID;

    -- 1) Tipo 1: el nombre se sobrescribe en todas las versiones
    UPDATE d SET d.CustomerName = c.CustomerName
    FROM dw.DimCustomer d
    JOIN #c c ON c.CustomerID = d.CustomerID
    WHERE d.CustomerName <> c.CustomerName;
    SET @upd = @@ROWCOUNT;

    -- 2) Clientes nuevos
    INSERT INTO dw.DimCustomer (CustomerID, CustomerName, CustomerCategory, City, StateProvince,
                                SalesTerritory, Country, ValidFrom, ValidTo, IsCurrent)
    SELECT c.CustomerID, c.CustomerName, c.CustomerCategory, c.City, c.StateProvince,
           c.SalesTerritory, c.Country, '1900-01-01', '9999-12-31', 1
    FROM #c c
    WHERE NOT EXISTS (SELECT 1 FROM dw.DimCustomer d WHERE d.CustomerID = c.CustomerID);
    SET @ins = @@ROWCOUNT;

    -- 3) Tipo 2: atributos que cambiaron -> cerrar version vigente y crear una nueva
    SELECT d.CustomerKey, c.CustomerID, c.CustomerName, c.CustomerCategory, c.City,
           c.StateProvince, c.SalesTerritory, c.Country
    INTO #chg
    FROM dw.DimCustomer d
    JOIN #c c ON c.CustomerID = d.CustomerID
    WHERE d.IsCurrent = 1
      AND (d.CustomerCategory <> c.CustomerCategory OR d.City <> c.City
           OR d.StateProvince <> c.StateProvince OR d.SalesTerritory <> c.SalesTerritory
           OR d.Country <> c.Country);

    UPDATE d SET d.ValidTo = @now, d.IsCurrent = 0
    FROM dw.DimCustomer d
    JOIN #chg x ON x.CustomerKey = d.CustomerKey;
    SET @upd = @upd + @@ROWCOUNT;

    INSERT INTO dw.DimCustomer (CustomerID, CustomerName, CustomerCategory, City, StateProvince,
                                SalesTerritory, Country, ValidFrom, ValidTo, IsCurrent)
    SELECT x.CustomerID, x.CustomerName, x.CustomerCategory, x.City, x.StateProvince,
           x.SalesTerritory, x.Country, @now, '9999-12-31', 1
    FROM #chg x;
    SET @ins = @ins + @@ROWCOUNT;

    SELECT @ins AS inserted, @upd AS updated, CAST(NULL AS DATETIME2(7)) AS watermark_start,
           CAST(NULL AS DATETIME2(7)) AS watermark_end;
END
GO

CREATE OR ALTER PROCEDURE dw.usp_load_fact_sales
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @wm_prev DATETIME2(7), @from DATETIME2(7), @wm_end DATETIME2(7),
            @ins INT = 0, @upd INT = 0;

    SELECT @wm_prev = last_watermark FROM audit.etl_watermark WHERE pipeline_name = 'load_fact_sales';
    -- Carga inicial: desde el principio. Incremental: desde el watermark - 1 dia (ventana de
    -- solapamiento para registros tardios). Re-procesar filas es seguro porque se hace upsert.
    SET @from = CASE WHEN @wm_prev IS NULL THEN CAST('1900-01-01' AS DATETIME2(7))
                     ELSE DATEADD(DAY, -1, @wm_prev) END;
    SELECT @wm_end = MAX(LastEditedWhen) FROM clean.order_lines;

    -- Resolver claves de dimension ANTES de insertar hechos (cliente = version vigente)
    SELECT ol.OrderLineID, ol.OrderID,
           YEAR(o.OrderDate) * 10000 + MONTH(o.OrderDate) * 100 + DAY(o.OrderDate) AS DateKey,
           ISNULL(dc.CustomerKey, -1) AS CustomerKey,
           ISNULL(dp.ProductKey, -1)  AS ProductKey,
           CAST(ol.Quantity AS INT)                          AS Quantity,
           CAST(ol.UnitPrice AS DECIMAL(18,2))               AS UnitPrice,
           CAST(ol.TaxRate AS DECIMAL(5,2))                  AS TaxRate,
           CAST(ol.LineAmount AS DECIMAL(18,2))              AS NetAmount,
           CAST(ol.TaxAmount AS DECIMAL(18,2))               AS TaxAmount,
           CAST(ol.LineAmount + ol.TaxAmount AS DECIMAL(18,2)) AS GrossAmount,
           CAST(ol.IsPriceOutlier AS BIT)                    AS IsPriceOutlier,
           ol.LastEditedWhen
    INTO #src
    FROM clean.order_lines ol
    JOIN clean.orders o               ON o.OrderID = ol.OrderID
    LEFT JOIN dw.DimCustomer dc       ON dc.CustomerID = o.CustomerID AND dc.IsCurrent = 1
    LEFT JOIN dw.DimProduct dp        ON dp.StockItemID = ol.StockItemID
    WHERE ol.LastEditedWhen >= @from;

    -- Upsert: actualizar lo que cambio ...
    UPDATE f
       SET f.Quantity = s.Quantity, f.UnitPrice = s.UnitPrice, f.TaxRate = s.TaxRate,
           f.NetAmount = s.NetAmount, f.TaxAmount = s.TaxAmount, f.GrossAmount = s.GrossAmount,
           f.IsPriceOutlier = s.IsPriceOutlier, f.SourceLastEditedWhen = s.LastEditedWhen,
           f.UpdatedAt = SYSDATETIME()
    FROM dw.FactSales f
    JOIN #src s ON s.OrderLineID = f.OrderLineID
    WHERE f.Quantity <> s.Quantity OR f.UnitPrice <> s.UnitPrice OR f.TaxRate <> s.TaxRate
       OR f.NetAmount <> s.NetAmount OR f.TaxAmount <> s.TaxAmount;
    SET @upd = @@ROWCOUNT;

    -- ... e insertar lo nuevo (si la fila ya existe NO se duplica: idempotencia)
    INSERT INTO dw.FactSales (OrderLineID, OrderID, DateKey, CustomerKey, ProductKey, Quantity,
                              UnitPrice, TaxRate, NetAmount, TaxAmount, GrossAmount,
                              IsPriceOutlier, SourceLastEditedWhen)
    SELECT s.OrderLineID, s.OrderID, s.DateKey, s.CustomerKey, s.ProductKey, s.Quantity,
           s.UnitPrice, s.TaxRate, s.NetAmount, s.TaxAmount, s.GrossAmount,
           s.IsPriceOutlier, s.LastEditedWhen
    FROM #src s
    WHERE NOT EXISTS (SELECT 1 FROM dw.FactSales f WHERE f.OrderLineID = s.OrderLineID);
    SET @ins = @@ROWCOUNT;

    -- El watermark solo avanza si todo lo anterior salio bien (la transaccion es de Python)
    IF @wm_end IS NOT NULL
    BEGIN
        IF EXISTS (SELECT 1 FROM audit.etl_watermark WHERE pipeline_name = 'load_fact_sales')
            UPDATE audit.etl_watermark SET last_watermark = @wm_end, updated_at = SYSDATETIME()
            WHERE pipeline_name = 'load_fact_sales';
        ELSE
            INSERT INTO audit.etl_watermark (pipeline_name, last_watermark)
            VALUES ('load_fact_sales', @wm_end);
    END

    SELECT @ins AS inserted, @upd AS updated, @from AS watermark_start, @wm_end AS watermark_end;
END
GO
