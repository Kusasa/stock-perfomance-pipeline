FROM apache/airflow:2.10.3

# Switch to root to install necessary packages
USER root

# Install required utilities including wget
RUN apt-get update && apt-get install -y wget

# Install Anaconda
RUN wget https://repo.anaconda.com/archive/Anaconda3-2023.03-Linux-x86_64.sh -O ~/anaconda.sh && \
    bash ~/anaconda.sh -b -p /opt/anaconda && \
    rm ~/anaconda.sh && \
    /opt/anaconda/bin/conda init

# Set the conda path
ENV PATH /opt/anaconda/bin:$PATH
ENV PATH /home/airflow/.local/lib/python3.12/site-packages/:$PATH

# Copy the requirements file
COPY requirements.txt /requirements.txt

# Install the Python packages
RUN pip install --upgrade pip && \
    pip install -r /requirements.txt

# Copy the example X json response
COPY examples/most_popular_tweets_2024-12-07T21_17_35.json /opt/airflow/dags/most_popular_tweets_2024-12-07T21_17_35.json
RUN chmod +rx /opt/airflow/dags/most_popular_tweets_2024-12-07T21_17_35.json