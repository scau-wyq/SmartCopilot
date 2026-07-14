# SmartCopilot

## 项目介绍

SmartCopilot 是一个面向个人和团队的智能知识助手平台。它将大语言模型与企业或个人知识库结合，让用户能够通过自然语言完成资料检索、文档问答、内容总结和连续对话，减少在大量文件中手动查找信息的时间。

平台支持接入兼容 OpenAI 接口规范的聊天模型和 Embedding 模型。上传的文档经过解析、切分和向量化后写入 Elasticsearch；用户提问时，系统会检索相关知识片段并将其作为上下文交给大语言模型，从而生成更贴近已有资料的回答。

### 核心能力

- 智能对话：支持流式回答、连续会话和上下文记忆。
- 知识库问答：支持文档上传、分片处理、向量检索和回答来源引用。
- 异步文档处理：通过 Kafka 和独立 Worker 处理文档解析及向量化任务。
- 对象存储：使用 MinIO 保存上传文件和合并后的文档对象。
- 用户与组织管理：通过组织标签和私人空间隔离不同用户及团队的知识数据。
- 模型与用量管理：支持免费、付费及自定义模型模式，并记录 LLM 与 Embedding Token 用量。
- 完整 Web 应用：提供 Vue 前端、FastAPI 后端及 WebSocket 实时通信能力。

适用场景包括个人资料助手、团队内部知识库、企业文档问答、产品与技术资料检索，以及基于私有文档的 AI Copilot。

## Docker 一键部署

环境要求：Docker Engine 24+、Docker Compose 2.20+，建议至少 4 核 CPU、8 GB 内存和 15 GB 可用磁盘。

首次部署前复制配置模板并修改密码、JWT 密钥和模型 API 配置：

```powershell
Copy-Item .env.docker.example .env
docker compose up -d --build
```

Linux/macOS：

```bash
cp .env.docker.example .env
docker compose up -d --build
```

启动完成后访问：

- SmartCopilot：`http://localhost:8080`
- MinIO 控制台：`http://localhost:9001`
- 默认管理员：由 `.env` 中的 `INITIAL_ADMIN_USERNAME` 和 `INITIAL_ADMIN_PASSWORD` 指定

管理员密码仅在该用户名首次创建时生效，后续修改 `.env` 不会覆盖数据库中的现有密码。

查看状态和日志：

```bash
docker compose ps
docker compose logs -f backend worker
```

停止服务但保留数据：

```bash
docker compose down
```

删除服务及全部持久化数据（不可恢复）：

```bash
docker compose down -v
```

编排会创建 MySQL、Redis、Kafka、Elasticsearch、MinIO、数据库初始化任务、FastAPI 后端、Kafka Worker 和 Nginx 前端。MySQL 首次创建数据卷时执行 `docs/sql/create_table.sql`；初始化任务随后幂等创建管理员、默认组织、管理员私人组织和默认充值套餐。
