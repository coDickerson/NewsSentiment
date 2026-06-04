import os
import pandas as pd
import boto3
from datetime import date, datetime
from dotenv import load_dotenv
from eventregistry import EventRegistry, QueryArticlesIter, ArticleInfoFlags, ReturnInfo

load_dotenv()


class NewsIngestor:
    def __init__(self):
        self.er = EventRegistry(
            apiKey=os.getenv('NEWS_API_KEY'),
            allowUseOfArchive=False,
            verboseOutput=False,
        )
        self.s3_bucket = os.getenv('S3_BUCKET_NAME')
        self.s3_client = boto3.client('s3')

    def fetch_financial_news(self, max_articles=100):
        """Fetches today's financial news articles via newsapi.ai"""
        today = date.today().isoformat()

        q = QueryArticlesIter(
            keywords='"S&P 500" OR NVIDIA OR earnings OR "stock market" OR economy',
            dateStart=today,
            dateEnd=today,
            lang='eng',
            isDuplicateFilter='skipDuplicates',
        )

        return_info = ReturnInfo(
            articleInfo=ArticleInfoFlags(bodyLen=300, authors=True)
        )

        articles = []
        for article in q.execQuery(self.er, sortBy='date', maxItems=max_articles, returnInfo=return_info):
            articles.append(article)

        return articles

    def process_to_dataframe(self, articles):
        """Data cleaning and transformation"""
        if not articles:
            return pd.DataFrame(columns=['source_name', 'author', 'title', 'description', 'url', 'publishedAt'])

        rows = []
        for a in articles:
            rows.append({
                'source_name': a.get('source', {}).get('title', ''),
                'author': ', '.join(auth.get('name', '') for auth in a.get('authors', [])),
                'title': a.get('title', ''),
                'description': a.get('body', ''),
                'url': a.get('url', ''),
                'publishedAt': a.get('dateTime', ''),
            })

        df = pd.DataFrame(rows)
        df = df.dropna(subset=['title'])
        df['publishedAt'] = pd.to_datetime(df['publishedAt'])

        return df

    def upload_to_s3(self, df):
        """Uploads to S3 as a CSV in the landing/ prefix"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"raw_news_{timestamp}.csv"

        csv_buffer = df.to_csv(index=False)

        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=f"landing/{filename}",
            Body=csv_buffer,
        )
        print(f"Uploaded {len(df)} articles → s3://{self.s3_bucket}/landing/{filename}")


if __name__ == "__main__":
    ingestor = NewsIngestor()
    raw_articles = ingestor.fetch_financial_news()
    print(f"Fetched {len(raw_articles)} articles")
    if not raw_articles:
        print("No articles returned — daily quota may be exhausted or API key invalid")
        exit(0)
    df = ingestor.process_to_dataframe(raw_articles)
    if df.empty:
        print("No valid articles after processing")
        exit(0)
    ingestor.upload_to_s3(df)
