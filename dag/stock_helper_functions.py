import requests
from urllib.parse import quote
import boto3
import json
from datetime import datetime
import re
import yfinance as yf
import numpy as np
import psycopg2
import logging
from airflow.models import Variable
import sys


#-------------------------------------HELPER FUNCTIONS
x_bearer_token = Variable.get("x_bearer_token")
aws_access_key_id = Variable.get("aws_access_key_id")
aws_secret_access_key = Variable.get("aws_secret_access_key")

# A1) X Fetcher
def x_fetcher(stock_name = "#Amazon"):
    query = f'{stock_name} -is:retweet'
    encoded_query = quote(query)
    url = f'https://api.twitter.com/2/tweets/search/recent?query={encoded_query}&tweet.fields=public_metrics&max_results=100'
    
    headers = {
        'Authorization': f'Bearer {x_bearer_token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.get(url, headers=headers)
    
    # Check the response status
    if response.status_code == 200:
        tweets = response.json().get('data', [])
        
        if not tweets:
            print("No tweets found.")
            raise Exception("No tweets found.")
        else:
            # Sort tweets by retweet count to find the most popular one
            most_popular_tweets = sorted(tweets, key=lambda tweet: tweet['public_metrics']['retweet_count'], reverse=True)[0:10]
            
            #print(f"Most popular tweets: {most_popular_tweets['text']}\nRetweets: {most_popular_tweets['public_metrics']['retweet_count']}")
            return most_popular_tweets
    elif response.status_code == 429:
        sys.path.append('/opt/airflow/dags')
        with open("/opt/airflow/dags/most_popular_tweets_2024-12-07T21_17_35.json", 'r') as file: 
            most_popular_tweets = json.load(file)
        return most_popular_tweets
    else:
        print(f"Failed to fetch tweets: {response.status_code} - {response.text}")
        raise Exception(f"Failed to fetch tweets: {response.status_code} - {response.text}")

# A2) Stager
def stager(data,bucket_name, data_name):
    session = boto3.Session(aws_access_key_id, aws_secret_access_key, region_name='us-east-1')
    s3 = session.client('s3')
    
    json_data = json.dumps(data, indent=4)
    
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    file_name = f'{data_name}_{current_time}.json'
    
    s3.put_object(Bucket=bucket_name, Key=file_name,Body=json_data)
    
    print(f"File {file_name} uploaded to {bucket_name} successfully!")
    
# A3) X Transformer
def x_transformer(data, stock_name = "#Amazon"):
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    def transformer(record):
        transformed_record = record["public_metrics"]
        allowed_pattern = r'[^A-Za-z0-9\s.,!?\'-]'
        transformed_record["text"] = re.sub(allowed_pattern, '', record["text"])
        transformed_record["stock_name"] = stock_name
        transformed_record["datetime"] = current_time
        return transformed_record
    
    transformed_data = list(map(transformer, data))
    return transformed_data

# A4) X Insertor
def x_insertor(transformed_data):
    session = boto3.Session(aws_access_key_id, aws_secret_access_key, region_name='us-east-1')
    dynamodb = session.client('dynamodb')
    
    table_name = "tweets-mbd"
    index = 0
    for tweet in transformed_data:
        dynamodb.put_item(
            TableName=table_name,
            Item={
                'datetime': {'S': tweet['datetime'] + "_" + str(index)},
                'stock_name': {'S': tweet['stock_name']},
                'bookmark_count': {'N': str(tweet['bookmark_count'])},
                'impression_count': {'N': str(tweet['impression_count'])},
                'like_count': {'N': str(tweet['like_count'])},
                'quote_count': {'N': str(tweet['quote_count'])},
                'reply_count': {'N': str(tweet['reply_count'])},
                'retweet_count': {'N': str(tweet['retweet_count'])},
                'post': {'S': str(tweet['text'])}
            }
        )
        index += 1
        
# A5) X Sentiment
def x_sentiment(transformed_data):
    session = boto3.Session(aws_access_key_id, aws_secret_access_key, region_name='us-east-1')
    comprehend = session.client('comprehend')
    
    sentiment_data = transformed_data.copy()
    def sentiment_analysis(sentiment_record):
        response = comprehend.detect_sentiment(Text=sentiment_record["text"], LanguageCode='en')
        sentiment_record["sentiment"] = response["Sentiment"]
        sentiment_record["sentiment_positivity"] = response["SentimentScore"]["Positive"]
        sentiment_record["sentiment_neutrality"] = response["SentimentScore"]["Neutral"]
        sentiment_record["sentiment_negativity"] = response["SentimentScore"]["Negative"]
        sentiment_record["sentiment_mixed"] = response["SentimentScore"]["Mixed"]
        
        return sentiment_record
    
    sentiment_data = list(map(sentiment_analysis, sentiment_data))
    
    return sentiment_data

# A6) X Overall Sentiment
def x_overall_popular_sentiment(sentiment_data):
    values, counts = np.unique([sentiment["sentiment"] for sentiment in sentiment_data], return_counts=True)
    mode = str(values[np.argmax(counts)])
    
    overall_sentiment = {}
    overall_sentiment["datetime"] = sentiment_data[0]["datetime"]
    overall_sentiment["stock_name"] = sentiment_data[0]["stock_name"]
    overall_sentiment["popular_sentiment"] = mode
    
    return overall_sentiment

# B1) Stock Fetcher
def stock_fetcher(stock_ticker = "AMZN"):
    stock = yf.Ticker(stock_ticker)
    stock_data = stock.info
    
    return stock_data

# B3) Stock Transformer
def stock_transformer(data):
    transformed_data = {}
    transformed_data["datetime"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    transformed_data["ticker"] = data["symbol"]
    transformed_data["price"] = data["currentPrice"]
    transformed_data["volume"] = data["volume"]
    
    return transformed_data

# B4) Stock Insertor
def stock_insertor(transformed_data):
    session = boto3.Session(aws_access_key_id, aws_secret_access_key, region_name='us-east-1')
    dynamodb = session.client('dynamodb')
    
    table_name = "stockprices-mbd"
    dynamodb.put_item(
        TableName=table_name,
        Item={
            'datetime': {'S': transformed_data['datetime']},
            'stock': {'S': transformed_data['ticker']},
            'price': {'N': str(transformed_data['price'])},
            'volume': {'N': str(transformed_data['volume'])}
        }
    )

# C1) Data Join
def data_joiner(x_stock_sentiment, stockprice):
    combined_data = x_stock_sentiment.copy()
    combined_data["price"] = stockprice["price"]
    combined_data["ticker"] = stockprice["ticker"]
    combined_data["volume"] = stockprice["volume"]
    
    return combined_data

# C2) Data Loader
def data_loader(combined_data):
    host = 'stock-mbd.c9ocw6yo8c4d.us-east-1.rds.amazonaws.com'
    database = 'postgres'
    user = 'postgres'
    password = 'ThisIsSpartan'
    port = 5432
    
    # Establish a connection to the database
    conn = psycopg2.connect(
        host=host,
        database=database,
        user=user,
        password=password,
        port=port
    )
    
    # Create a cursor object
    cur = conn.cursor()
    
    # Define the SQL query to insert data
    insert_query = """
    INSERT INTO stock_performance (datetime, stock_name, popular_sentiment, price, ticker, volume)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    
    # Extract values from the JSON object
    data_to_insert = (combined_data['datetime'], combined_data['stock_name'], \
                    combined_data['popular_sentiment'], combined_data['price'], combined_data['ticker'], \
                    combined_data['volume'])
    
    # Execute the SQL query
    cur.execute(insert_query, data_to_insert)
    
    # Commit the transaction
    conn.commit()
    
    # Close the cursor and connection
    cur.close()
    conn.close()
    
    print("Data inserted successfully.")

# D) Email Alert
def sns_alert(status):
    try:
        session = boto3.Session(aws_access_key_id, aws_secret_access_key, region_name='us-east-1')
        sns = session.client('sns')
        sns.publish(
            TopicArn='arn:aws:sns:us-east-1:008971661443:stock_perfomance_alerts',
            Message=f'Pipeline was a {status.lower()}!',
            Subject=f'Stock_Pipeline_{status}'
        )
        logging.info(f"Pipeline was a {status.lower()}!")
    except Exception as e:
        logging.error(f"Pipeline was a {status.lower()}: {e}")    
    

#-------------------------------------TEST FUNCTIONS
if __name__ == "__main__":
    most_popular_tweets = x_fetcher()
    stager(most_popular_tweets, "tweets-mbd", "most_popular_stock_tweets")
    transformed_tweets = x_transformer(most_popular_tweets)
    x_insertor(transformed_tweets)
    sentiment_of_tweets = x_sentiment(transformed_tweets)
    popular_sentiment = x_overall_popular_sentiment(sentiment_of_tweets)
    
    stockprice_data = stock_fetcher()
    stager(stockprice_data, "stockprices-mbd", "stockprice")
    transformed_stockprice = stock_transformer(stockprice_data)
    stock_insertor(transformed_stockprice)
    
    aggreggated_data = data_joiner(popular_sentiment, transformed_stockprice)
    data_loader(aggreggated_data)