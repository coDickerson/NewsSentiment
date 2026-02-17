import os
import pandas as pd
from newsapi import NewsApiClient
from datetime import datetime
from dotenv import load_dotenv
import boto3

# Load credentials from .env
load_dotenv()

class NewsIngestor:
    def __init__(self):
        self.api_key = os.getenv('NEWS_API_KEY')
        self.newsapi = NewsApiClient(api_key=self.api_key)
        self.s3_bucket = os.getenv('S3_BUCKET_NAME')
        self.s3_client = boto3.client('s3')

    def fetch_financial_news(self, query='economy OR stock market'):
        """Fetches raw data from NewsAPI"""
        # Use 'everything' for historical/depth or 'top_headlines' for speed
        response = self.newsapi.get_everything(
            q=query,
            language='en',
            sort_by='publishedAt',
            page_size=100  # Max for free tier
        )
        return response['articles']

    def process_to_dataframe(self, articles):
        '''Data cleaning and transformation'''
        df = pd.DataFrame(articles)
        
        # Flatten the 'source' column which is a dictionary
        df['source_name'] = df['source'].apply(lambda x: x['name'])
        
        # Keep only essential columns for Snowflake warehouse
        cols_to_keep = ['source_name', 'author', 'title', 'description', 'url', 'publishedAt', 'content']
        df = df[cols_to_keep]
        
        # Data Cleaning: Remove rows with missing essential info
        df = df.dropna(subset=['title', 'description'])
        
        # Convert timestamp to ISO format
        df['publishedAt'] = pd.to_datetime(df['publishedAt'])
        
        return df

    def upload_to_s3(self, df):
        """Uploads to S3 as a CSV"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"raw_news_{timestamp}.csv"
        
        # Convert DF to CSV string in memory
        csv_buffer = df.to_csv(index=False)
        
        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=f"landing/{filename}",
            Body=csv_buffer
        )
        print(f"Successfully uploaded {filename} to S3")

if __name__ == "__main__":
    ingestor = NewsIngestor()
    raw_data = ingestor.fetch_financial_news()
    cleaned_df = ingestor.process_to_dataframe(raw_data)
    ingestor.upload_to_s3(cleaned_df)