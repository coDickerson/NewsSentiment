import boto3
import os
from dotenv import load_dotenv

load_dotenv() # Loads the variables from .env

s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

# This will list your buckets to confirm the handshake works
response = s3.list_buckets()
print("Connection Successful! Buckets found:", [b['Name'] for b in response['Buckets']])