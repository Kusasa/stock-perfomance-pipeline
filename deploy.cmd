@echo off

REM Create and subscribe to SNS Alert
aws sns create-topic --name stock_perfomance_alerts --region us-east-1
aws sns subscribe --topic-arn arn:aws:sns:us-east-1:008971661443:stock_perfomance_alerts --protocol email --notification-endpoint skusasalethu@gmail.com

REM Create keypair
aws ec2 create-key-pair --key-name stock_perfomance_key --region us-east-1 --query KeyMaterial --output text > %USERPROFILE%\.ssh\stock_perfomance_key.pem

REM Deploy pipeline stack
aws cloudformation create-stack --stack-name stockPerfomancesInfra --template-body file://infrastructure/pipeline_infra.yml --region us-east-1
aws cloudformation wait stack-create-complete --stack-name stockPerfomancesInfra

REM Capture output values from the stack deployment as variables
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name stockPerfomancesInfra --query "Stacks[0].Outputs[?OutputKey=='EC2InstanceId'].OutputValue" --output text') do set EC2InstanceId=%%i
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name stockPerfomancesInfra --query "Stacks[0].Outputs[?OutputKey=='EC2PublicIP'].OutputValue" --output text') do set EC2PublicIP=%%i
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name stockPerfomancesInfra --query "Stacks[0].Outputs[?OutputKey=='RDSInstanceIdentifier'].OutputValue" --output text') do set RDSInstanceIdentifier=%%i
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name stockPerfomancesInfra --query "Stacks[0].Outputs[?OutputKey=='RDSInstanceEndpoint'].OutputValue" --output text') do set RDSInstanceEndpoint=%%i

REM Add host fingerprint of EC2 instance
ssh-keyscan -t ed25519 %EC2PublicIP% >> %USERPROFILE%\.ssh\known_hosts

REM Connect to the EC2 instance using SSH and create the home directory of the pipeline
ssh -i %USERPROFILE%\.ssh\stock_perfomance_key.pem ubuntu@%EC2PublicIP% mkdir ~/pipeline
ssh -i %USERPROFILE%\.ssh\stock_perfomance_key.pem ubuntu@%EC2PublicIP% ^
"mkdir -p ~/pipeline/dags ~/pipeline/logs ~/pipeline/plugins ~/pipeline/examples"

REM Copy dag folder with its contents to the dags folder in the remote server
scp -i %USERPROFILE%\.ssh\stock_perfomance_key.pem -r .\dag\* ubuntu@%EC2PublicIP%:~/pipeline/dags
scp -i %USERPROFILE%\.ssh\stock_perfomance_key.pem -r .\infrastructure\requirements.txt ubuntu@%EC2PublicIP%:~/pipeline/requirements.txt
scp -i %USERPROFILE%\.ssh\stock_perfomance_key.pem -r .\infrastructure\Dockerfile ubuntu@%EC2PublicIP%:~/pipeline/Dockerfile
scp -i %USERPROFILE%\.ssh\stock_perfomance_key.pem -r .\infrastructure\docker-compose.yaml ubuntu@%EC2PublicIP%:~/pipeline/docker-compose.yaml
scp -i %USERPROFILE%\.ssh\stock_perfomance_key.pem -r .\examples\most_popular_tweets_2024-12-07T21_17_35.json ubuntu@%EC2PublicIP%:~/pipeline/examples/most_popular_tweets_2024-12-07T21_17_35.json

REM Install Docker, Airflow containers and python dependencies
ssh -i %USERPROFILE%\.ssh\stock_perfomance_key.pem ubuntu@%EC2PublicIP% "bash -s" < .\infrastructure\docker_airflow.sh

REM Set airflow connections and variables
echo WAIT 3 MINUTES FOR THE AIRFLOW SERVICES TO FULLY START - Then connect to the airflow webserver using IP %EC2PublicIP% and port 8080 and do the following:
echo Create the aws_rds connection ID for the RDS Instance Endpoint: %RDSInstanceEndpoint%
echo create the aws_default connection
echo Creating the environment variable for the RDS Cluster ID named rds_cluster_id: %RDSInstanceIdentifier%
echo create the environment variables: x_bearer_token, aws_access_key_id, aws_secret_access_key
