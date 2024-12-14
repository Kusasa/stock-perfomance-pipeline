# Update and install required packages
sudo apt-get update
sudo apt-get install -y ca-certificates curl

# Create a directory and download the Docker GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc > /dev/null

# Set correct permissions and add Docker repository
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update repositories and install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Change to the pipeline directory and download airflow docker-compose file
cd ~/pipeline
echo -e "AIRFLOW_UID=$(id -u)" > .env

# Build image which has anaconda and the necessary python libraries
sudo docker compose build

# Initialize and start Airflow
sudo docker compose up -d

# Expose configurations on webserver
#sudo docker exec -d pipeline-airflow-webserver-1 /bin/bash -c "rm -f /opt/airflow/airflow-webserver.pid"
#sudo docker exec -d pipeline-airflow-webserver-1 /bin/bash -c "sed -i 's/expose_config = False/expose_config = True/' /opt/airflow/airflow.cfg && exec airflow webserver"

# Install airflow CLI
sudo apt-get update
wget https://repo.anaconda.com/archive/Anaconda3-2023.03-Linux-x86_64.sh -O ~/anaconda.sh && \
sudo bash ~/anaconda.sh -b -p /opt/anaconda && \
sudo rm ~/anaconda.sh && \
sudo /opt/anaconda/bin/conda init bash
source ~/.bashrc
pip install apache-airflow
export PATH="$PATH:/home/ubuntu/.local/bin"
