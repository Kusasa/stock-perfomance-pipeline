#!/bin/bash

echo "Stop Airflow service"
ssh -i "~/.ssh/stock_perfomance_key.pem" ubuntu@$EC2PublicIP << 'EOF'
cd ~/pipeline &&
docker-compose down
exit
EOF

echo "Delete pipeline stack"
aws cloudformation delete-stack --stack-name stockPerfomancesInfra
aws cloudformation wait stack-delete-complete --stack-name stockPerfomancesInfra

REM Delete keypair
aws ec2 delete-key-pair --key-name stock_perfomance_key --region us-east-1

echo "Delete SNS Topic"
aws sns delete-topic --topic-arn arn:aws:sns:us-east-1:008971661443:stock_perfomance_alerts