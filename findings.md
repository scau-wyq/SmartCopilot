# Docker 部署调研记录

用于记录仓库现状、配置映射和实现决策。

## 仓库现状
- 后端入口：`app.main:app`，生产端口可使用 8081。
- 后端配置已覆盖 MySQL、Redis、Elasticsearch、Kafka、MinIO，容器内只需把主机名改为 Compose 服务名。
- Kafka 文件处理消费者是独立入口 `python -m app.workers.file_processing_worker`，必须作为单独 Worker 服务运行。
- 前端生产 API 为 `/api/v1`，WebSocket 为 `/chat/{token}`，适合由 Nginx 同域反向代理。
- MySQL schema 位于 `docs/sql/create_table.sql`；原有种子存在空库无法创建组织、重跑会重复套餐的问题，现已将种子统一迁移到幂等初始化任务。
- 后端没有自动建表或迁移流程，应由一次性初始化容器负责幂等建表和种子数据。
- Docker CLI 与 Compose 已安装；当前受限会话不能连接本机 Docker Engine，静态配置校验仍可执行，实际构建需要获得 Docker Engine 权限。

## 部署设计
- 固定基础服务版本：MySQL 8.4 LTS、Redis 7.4、Kafka 3.9、Elasticsearch 8.17、MinIO 2025-07-18 发行版。
- 使用命名卷持久化数据库、缓存、Kafka 日志、ES 索引和 MinIO 对象。
- 只把前端 HTTP 端口和可选的 MinIO Console 映射到宿主机；数据库端口默认不公开。
- 使用 `service_healthy` 和 `service_completed_successfully` 消除基础设施、初始化和应用之间的启动竞争。
- 初始化脚本读取管理员账号密码环境变量，生成 bcrypt 密码并幂等写入管理员、默认组织、私人组织及充值套餐。

## 官方资料核对
- Docker Compose 官方文档确认 `service_healthy` 和 `service_completed_successfully` 可用于可靠启动顺序。
- 官方镜像信息确认 MySQL 8.4、Redis 7.4、Apache Kafka 3.9.2 和 MinIO 2025-07-18 标签可用。
