-- Modulo de alertas: reglas, alertas (con estado) y registro de entregas.
-- Lo ejecuta notifications/alert_engine.py (separa los lotes por GO).
IF SCHEMA_ID('alerts') IS NULL EXEC('CREATE SCHEMA alerts');
GO
IF OBJECT_ID('alerts.alert_rule') IS NULL
BEGIN
    CREATE TABLE alerts.alert_rule (
        rule_code     NVARCHAR(40)  NOT NULL CONSTRAINT PK_alert_rule PRIMARY KEY,
        name          NVARCHAR(150) NOT NULL,
        source_type   NVARCHAR(10)  NOT NULL,      -- RULE (regla de negocio) / ML (modelo)
        indicator     NVARCHAR(100) NOT NULL,
        threshold_pct FLOAT         NOT NULL,
        is_active     BIT           NOT NULL CONSTRAINT DF_alert_rule_active DEFAULT 1,
        description   NVARCHAR(500) NULL
    );
    INSERT INTO alerts.alert_rule (rule_code, name, source_type, indicator, threshold_pct, description)
    VALUES (N'SALES_DROP', N'Caida de ventas mensuales', 'RULE', N'Ventas netas mensuales', 15,
            N'Se dispara si las ventas netas del mes caen mas de X% frente al promedio de los 3 meses anteriores.'),
           (N'FORECAST_DROP', N'Prediccion de ventas baja', 'ML', N'Ventas netas pronosticadas', 15,
            N'Se dispara si la prediccion del proximo mes esta mas de X% por debajo del promedio de los ultimos 3 meses reales.');
END
GO
IF OBJECT_ID('alerts.alert') IS NULL
BEGIN
    CREATE TABLE alerts.alert (
        alert_id           BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_alert PRIMARY KEY,
        event_key          NVARCHAR(150) NOT NULL CONSTRAINT UQ_alert_event UNIQUE,   -- evita alertas duplicadas
        rule_code          NVARCHAR(40)  NOT NULL CONSTRAINT FK_alert_rule REFERENCES alerts.alert_rule (rule_code),
        created_at         DATETIME2(0)  NOT NULL CONSTRAINT DF_alert_created DEFAULT SYSDATETIME(),
        source_type        NVARCHAR(10)  NOT NULL,      -- RULE / ML / AI
        severity           NVARCHAR(10)  NOT NULL,      -- BAJA / MEDIA / ALTA
        indicator          NVARCHAR(100) NOT NULL,
        entity             NVARCHAR(100) NOT NULL,
        period_label       NVARCHAR(40)  NULL,
        reference_label    NVARCHAR(100) NULL,
        observed_value     DECIMAL(18,2) NOT NULL,      -- valor observado o predicho
        reference_value    DECIMAL(18,2) NOT NULL,
        threshold_pct      FLOAT         NOT NULL,
        change_pct         FLOAT         NOT NULL,
        model_version      NVARCHAR(60)  NULL,
        explanation        NVARCHAR(1000) NULL,
        recommended_action NVARCHAR(1000) NULL,
        is_simulated       BIT           NOT NULL CONSTRAINT DF_alert_sim DEFAULT 0,
        status             NVARCHAR(12)  NOT NULL CONSTRAINT DF_alert_status DEFAULT N'NUEVA',
        updated_at         DATETIME2(0)  NULL,
        updated_by         NVARCHAR(100) NULL,
        CONSTRAINT CK_alert_status CHECK (status IN (N'NUEVA', N'ATENDIDA', N'DESCARTADA', N'RESUELTA'))
    );
    CREATE INDEX IX_alert_status ON alerts.alert (status, created_at DESC);
END
GO
IF OBJECT_ID('alerts.delivery') IS NULL
CREATE TABLE alerts.delivery (
    delivery_id     BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_delivery PRIMARY KEY,
    alert_id        BIGINT        NOT NULL CONSTRAINT FK_delivery_alert REFERENCES alerts.alert (alert_id),
    channel         NVARCHAR(20)  NOT NULL,          -- DASHBOARD / EMAIL
    status          NVARCHAR(10)  NOT NULL,          -- SENT / FAILED
    attempts        INT           NOT NULL CONSTRAINT DF_delivery_att DEFAULT 0,
    last_attempt_at DATETIME2(0)  NULL,
    error_detail    NVARCHAR(500) NULL,
    CONSTRAINT UQ_delivery UNIQUE (alert_id, channel)
);
GO
-- El dashboard solo puede LEER alertas y cambiar su estado (no borrar ni modificar el resto)
IF DATABASE_PRINCIPAL_ID('api_reader') IS NOT NULL
BEGIN
    GRANT SELECT ON SCHEMA::alerts TO api_reader;
    GRANT UPDATE (status, updated_at, updated_by) ON alerts.alert TO api_reader;
END
GO
