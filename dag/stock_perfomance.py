from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
from airflow.providers.amazon.aws.operators.rds import RDSDataExecuteStatementOperator
from datetime import datetime
from stock_helper_functions import x_fetcher, x_transformer, x_insertor, x_sentiment, x_overall_popular_sentiment, \
stock_fetcher, stock_transformer, stock_insertor, data_joiner, sns_alert
from airflow.models import Variable


pg_user = Variable.get("pg_user")
pg_pass = Variable.get("pg_pass")
rds_cluster_id  = Variable.get("rds_cluster_id")

# Define the default_args for the DAG
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 1
}

# Define the DAG
stock_perfomance = DAG(
    'stock_performance',
    default_args=default_args,
    description='DAG for stock performance',
    schedule_interval='@hourly'#,
    #on_failure_callback= sns_alert("failure"),
    #on_success_callback= sns_alert("success")
)

# Define the tasks
fetch_most_popular_tweets = PythonOperator(
    task_id='fetch_most_popular_tweets',
    python_callable=x_fetcher,
    dag=stock_perfomance
)

stage_most_popular_tweets = S3CreateObjectOperator(
    task_id='stage_most_popular_tweets',
    aws_conn_id='aws_default',
    s3_bucket='tweets-mbd',
    s3_key="{{ macros.datetime.now().strftime('%Y-%m-%dT%H:%M:%S') }}.json",
    data="{{ task_instance.xcom_pull(task_ids='fetch_most_popular_tweets') }}",
    replace=True,
    dag=stock_perfomance
    )

transform_most_popular_tweets = PythonOperator(
    task_id='transform_most_popular_tweets',
    python_callable=lambda: x_transformer(fetch_most_popular_tweets.output),
    dag=stock_perfomance
)

insert_transformed_tweets = PythonOperator(
    task_id='insert_transformed_tweets',
    python_callable=lambda: x_insertor(transform_most_popular_tweets.output),
    dag=stock_perfomance
)

sentiment_analysis_of_tweets = PythonOperator(
    task_id='sentiment_analysis_of_tweets',
    python_callable=lambda: x_sentiment(transform_most_popular_tweets.output),
    dag=stock_perfomance
)

overall_popular_sentiment = PythonOperator(
    task_id='overall_popular_sentiment',
    python_callable=lambda: x_overall_popular_sentiment(sentiment_analysis_of_tweets.output),
    dag=stock_perfomance
)

fetch_stockprice_data = PythonOperator(
    task_id='fetch_stockprice_data',
    python_callable=stock_fetcher,
    dag=stock_perfomance
)

stage_stockprice_data = S3CreateObjectOperator(
    task_id='stage_stockprice_data',
    aws_conn_id='aws_default',
    s3_bucket='stockprices-mbd',
    s3_key="{{ macros.datetime.now().strftime('%Y-%m-%dT%H:%M:%S') }}.json",
    data="{{ task_instance.xcom_pull(task_ids='fetch_stockprice_data') }}",
    replace=True,
    dag=stock_perfomance
    )

transform_stockprice_data = PythonOperator(
    task_id='transform_stockprice_data',
    python_callable=lambda: stock_transformer(fetch_stockprice_data.output),
    dag=stock_perfomance
)

insert_transformed_stockprice = PythonOperator(
    task_id='insert_transformed_stockprice',
    python_callable=lambda: stock_insertor(transform_stockprice_data.output),
    dag=stock_perfomance
)

join_aggregated_data = PythonOperator(
    task_id='join_aggregated_data',
    python_callable=lambda: data_joiner(overall_popular_sentiment.output, transform_stockprice_data.output),
    dag=stock_perfomance
)

load_aggregated_data = RDSDataExecuteStatementOperator(
    task_id='load_aggregated_data',
    sql="""
        CREATE TABLE IF NOT EXISTS stock_performance (
            datetime TIMESTAMP,
            stock_name VARCHAR(255),
            popular_sentiment VARCHAR(255),
            price REAL,
            ticker VARCHAR(255),
            volume BIGINT
        );
        INSERT INTO stock_performance (datetime, stock_name, popular_sentiment, price, ticker, volume) \
        VALUES (:datetime, :stock_name, :popular_sentiment, :price, :ticker, :volume);
    """,
    parameters=[
        {'name': 'datetime', 'value': {'stringValue': '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["datetime"] }}'}},
        {'name': 'stock_name', 'value': {'stringValue': '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["stock_name"] }}'}},
        {'name': 'popular_sentiment', 'value': {'stringValue': '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["popular_sentiment"] }}'}},
        {'name': 'price', 'value': {'doubleValue': '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["price"] }}'}},
        {'name': 'ticker', 'value': {'stringValue': '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["ticker"] }}'}},
        {'name': 'volume', 'value': {'longValue': '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["volume"] }}'}}
    ],
    database= 'postgres',
    resource_arn= f'arn:aws:rds:us-east-1:123456789012:cluster:{rds_cluster_id}',
    username = pg_user,
    password = pg_pass,
    aws_conn_id='aws_rds',
    dag=stock_perfomance
)

# Set up the task dependencies
fetch_most_popular_tweets >> stage_most_popular_tweets >> transform_most_popular_tweets >> \
insert_transformed_tweets >> sentiment_analysis_of_tweets >> overall_popular_sentiment

fetch_stockprice_data >> stage_stockprice_data >> transform_stockprice_data >> insert_transformed_stockprice

overall_popular_sentiment >> join_aggregated_data >> load_aggregated_data
insert_transformed_stockprice >> join_aggregated_data