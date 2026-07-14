# SmartCopilot Docker 一键部署计划

## 目标
在项目根目录提供可重复、可配置的一键部署方案，启动 MySQL、Kafka、Redis、Elasticsearch、MinIO、后端和前端，并自动完成数据库表结构与基础数据初始化。

## 阶段
- [complete] 1. 盘点现有服务配置、构建方式、SQL 和运行依赖
- [complete] 2. 设计容器拓扑、健康检查、数据卷、网络和环境变量
- [complete] 3. 编写前后端镜像、反向代理配置和 Compose 编排
- [complete] 4. 接入数据库结构及基础数据的幂等初始化
- [complete] 5. 补充环境模板、启动说明与安全提示
- [complete] 6. 校验 Compose 配置、镜像构建和服务启动链路（实际镜像拉取受宿主机镜像源 HTTP 429 限流，已完成其余校验）

## 关键决策
- 默认入口采用 `docker compose up -d --build`，避免通过 Docker Socket 让单个 `docker run` 容器控制宿主机。
- 所有密码和端口通过项目根目录 `.env` 配置，不在镜像中硬编码生产凭据。
- 基础设施必须通过健康检查后，应用容器才启动。

## 错误记录
| 错误 | 次数 | 处理方式 |
|---|---:|---|
| 补丁无法自动创建 `src/app/scripts` 多层目录 | 1 | 改为放在已有包目录 `src/app/init_database.py`，避免目录创建权限问题 |
| Docker 基础镜像拉取返回 HTTP 429 | 1 | 宿主机 `docker.xuanyuan.me` 免费镜像源限流；停止重复拉取，保留静态与本地构建验证结果 |
