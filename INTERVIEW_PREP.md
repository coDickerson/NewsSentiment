# Financial News Sentiment Pipeline — Interview Prep

A cheat-sheet for talking about this project in technical interviews.
Keep it open, read it the night before, and you'll be ready for any direction they take.

---

## 1. One-Sentence Pitch

> "I built a fully serverless ETL pipeline that fetches financial news headlines, runs VADER sentiment analysis in AWS Lambda triggered by S3 events, warehouses the enriched data in Snowflake via Snowpipe, and visualizes trends in a live Streamlit dashboard."

---

## 2. Architecture at a Glance

```
newsapi.ai
    │  (eventregistry SDK, QueryArticlesIter)
    ▼
ingest.news.py  ──────────────────────────►  S3: landing/raw_news_<ts>.csv
                                                      │
                                              S3 Event Notification (ObjectCreated)
                                                      │
                                                      ▼
                                              AWS Lambda (lambda_function.py)
                                              VADER scores title + description
                                              writes enriched CSV
                                                      │
                                                      ▼
                                             S3: processed/raw_news_<ts>.csv
                                                      │
                                              S3 Event Notification → SQS (Snowpipe)
                                                      │
                                                      ▼
                                             Snowflake: financial_news table
                                                      │
                                                      ▼
                                             Streamlit dashboard (dashboard/app.py)
```

**Key design choice:** event-driven, not scheduled. Lambda fires the moment a new file lands in `landing/`. Snowpipe fires the moment a file lands in `processed/`. Zero polling, near-real-time end-to-end.

---

## 3. VADER — Deep Dive

### What is VADER?

VADER (Valence Aware Dictionary and sEntiment Reasoner) is a **rule-based, lexicon-driven** sentiment analyzer built specifically for short, informal social media text. It outputs four scores:

| Score | Range | Meaning |
|-------|-------|---------|
| `pos` | 0–1 | Fraction of tokens scored positive |
| `neu` | 0–1 | Fraction scored neutral |
| `neg` | 0–1 | Fraction scored negative |
| `compound` | −1 to +1 | Normalized weighted composite of the three |

### Why VADER for financial news?

- **No GPU, no training data needed** — installs as a 2 MB pip package, runs in Lambda's 256 MB memory footprint
- **Speed** — scores thousands of articles in milliseconds; no model inference latency
- **Financial text quirk** — headlines are terse and keyword-heavy (exactly what VADER was tuned for)
- **Trade-off vs. FinBERT**: VADER misses domain-specific meaning ("guidance lowered" is negative in finance but not in everyday English). FinBERT would be more accurate but requires a GPU or a paid inference endpoint

### The compound score formula

VADER sums each token's valence (from its lexicon), applies booster/dampener rules (all-caps, punctuation, degree modifiers like "very"), then normalizes:

```
compound = sum_of_valences / sqrt(sum_of_valences² + 15)
```

The `+ 15` is a hand-tuned normalization constant from the original paper that keeps the result in [−1, +1].

### Thresholds — the 0.05 rule

```python
if compound >= 0.05:    label = 'Positive'
elif compound <= -0.05: label = 'Negative'
else:                   label = 'Neutral'
```

These are **VADER's recommended default thresholds** from Hutto & Gilbert (2014). They were derived empirically on Amazon product reviews and Twitter data. In financial text, headlines tend to cluster near zero (neutral institutional language), so the ±0.05 band works well — it avoids false positives from mildly worded releases.

**"Why not tighten the threshold to ±0.2 for finance?"** — Fair challenge. Stricter thresholds would reduce false positives (e.g. "stock edges higher" labeled Positive) but increase Neutral counts. For a dashboard showing trends, the broad threshold gives more signal; for a trading signal, you'd tighten it or switch to FinBERT.

### What text does VADER score?

```python
text = f"{row.get('title', '')} {row.get('description', '')}"
```

Title + body concatenated. The title dominates emotionally (that's intentional — it's what drives engagement and what analysts scan). Body adds context that title puns or hedges don't capture.

---

## 4. Hardest Challenges

### Challenge 1 — Lambda packaging for vaderSentiment

vaderSentiment ships with `.so` native extension files that are architecture-dependent. Building on an M-series Mac and uploading to Lambda (Amazon Linux x86_64 / arm64) will silently fail at runtime.

**Solution:** Package via `pip install ... -t lambda_package/` inside the target Lambda environment or use the `--platform manylinux2014_x86_64` flag when building locally. Alternatively: publish as a Lambda Layer from a Cloud9 instance.

### Challenge 2 — Snowpipe trust-policy handshake

Snowflake creates its own IAM user (not yours) to read from S3. After `CREATE STORAGE INTEGRATION`, you run `DESC INTEGRATION` to get Snowflake's IAM user ARN and external ID, then paste those into your AWS IAM role's trust policy. Getting this wrong produces a silent failure — Snowpipe just never ingests. Debugging required checking `SYSTEM$PIPE_STATUS()` and CloudTrail.

### Challenge 3 — newsapi.ai free-tier quirks

The `eventregistry` SDK's `QueryArticlesIter` silently returns 0 results if `allowUseOfArchive=True` on a free-tier key. Also, `dateStart`/`dateEnd` use the article's crawl date, not its publication date — a subtlety that caused me to see "today" articles that were published yesterday.

### Challenge 4 — Streamlit + Snowflake credential duality

Streamlit Cloud uses `st.secrets` (a TOML file in the dashboard), not `.env`. Local dev uses `.env`. The dashboard reads `st.secrets.get(key) or os.getenv(key)` to handle both without branching on environment.

---

## 5. Common Interview Questions

### "Walk me through the pipeline end to end."

Start with the ingestion script: `ingest.news.py` runs `QueryArticlesIter` with financial keywords, maps raw article dicts to a clean DataFrame, and uploads a CSV to `s3://bucket/landing/`. That S3 write triggers a Lambda via an S3 event notification. Lambda reads the CSV, scores each row with VADER on `title + description`, and writes the enriched CSV to `processed/`. A Snowpipe SQS notification on `processed/` auto-ingests into the `financial_news` table. The Streamlit dashboard queries that table live.

### "Why Lambda instead of an EC2 instance or Glue job?"

Scale-to-zero billing and zero ops. Runs 100 files/day for free on Lambda's free tier. An EC2 instance would idle 23 h/day. Glue has a 10-minute minimum billing unit — overkill for CSVs measured in KB. Lambda cold start (~500 ms) is fine because the trigger doesn't need sub-second latency.

### "What's the SLA between a file landing and showing up in Snowflake?"

Roughly 1–3 minutes end to end: Lambda fires within seconds of the S3 write → CSV written to `processed/` → Snowpipe polls its SQS queue every ~1 minute → COPY INTO completes. Not real-time, but fast enough for a news dashboard.

### "How would you scale this to 1M articles/day?"

- Keep Lambda as-is (it scales horizontally automatically; S3 trigger fans out per file)
- Switch from newsapi.ai to a paid Firehose feed, land Parquet instead of CSV
- Partition S3 by `YYYY/MM/DD/` and add an Athena external table for ad-hoc queries without loading Snowflake
- Move VADER scoring into a Spark job (AWS Glue or EMR) if article volume per file grows large
- Consider FinBERT on a SageMaker endpoint for accuracy at scale

### "Why VADER and not a transformer model like FinBERT?"

VADER fits in a Lambda deployment package (<5 MB) with no inference server. FinBERT needs ~440 MB and a GPU for reasonable throughput. For a side project on free-tier AWS, VADER was the right call. If accuracy on domain-specific phrases ("earnings miss", "beat consensus") becomes critical, I'd add FinBERT via a SageMaker endpoint and call it from Lambda.

### "What's Snowpipe and why not just run COPY INTO on a schedule?"

Snowpipe is Snowflake's continuous-ingest service. It listens on an SQS queue that S3 writes to on every `ObjectCreated` event, then issues a micro-`COPY INTO` for each new file within ~1 minute. A scheduled `COPY INTO` would introduce lag (at minimum, the scheduling interval), require a running compute resource to trigger it, and adds operational complexity. Snowpipe is fully managed and charges per credit of compute consumed, not per minute it's running.

### "How do you handle duplicate articles?"

Two layers: (1) the `isDuplicateFilter='skipDuplicates'` parameter in `QueryArticlesIter` deduplicates at the API level. (2) If the same file is somehow re-processed (Lambda retry), Snowpipe's `COPY INTO` tracks loaded file metadata and skips already-loaded files by default.

### "Walk me through the Streamlit dashboard features."

Sidebar with date-range picker and sentiment-label filter. Four KPI cards (total articles, avg score, positive count, negative count). A daily average sentiment line chart showing trend over time. A bar chart of label distribution (Positive / Neutral / Negative). A 100-row latest-headlines table with colored emoji sentiment badges, score formatted as `+0.123` / `-0.045`, and clickable URLs. All cached for 5 minutes via `@st.cache_data`.

### "What would you monitor in production?"

- Lambda: CloudWatch `Errors` and `Duration` alarms; set alarm if `processed/` write count diverges from `landing/` write count
- Snowpipe: `SYSTEM$PIPE_STATUS('news_pipe')` for staleness; Snowflake task to alert if table row count stops growing
- Ingestor: alert if newsapi.ai returns 0 articles (quota exhausted or key expired)
- Dashboard: Streamlit Cloud's built-in error emails

---

## 6. Tech Stack Summary Card

| Component | Technology | Why |
|-----------|-----------|-----|
| News source | newsapi.ai (eventregistry SDK) | Financial keyword filtering, 100 req/day free |
| Storage | AWS S3 | Free tier, native Lambda/Snowpipe integration |
| Compute | AWS Lambda (Python 3.12) | Serverless, event-driven, free tier |
| NLP | VADER (vaderSentiment 3.3.2) | No GPU, fast, fits in Lambda |
| Warehouse | Snowflake | Auto-ingest Snowpipe, SQL, Streamlit connector |
| Dashboard | Streamlit | Python-native, free cloud hosting |
| IaC | Manual + SQL scripts | Scope: learning project, not prod infra |

---

## 7. Things to Know Cold

- VADER compound threshold: `≥0.05` Positive, `≤-0.05` Negative
- Snowpipe latency: ~1 minute (SQS polling interval)
- Lambda memory: 256 MB (vaderSentiment peak ~50 MB)
- newsapi.ai free tier: 100 articles/request, 30-day lookback, 1-month history
- S3 landing prefix: `landing/`, processed prefix: `processed/`
- Snowflake table: `NEWS_DB.PUBLIC.financial_news`
- Dashboard cache TTL: 5 minutes (`@st.cache_data(ttl=300)`)
