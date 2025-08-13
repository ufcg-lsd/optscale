CREATE TABLE IF NOT EXISTS aws_bucket_intelligent_tiering_info
(
    cloud_account_id String,
    bucket_name String,
    intelligent_tiering_status String,
    tiers Array(String),
    last_checked DateTime
)
ENGINE = MergeTree()
ORDER BY (cloud_account_id, bucket_name);
