CREATE TABLE IF NOT EXISTS stock_performance (
    datetime TIMESTAMP,
    stock_name VARCHAR(255),
    popular_sentiment VARCHAR(255),
    price REAL,
    ticker VARCHAR(255),
    volume BIGINT
);
