#!/bin/bash
# Builds lambda_deployment.zip from lambda_function.py + requirements_lambda.txt
set -e

rm -rf lambda_package lambda_deployment.zip
mkdir lambda_package

pip install -r requirements_lambda.txt -t lambda_package/ --quiet

cp lambda_function.py lambda_package/

cd lambda_package
zip -r ../lambda_deployment.zip . -q
cd ..

echo "Built lambda_deployment.zip ($(du -sh lambda_deployment.zip | cut -f1))"
