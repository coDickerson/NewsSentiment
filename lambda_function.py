import boto3
import csv
import io
import os
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

s3 = boto3.client('s3', region_name=os.getenv('AWS_REGION', 'us-west-1'))
analyzer = SentimentIntensityAnalyzer()


def _sentiment_label(compound: float) -> str:
    if compound >= 0.05:
        return 'Positive'
    elif compound <= -0.05:
        return 'Negative'
    return 'Neutral'


def lambda_handler(event, context):
    record = event['Records'][0]['s3']
    bucket = record['bucket']['name']
    key = record['object']['key']

    obj = s3.get_object(Bucket=bucket, Key=key)
    content = obj['Body'].read().decode('utf-8')

    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        text = f"{row.get('title', '')} {row.get('description', '')}"
        compound = analyzer.polarity_scores(text)['compound']
        row['sentiment_score'] = round(compound, 4)
        row['sentiment_label'] = _sentiment_label(compound)
        rows.append(row)

    if not rows:
        return {'statusCode': 200, 'body': 'No rows to process'}

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    filename = key.split('/')[-1]
    processed_key = f"processed/{filename}"

    s3.put_object(
        Bucket=bucket,
        Key=processed_key,
        Body=output.getvalue(),
    )

    print(f"Processed {len(rows)} articles → s3://{bucket}/{processed_key}")
    return {'statusCode': 200, 'body': f'Processed {len(rows)} articles'}
