import logging
import os
import pandas as pd
import streamlit as st
import snowflake.connector
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

st.set_page_config(
    page_title="Financial News Sentiment",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Financial News Sentiment Dashboard")
st.caption("Live sentiment analysis of financial headlines, powered by VADER + Snowflake")


# ------------------------------------------------------------------
# Connection
# ------------------------------------------------------------------
@st.cache_resource(show_spinner="Connecting to Snowflake…")
def get_connection():
    # Streamlit Cloud: secrets live in st.secrets; local: .env
    def _get(key):
        return st.secrets.get(key) or os.getenv(key)

    return snowflake.connector.connect(
        account=_get("SNOWFLAKE_ACCOUNT"),
        user=_get("SNOWFLAKE_USER"),
        password=_get("SNOWFLAKE_PASSWORD"),
        warehouse=_get("SNOWFLAKE_WAREHOUSE"),
        database=_get("SNOWFLAKE_DATABASE"),
        schema=_get("SNOWFLAKE_SCHEMA"),
    )


@st.cache_data(ttl=300, show_spinner="Loading data…")
def load_data() -> pd.DataFrame:
    conn = get_connection()
    query = """
        SELECT
            source_name,
            author,
            title,
            url,
            published_at,
            sentiment_score,
            sentiment_label
        FROM financial_news
        ORDER BY published_at DESC
        LIMIT 2000
    """
    cur = conn.cursor()
    cur.execute(query)
    cols = [d[0].lower() for d in cur.description]
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


# ------------------------------------------------------------------
# Load
# ------------------------------------------------------------------
try:
    df = load_data()
except Exception as e:
    logger.exception("Snowflake load failed")
    st.error("Could not load data. Please try again later.")
    st.stop()

if df.empty:
    st.warning("No data in Snowflake yet — run ingest.news.py and wait for Lambda + Snowpipe.")
    st.stop()

df["published_at"] = pd.to_datetime(df["published_at"])
df["date"] = df["published_at"].dt.date


# ------------------------------------------------------------------
# Sidebar filters
# ------------------------------------------------------------------
st.sidebar.header("Filters")

date_min = df["date"].min()
date_max = df["date"].max()
date_range = st.sidebar.date_input(
    "Date range",
    value=(date_min, date_max),
    min_value=date_min,
    max_value=date_max,
)

label_options = ["All"] + sorted(df["sentiment_label"].unique().tolist())
selected_label = st.sidebar.selectbox("Sentiment label", label_options)

mask = (df["date"] >= date_range[0]) & (df["date"] <= date_range[1])
if selected_label != "All":
    mask &= df["sentiment_label"] == selected_label
filtered = df[mask]

st.sidebar.markdown(f"**{len(filtered):,}** articles shown")


# ------------------------------------------------------------------
# KPI row
# ------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Articles", f"{len(filtered):,}")
col2.metric("Avg Sentiment Score", f"{filtered['sentiment_score'].mean():.3f}")

label_counts = filtered["sentiment_label"].value_counts()
col3.metric("Positive", int(label_counts.get("Positive", 0)))
col4.metric("Negative", int(label_counts.get("Negative", 0)))

st.divider()


# ------------------------------------------------------------------
# Chart 1 — Sentiment over time
# ------------------------------------------------------------------
st.subheader("Sentiment Score Over Time")
daily = (
    filtered.groupby("date")["sentiment_score"]
    .mean()
    .reset_index()
    .rename(columns={"sentiment_score": "avg_sentiment_score"})
)
daily["date"] = pd.to_datetime(daily["date"])
st.line_chart(daily.set_index("date")["avg_sentiment_score"])


# ------------------------------------------------------------------
# Chart 2 — Sentiment label breakdown
# ------------------------------------------------------------------
st.subheader("Sentiment Breakdown")
breakdown = label_counts.reset_index()
breakdown.columns = ["sentiment_label", "count"]

label_order = ["Positive", "Neutral", "Negative"]
breakdown = breakdown.set_index("sentiment_label").reindex(label_order).fillna(0)
st.bar_chart(breakdown["count"])


# ------------------------------------------------------------------
# Table — Latest headlines, score color-coded
# ------------------------------------------------------------------
st.subheader("Latest Headlines")

LABEL_COLORS = {"Positive": "🟢", "Neutral": "🟡", "Negative": "🔴"}

headlines = filtered[["published_at", "title", "source_name", "sentiment_score", "sentiment_label", "url"]].copy()
headlines = headlines.sort_values("published_at", ascending=False).head(100).reset_index(drop=True)
headlines["sentiment"] = headlines["sentiment_label"].map(LABEL_COLORS) + " " + headlines["sentiment_label"]
headlines["score"] = headlines["sentiment_score"].map(lambda x: f"{x:+.3f}")

display = headlines[["published_at", "source_name", "title", "score", "sentiment", "url"]]
display.columns = ["Published", "Source", "Headline", "Score", "Sentiment", "URL"]

st.dataframe(
    display,
    use_container_width=True,
    column_config={
        "URL": st.column_config.LinkColumn("URL", validate=r"^https?://"),
        "Published": st.column_config.DatetimeColumn("Published", format="MMM D, YYYY HH:mm"),
    },
    hide_index=True,
)
