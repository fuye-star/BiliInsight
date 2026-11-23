-- ============================================================
-- BiliInsight MySQL 初始化脚本
-- 由 docker-compose 在首次启动 MySQL 时自动执行
-- （挂载到 /docker-entrypoint-initdb.d/）
-- ============================================================

CREATE DATABASE IF NOT EXISTS biliinsight
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

-- 为应用账号授权（compose 已建号，这里补齐权限）
GRANT ALL PRIVILEGES ON biliinsight.* TO 'bili'@'%';
FLUSH PRIVILEGES;

USE biliinsight;

-- ------------------------------------------------------------
-- 说明：业务表由 Django Migrations 创建
--   python manage.py migrate
-- 此处仅创建扩展与常用索引预留，便于压测对比
-- ------------------------------------------------------------
