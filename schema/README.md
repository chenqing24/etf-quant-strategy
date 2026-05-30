-- ============================================================
-- 数据库初始化脚本
-- 用于创建数据库并执行 schema
-- ============================================================

-- 使用说明：
-- 1. 创建数据库：sqlite3 etf_data_live/etf.db < schema/01_etf_live_schema.sql
-- 2. 创建数据库：sqlite3 data/etf_factors.db < schema/02_etf_factors_schema.sql
-- 3. 如需重建，执行：rm *.db && sqlite3 xxx.db < schema/xxx_schema.sql

-- 示例：
-- cd etf_strategy
-- rm -f etf_data_live/etf.db data/etf_factors.db
-- sqlite3 etf_data_live/etf.db < schema/01_etf_live_schema.sql
-- sqlite3 data/etf_factors.db < schema/02_etf_factors_schema.sql