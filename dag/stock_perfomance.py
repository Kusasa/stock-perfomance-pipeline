from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from datetime import datetime
from stock_helper_functions import x_fetcher, x_transformer, x_insertor, x_sentiment, x_overall_popular_sentiment, \
stock_fetcher, stock_transformer, stock_insertor, data_joiner, sns_alert


# Define the default_args for the DAG
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 12, 1),
    'retries': 0
}

# Define the DAG
stock_perfomance = DAG(
    'stock_performance',
    default_args=default_args,
    description='DAG for stock performance',
    schedule_interval='@hourly',
    catchup=False,
    on_failure_callback= sns_alert("failure"),
    on_success_callback= sns_alert("success")
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
    s3_key="stock_popular_tweets_{{ macros.datetime.now().strftime('%Y-%m-%dT%H:%M:%S') }}.json",
    data="{{ task_instance.xcom_pull(task_ids='fetch_most_popular_tweets') }}",
    replace=True,
    dag=stock_perfomance
    )

transform_most_popular_tweets = PythonOperator(
    task_id='transform_most_popular_tweets',
    python_callable=lambda **kwargs: x_transformer(kwargs['ti'].xcom_pull(task_ids='fetch_most_popular_tweets')),
    provide_context=True,
    dag=stock_perfomance
)

insert_transformed_tweets = PythonOperator(
    task_id='insert_transformed_tweets',
    python_callable=lambda **kwargs: x_insertor(kwargs['ti'].xcom_pull(task_ids='transform_most_popular_tweets')),
    provide_context=True,
    dag=stock_perfomance
)

sentiment_analysis_of_tweets = PythonOperator(
    task_id='sentiment_analysis_of_tweets',
    python_callable=lambda **kwargs: x_sentiment(kwargs['ti'].xcom_pull(task_ids='transform_most_popular_tweets')),
    provide_context=True,
    dag=stock_perfomance
)

overall_popular_sentiment = PythonOperator(
    task_id='overall_popular_sentiment',
    python_callable=lambda **kwargs: x_overall_popular_sentiment(kwargs['ti'].xcom_pull(task_ids='sentiment_analysis_of_tweets')),
    provide_context=True,
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
    s3_key="stock_metrics_{{ macros.datetime.now().strftime('%Y-%m-%dT%H:%M:%S') }}.json",
    data="{{ task_instance.xcom_pull(task_ids='fetch_stockprice_data') }}",
    replace=True,
    dag=stock_perfomance
    )

transform_stockprice_data = PythonOperator(
    task_id='transform_stockprice_data',
    python_callable=lambda **kwargs: stock_transformer(kwargs['ti'].xcom_pull(task_ids='fetch_stockprice_data')),
    provide_context=True,
    dag=stock_perfomance
)

insert_transformed_stockprice = PythonOperator(
    task_id='insert_transformed_stockprice',
    python_callable=lambda **kwargs: stock_insertor(kwargs['ti'].xcom_pull(task_ids='transform_stockprice_data')),
    provide_context=True,
    dag=stock_perfomance
)

join_aggregated_data = PythonOperator(
    task_id='join_aggregated_data',
    python_callable=lambda **kwargs: data_joiner(
        kwargs['ti'].xcom_pull(task_ids='overall_popular_sentiment'),
        kwargs['ti'].xcom_pull(task_ids='transform_stockprice_data')
    ),
    provide_context=True,
    dag=stock_perfomance
)

load_aggregated_data = PostgresOperator(
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
        INSERT INTO stock_performance (datetime, stock_name, popular_sentiment, price, ticker, volume)
        VALUES (
            '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["datetime"] }}',
            '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["stock_name"] }}',
            '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["popular_sentiment"] }}',
            '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["price"] }}',
            '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["ticker"] }}',
            '{{ task_instance.xcom_pull(task_ids="join_aggregated_data")["volume"] }}'
        );
    """,
    postgres_conn_id='aws_rds',
    database='postgres',
    dag=stock_perfomance
)

# Set up the task dependencies
fetch_most_popular_tweets >> stage_most_popular_tweets >> transform_most_popular_tweets >> \
insert_transformed_tweets >> sentiment_analysis_of_tweets >> overall_popular_sentiment

fetch_stockprice_data >> stage_stockprice_data >> transform_stockprice_data >> insert_transformed_stockprice

overall_popular_sentiment >> join_aggregated_data >> load_aggregated_data
insert_transformed_stockprice >> join_aggregated_data