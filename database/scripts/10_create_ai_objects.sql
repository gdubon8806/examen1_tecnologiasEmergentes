-- Registro de consultas al asistente (auditoria compatible con privacidad: sin resultados, texto acotado).
-- Lo ejecuta generative_ai/setup_ai.py
IF SCHEMA_ID('ai') IS NULL EXEC('CREATE SCHEMA ai');
GO
IF OBJECT_ID('ai.assistant_log') IS NULL
CREATE TABLE ai.assistant_log (
    log_id           BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_assistant_log PRIMARY KEY,
    asked_at         DATETIME2(0)  NOT NULL CONSTRAINT DF_assistant_log_at DEFAULT SYSDATETIME(),
    username         NVARCHAR(100) NOT NULL,
    question         NVARCHAR(500) NOT NULL,
    status           NVARCHAR(20)  NOT NULL,     -- ANSWERED / NO_DATA / OUT_OF_SCOPE / ERROR
    tools            NVARCHAR(200) NULL,
    provider         NVARCHAR(60)  NULL,
    latency_ms       INT           NULL,
    unverified_count INT           NOT NULL CONSTRAINT DF_assistant_log_unv DEFAULT 0
);
GO
IF DATABASE_PRINCIPAL_ID('api_reader') IS NOT NULL GRANT INSERT ON ai.assistant_log TO api_reader;
GO
