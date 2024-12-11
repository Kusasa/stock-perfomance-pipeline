@echo off

REM Stop airflow service
ssh -i "C:\Users\skusa\.ssh\stock_perfomance_key.pem" ubuntu@%EC2PublicIP% "cd pipeline && docker-compose down"

REM Delete pipeline stack
aws cloudformation delete-stack --stack-name stockPerfomancesInfra

REM Delete keypair
aws ec2 delete-key-pair --key-name stock_perfomance_key --region us-east-1

REM Delete SNS Topic
aws sns delete-topic --topic-arn arn:aws:sns:us-east-1:008971661443:stock_perfomance_alerts --region us-east-1

