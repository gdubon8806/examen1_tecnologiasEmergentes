-- Base de staging + DW con esquemas separados
IF DB_ID('AnalyticsDW') IS NULL CREATE DATABASE AnalyticsDW;
GO
USE AnalyticsDW;
GO
IF SCHEMA_ID('raw')   IS NULL EXEC('CREATE SCHEMA raw');    -- datos tal como llegan de la fuente
IF SCHEMA_ID('clean') IS NULL EXEC('CREATE SCHEMA clean');  -- datos validados/depurados
IF SCHEMA_ID('dw')    IS NULL EXEC('CREATE SCHEMA dw');     -- modelo dimensional
IF SCHEMA_ID('audit') IS NULL EXEC('CREATE SCHEMA audit');  -- auditoría y calidad
GO

-- Auditoría de ejecuciones ETL
IF OBJECT_ID('audit.etl_run') IS NULL
CREATE TABLE audit.etl_run (
    execution_id    UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID() PRIMARY KEY,
    pipeline_name   VARCHAR(100)  NOT NULL,
    start_time      DATETIME2     NOT NULL DEFAULT SYSDATETIME(),
    end_time        DATETIME2     NULL,
    source_object   VARCHAR(200)  NULL,
    target_object   VARCHAR(200)  NULL,
    rows_read       INT NULL, rows_inserted INT NULL,
    rows_updated    INT NULL, rows_rejected INT NULL,
    status          VARCHAR(20)   NOT NULL DEFAULT 'RUNNING',  -- RUNNING / SUCCESS / FAILED
    error_detail    NVARCHAR(MAX) NULL,
    watermark_start DATETIME2     NULL,
    watermark_end   DATETIME2     NULL
);

-- Watermark persistente (solo se avanza si la carga termina bien)
IF OBJECT_ID('audit.etl_watermark') IS NULL
CREATE TABLE audit.etl_watermark (
    pipeline_name VARCHAR(100) PRIMARY KEY,
    last_watermark DATETIME2 NOT NULL,
    updated_at DATETIME2 NOT NULL DEFAULT SYSDATETIME()
);

-- Cuarentena de registros rechazados
IF OBJECT_ID('audit.quarantine') IS NULL
CREATE TABLE audit.quarantine (
    quarantine_id BIGINT IDENTITY PRIMARY KEY,
    execution_id  UNIQUEIDENTIFIER NOT NULL,
    source_object VARCHAR(200) NOT NULL,
    business_key  VARCHAR(100) NULL,
    failed_rule   VARCHAR(200) NOT NULL,
    record_json   NVARCHAR(MAX) NULL,
    created_at    DATETIME2 NOT NULL DEFAULT SYSDATETIME()
);
GO
PRINT 'Estructura AnalyticsDW creada.';
GO
