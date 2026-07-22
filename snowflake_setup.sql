-- =============================================================
-- Phase 3: Snowflake Setup — run these blocks in order in a
-- Snowflake worksheet.  Items marked [YOU FILL IN] need values
-- from your AWS account before running.
-- =============================================================


-- ---------------------------------------------------------------
-- 1. One-time warehouse / database / schema (skip if they exist)
-- ---------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS NEWS_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND   = 60
    AUTO_RESUME    = TRUE;

CREATE DATABASE IF NOT EXISTS NEWS_DB;
CREATE SCHEMA IF NOT EXISTS NEWS_DB.PUBLIC;

USE DATABASE NEWS_DB;
USE SCHEMA PUBLIC;
USE WAREHOUSE NEWS_WH;


-- ---------------------------------------------------------------
-- 2. Target table
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_news (
    source_name     VARCHAR,
    author          VARCHAR,
    title           VARCHAR,
    description     TEXT,
    url             VARCHAR,
    published_at    TIMESTAMP_NTZ,
    sentiment_score FLOAT,
    sentiment_label VARCHAR
);


-- ---------------------------------------------------------------
-- 3. IAM credentials for S3 access
--    [YOU FILL IN] Replace with your AWS key pair (the same user
--    that writes to S3 from Lambda).  Least-privilege: needs only
--    s3:GetObject on processed/*.
-- ---------------------------------------------------------------
CREATE OR REPLACE STORAGE INTEGRATION s3_news_integration
    TYPE                      = EXTERNAL_STAGE
    STORAGE_PROVIDER          = 'S3'
    ENABLED                   = TRUE
    STORAGE_AWS_ROLE_ARN      = 'arn:aws:iam::<YOUR_ACCOUNT_ID>:role/<YOUR_SNOWFLAKE_ROLE>'
    STORAGE_ALLOWED_LOCATIONS = ('s3://dickerson-s3-news-sentiment-data/processed/');

-- After creating the integration, run this and give the output
-- (STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID) to your
-- AWS IAM role's trust policy:
DESC INTEGRATION s3_news_integration;


-- ---------------------------------------------------------------
-- 4. External stage pointing at the processed/ prefix
-- ---------------------------------------------------------------
CREATE OR REPLACE STAGE news_processed_stage
    STORAGE_INTEGRATION = s3_news_integration
    URL                 = 's3://dickerson-s3-news-sentiment-data/processed/'
    FILE_FORMAT         = (
        TYPE             = CSV
        SKIP_HEADER      = 1
        FIELD_OPTIONALLY_ENCLOSED_BY = '"'
        EMPTY_FIELD_AS_NULL = TRUE
        DATE_FORMAT      = AUTO
        TIMESTAMP_FORMAT = AUTO
    );


-- ---------------------------------------------------------------
-- 5. Validate with a manual COPY before enabling auto-ingest
--    (Upload one test CSV to processed/ first, then run this)
-- ---------------------------------------------------------------
COPY INTO financial_news (
    source_name, author, title, description, url,
    published_at, sentiment_score, sentiment_label
)
FROM @news_processed_stage
ON_ERROR = 'CONTINUE';

SELECT COUNT(*), MIN(published_at), MAX(published_at) FROM financial_news;
SELECT sentiment_label, COUNT(*) FROM financial_news GROUP BY 1 ORDER BY 2 DESC;


-- ---------------------------------------------------------------
-- 6. Snowpipe — auto-ingest new files from S3
--    After creation, grab the SQS ARN from the SHOW PIPES output
--    and add it as an S3 bucket notification on processed/*.
-- ---------------------------------------------------------------
CREATE OR REPLACE PIPE news_pipe
    AUTO_INGEST = TRUE
    AS
    COPY INTO financial_news (
        source_name, author, title, description, url,
        published_at, sentiment_score, sentiment_label
    )
    FROM @news_processed_stage;

-- Get the SQS ARN to configure S3 → Snowpipe notifications:
SHOW PIPES LIKE 'news_pipe';
-- Copy the notification_channel column value (the SQS ARN),
-- then in AWS S3 Console → your bucket → Properties →
-- Event notifications → add notification with that SQS ARN,
-- prefix = processed/, event = s3:ObjectCreated:*

-- Monitor pipe status:
SELECT SYSTEM$PIPE_STATUS('news_pipe');
