#!/bin/bash
set -e

rm -rf lambda_package lambda_deployment.zip
mkdir lambda_package

python3.13 -m pip install -r requirements_lambda.txt -t lambda_package/ --quiet

cp lambda_function.py lambda_package/

cd lambda_package && zip -r ../lambda_deployment.zip . -x "*.pyc" -x "*__pycache__*"

echo "Done → lambda_deployment.zip ($(du -sh ../lambda_deployment.zip | cut -f1))"
