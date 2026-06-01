-- 集装箱与堆场管理模块数据库升级脚本
-- 说明：现有 containers 表继续保留；本脚本新增 yards 表，并建议 containers 使用
-- yard / area / column / layer 记录集装箱所在堆场、区域、列、层。

CREATE TABLE IF NOT EXISTS yards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yard_name VARCHAR(30) NOT NULL UNIQUE,
    usage_type VARCHAR(30) DEFAULT '综合堆场',
    zones VARCHAR(200) DEFAULT 'Zone-1,Zone-2,Zone-3,Zone-4',
    total_rows INTEGER DEFAULT 12,
    total_tiers INTEGER DEFAULT 5,
    status VARCHAR(20) DEFAULT '启用',
    remark VARCHAR(200)
);

CREATE INDEX IF NOT EXISTS idx_containers_location
ON containers (yard, area, column, layer);

INSERT OR IGNORE INTO yards (yard_name, usage_type, zones, total_rows, total_tiers, status)
VALUES
('堆场A', '进口箱', 'Zone-1,Zone-2,Zone-3,Zone-4', 12, 5, '启用'),
('堆场B', '出口箱', 'Zone-1,Zone-2,Zone-3,Zone-4', 12, 5, '启用'),
('堆场C', '冷藏箱', 'Zone-1,Zone-2,Zone-3,Zone-4', 12, 5, '启用');
