-- Media Vault Grafana views (PostgreSQL)
-- 假設表名與 SQLite schema 一致。

CREATE OR REPLACE VIEW mv_ingest_hourly AS
SELECT
    date_trunc('hour', ingested_at::timestamptz) AS bucket,
    COUNT(*) AS ingest_count
FROM unified_posts
WHERE ingested_at >= NOW() - INTERVAL '24 hours'
GROUP BY 1
ORDER BY 1;

CREATE OR REPLACE VIEW mv_compliance_dist AS
SELECT compliance_basis AS label, COUNT(*) AS post_count
FROM unified_posts
GROUP BY compliance_basis;

CREATE OR REPLACE VIEW mv_storage_by_platform AS
SELECT
    p.platform,
    COALESCE(SUM(a.byte_size), 0)::bigint AS total_bytes
FROM unified_posts p
LEFT JOIN media_assets a ON a.post_id = p.id
GROUP BY p.platform;

CREATE OR REPLACE VIEW mv_risk_dist AS
SELECT risk_level, COUNT(*) AS post_count
FROM unified_posts
GROUP BY risk_level;
