-- Objetos para Machine Learning: vista analitica controlada + registro de modelos + pronosticos.
-- Lo ejecuta machine-learning/train_forecast.py (separa los lotes por GO).
IF SCHEMA_ID('ml') IS NULL EXEC('CREATE SCHEMA ml');
GO
CREATE OR ALTER VIEW dw.vw_monthly_sales AS
SELECT DATEFROMPARTS(d.[Year], d.[Month], 1) AS month_start,
       d.YearMonth AS ym,
       SUM(f.NetAmount) AS net_sales,
       SUM(f.Quantity) AS units,
       COUNT(DISTINCT f.OrderID) AS orders,
       MAX(d.[Date]) AS last_day_with_data
FROM dw.FactSales f
JOIN dw.DimDate d ON d.DateKey = f.DateKey
GROUP BY d.[Year], d.[Month], d.YearMonth;
GO
IF OBJECT_ID('ml.model_registry') IS NULL
CREATE TABLE ml.model_registry (
    model_version      NVARCHAR(60)   NOT NULL CONSTRAINT PK_model_registry PRIMARY KEY,
    algorithm          NVARCHAR(100)  NOT NULL,
    target             NVARCHAR(100)  NOT NULL,
    trained_at         DATETIME2(0)   NOT NULL CONSTRAINT DF_model_trained DEFAULT SYSDATETIME(),
    trained_through    DATE           NOT NULL,   -- ultimo mes completo usado
    n_months           INT            NOT NULL,
    harmonics          TINYINT        NOT NULL,
    alpha              FLOAT          NOT NULL,
    mae_test           FLOAT NULL, rmse_test FLOAT NULL, mape_test FLOAT NULL,
    baseline_name      NVARCHAR(50) NULL,
    baseline_mae_test  FLOAT NULL, baseline_rmse_test FLOAT NULL, baseline_mape_test FLOAT NULL,
    metrics_json       NVARCHAR(MAX)  NULL,
    model_path         NVARCHAR(400)  NOT NULL,
    is_active          BIT            NOT NULL CONSTRAINT DF_model_active DEFAULT 0
);
GO
IF OBJECT_ID('ml.forecast_sales') IS NULL
BEGIN
    CREATE TABLE ml.forecast_sales (
        forecast_id         BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_forecast_sales PRIMARY KEY,
        model_version       NVARCHAR(60)  NOT NULL CONSTRAINT FK_forecast_model REFERENCES ml.model_registry (model_version),
        prediction_date     DATETIME2(0)  NOT NULL CONSTRAINT DF_forecast_date DEFAULT SYSDATETIME(),
        horizon_months      TINYINT       NOT NULL,
        target_month        DATE          NOT NULL,
        predicted_net_sales DECIMAL(18,2) NOT NULL,
        lower_80            DECIMAL(18,2) NOT NULL,
        upper_80            DECIMAL(18,2) NOT NULL,
        is_prediction       BIT           NOT NULL CONSTRAINT DF_forecast_flag DEFAULT 1   -- es PREDICCION, no dato historico
    );
    CREATE INDEX IX_forecast_model ON ml.forecast_sales (model_version, prediction_date);
END
GO
IF DATABASE_PRINCIPAL_ID('api_reader') IS NOT NULL GRANT SELECT ON SCHEMA::ml TO api_reader;
GO
