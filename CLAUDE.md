# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Serverless ETL pipeline: financial news ingestion → VADER sentiment analysis → Snowflake → Streamlit dashboard. Runs on AWS Free Tier + Snowflake Trial. Python 3.13.

## Commands

```bash
# Activate virtualenv
source .venv/bin/activate

# Run the ingestion pipeline (fetches ~100 articles, uploads to S3 landing/)
python ingest.news.py

# Verify newsapi.ai key and connectivity (fetches 1 article to conserve quota)
python test_newsapi.py

# Verify AWS S3 connectivity
python test_setup.py

# Package Lambda for deployment (produces lambda_deployment.zip)
bash package_lambda.sh
```

Tests are standalone scripts (no pytest). Run them directly with `python`.

## Environment Variables (.env)

```
NEWS_API_KEY              # newsapi.ai via eventregistry SDK
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
S3_BUCKET_NAME
```

Phase 3 will add Snowflake credentials; Phase 4 uses Streamlit Cloud secrets (not .env).

## Architecture

Four-phase pipeline (Phases 1–2 complete, 3–4 planned):

**Phase 1 — Ingest** (`ingest.news.py`): `NewsIngestor` class uses the `eventregistry` SDK to pull today's financial articles (up to 100/run), normalizes them into a DataFrame, and lands a timestamped CSV at `s3://<bucket>/landing/raw_news_<timestamp>.csv`.

**Phase 2 — Sentiment** (`lambda_function.py`): AWS Lambda triggered by `s3:ObjectCreated:*` on the `landing/` prefix. Reads the CSV, scores each row's `title + description` with VADER, appends `sentiment_score` (compound, –1 to 1) and `sentiment_label` (Positive ≥ 0.05, Negative ≤ –0.05, else Neutral), writes to `processed/<same filename>`.

**Phase 3 — Warehouse** (`snowflake_setup.sql`, not yet created): Snowpipe with `AUTO_INGEST = TRUE` watches `processed/` and loads into a `financial_news` Snowflake table.

**Phase 4 — Dashboard** (`dashboard/app.py`, not yet created): Streamlit app queries Snowflake and renders sentiment-over-time and breakdown charts.

## S3 Layout

```
<bucket>/
  landing/    # raw CSVs from ingest.news.py
  processed/  # sentiment-enriched CSVs from Lambda
```

## Lambda Deployment

`package_lambda.sh` installs `requirements_lambda.txt` (only `vaderSentiment==3.3.2`) into `lambda_package/`, copies `lambda_function.py`, and zips to `lambda_deployment.zip`. Lambda runtime is Python 3.12 in AWS; the packaging script uses `python3.13` locally — keep these in sync if upgrading.

After packaging, deploy via AWS Console: 256 MB memory, IAM policy scoped to `s3:GetObject` on `landing/*` and `s3:PutObject` on `processed/*`, S3 trigger on `landing/` prefix.
