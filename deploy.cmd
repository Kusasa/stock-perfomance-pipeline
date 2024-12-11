@echo off

REM Created and subscribe to SNS Alert
aws sns create-topic --name stock_perfomance_alerts --region us-east-1
aws sns subscribe --topic-arn arn:aws:sns:us-east-1:008971661443:stock_perfomance_alerts --protocol email --notification-endpoint skusasalethu@gmail.com

REM Create authentication key
aws ec2 create-key-pair --key-name stock_perfomance_key --query 'KeyMaterial' --output text > stock_perfomance_key.pem
chmod 400 stock_perfomance_key.pem

REM Deploy pipeline stack
aws cloudformation create-stack --stack-name stock_perfomances_infra --template-body file://infrastructure/pipeline_infra.yml --region us-east-1
aws cloudformation wait stack-create-complete --stack-name stock_perfomances_infra

REM Capture output values from the stack deployment as variables
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name stock_perfomances_infra --query "Stacks[0].Outputs[?OutputKey==`'EC2PublicIP`'].OutputValue" --output text') do set EC2PublicIP=%%i
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name stock_perfomances_infra --query "Stacks[0].Outputs[?OutputKey==`'RDSInstanceEndpoint`'].OutputValue" --output text') do set RDSInstanceEndpoint=%%i
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name stock_perfomances_infra --query "Stacks[0].Outputs[?OutputKey==`'RDSInstanceIdentifier`'].OutputValue" --output text') do set RDSInstanceIdentifier=%%i

REM Connect to the EC2 instance using SSH and create the home directory of the pipeline
ssh -i "stock_perfomance_key.pem" ubuntu@%EC2PublicIP% "mkdir -p ~/pipeline ~/pipeline/dags ~/pipeline/logs ~/pipeline/plugins"

REM Copy dag folder with its contents to the dags folder in the remote server
scp -i "stock_perfomance_key.pem" -r .\dag ubuntu@%EC2PublicIP%:~/pipeline/dags

REM Connect to the remote server, install docker engine and deploy the airflow docker containers with its required libraries
ssh -i "stock_perfomance_key.pem" ubuntu@%EC2PublicIP% << 'EOF'

sudo apt-get update
sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

cd ~/pipeline
echo -e "AIRFLOW_UID=$(id -u)" > .env
curl -LfO 'https://airflow.apache.org/docs/apache-airflow/stable/docker-compose.yaml'

docker-compose up airflow-init
docker-compose up -d

REM Connect to the airflow-webserver-1 container and install necessary packages
docker exec -it airflow-webserver-1 /bin/bash << 'EOC'

curl -O https://repo.anaconda.com/archive/Anaconda3-2023.03-Linux-x86_64.sh
bash Anaconda3-2023.03-Linux-x86_64.sh -b
echo 'export PATH=~/anaconda3/bin:$PATH' >> ~/.bashrc
source ~/.bashrc

conda install -c conda-forge awscli
conda install -c conda-forge airflow
pip install apache-airflow-providers-amazon
pip install yfinance --upgrade --no-cache-dir

exit
EOC

exit
EOF

REM Set airflow connections and variables
echo Connect to the airflow webserver using ip %EC2PublicIP% and port 8080 and do the following:
echo Create the aws_rds connection id for the RDS Instance Endpoint: %RDSInstanceEndpoint%
echo create the aws_default connection
echo Create the environment variable for the RDS Cluster ID named rds_cluster_id: %RDSInstanceIdentifier%
echo create the environment variables: x_bearer_token,  aws_access_key_id, aws_secret_access_key, pg_user, pg_pass