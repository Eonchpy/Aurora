# AuroraKB 核心价值设计方案

**创建时间**: 2025-12-17
**状态**: 设计阶段
**目标**: 解决 Multi-Agent 开发中的真实痛点

---

## 一、真实痛点分析

### 痛点 1: 跨平台/跨 Agent 记忆共享

**场景描述**：
```
在 Claude Code 中：
你："重构 authentication 模块，决定用 JWT + Redis session"
Claude："好的，已实现。架构决策已记录。"

切换到 Cursor/Windsurf：
你："继续开发登录功能"
AI："请问你们的 auth 方案是什么？" ❌

理想情况：
AI 自动知道："项目使用 JWT + Redis session" ✅
```

**根本原因**：
- 每个 AI agent 都是独立的对话上下文
- 没有共享的项目知识层
- 用户需要反复说明项目背景

**现有方案的问题**：
- **手动文档**：需要持续维护，容易过时
- **总结传递**：让 A agent 总结，复制给 B agent，繁琐
- **Mem0**：Python SDK，不是 MCP 原生，各 agent 需分别集成

---

### 痛点 2: Subagent 记忆丢失

**场景描述**：
```
主对话：
你："帮我分析项目架构，用 Explore agent"
主 Agent："好的，启动 Explore agent..."

Explore agent 启动：
Explore："这个项目用什么技术栈？" ❌
你："（再说一遍）FastAPI + PostgreSQL..."

理想情况：
Explore agent 启动时自动知道：
- 技术栈：FastAPI + PostgreSQL + pgvector
- 架构决策：内嵌后端模式
- 已解决问题：代理配置导致 localhost 连接失败
```

**根本原因**：
- Subagent 每次启动都是全新的上下文
- 无法访问主对话历史
- 重复询问浪费 token 和时间

**现有方案的问题**：
- **手动总结**：每次启动前手动注入上下文，繁琐
- **Mem0**：不针对 subagent 场景优化，召回慢

---

### 痛点 3: 多 Agent 分工协作

**场景描述**：
```
大型项目开发，使用多个专业 Agent 分工：

项目：MyApp (/Users/you/projects/myapp)
├── Claude Code  → 整体架构设计
├── Codex        → 后端开发 (FastAPI)
└── Gemini CLI   → 前端开发 (React)

❌ 当前问题：
- Claude Code 做的架构决策，Codex 不知道
- Codex 实现的 API 接口，Gemini 不知道
- Gemini 的 UI 需求，Claude Code 不知道
- 每个 Agent 都需要重复说明项目背景

✅ 理想情况：
- Claude Code 保存架构决策 → 所有 agents 自动看到
- Codex 保存 API 文档 → Gemini 自动调用正确的 endpoints
- Gemini 保存 UI 组件 → Claude Code 可以规划整体结构
- 所有决策和实现自动共享，无缝协作
```

**实际工作流**：
```
第1天 - Claude Code:
你: "设计前后端分离架构，FastAPI + React"
Claude: "已保存架构决策到 AuroraKB"

第2天 - Codex (在 backend/ 目录):
你: "实现用户认证 API"
Codex: [自动读取架构决策] "我看到用 FastAPI，会实现 /api/auth/login"
Codex: "已保存 API 文档到 AuroraKB"

第3天 - Gemini (在 frontend/ 目录):
你: "创建登录页面"
Gemini: [自动读取 API 文档] "我看到后端有 POST /api/auth/login，会调用这个"
Gemini: "已保存 UI 组件到 AuroraKB"

第4天 - 切回 Claude Code:
你: "整体进度如何？"
Claude: [搜索所有实现] "后端已完成认证 API，前端已完成登录页面..."
```

**根本原因**：
- 不同 AI agents 在同一项目的不同模块工作
- 缺少统一的项目知识共享层
- 决策和实现分散，难以追踪

**现有方案的问题**：
- **Confluence/Notion**：需要手动维护，容易过时
- **Git commit messages**：粒度粗，不包含设计思路
- **Slack/文档**：碎片化，难以检索

---

## 二、AuroraKB 的差异化定位

### 不是什么 ❌

- **不是** ChatGPT 式的对话记忆系统
- **不是** Mem0 的竞品（个人助理记忆）
- **不是** 通用知识库

### 是什么 ✅

**"Multi-Agent 协作的共享项目上下文层"**

**核心价值主张**：
> Stop repeating yourself across Claude Code, Cursor, and Windsurf.
> Shared context layer for AI coding assistants via MCP.

### 与 Mem0 的对比

| 维度 | Mem0 | AuroraKB |
|------|------|----------|
| **目标场景** | 个人助理记忆 | 项目协作上下文 |
| **优化对象** | 用户偏好、习惯 | 架构决策、问题解决 |
| **协议** | Python SDK | **MCP-native** ✅ |
| **跨平台** | 需要各自集成 | **原生支持** ✅ |
| **召回速度** | 慢（多层记忆） | **快（单层向量）** ✅ |
| **部署** | 复杂（多服务） | **简单（单 PostgreSQL）** ✅ |
| **决策追踪** | 无 | **专门优化** ✅ |

**关系**: 不是替代，是互补
- Mem0: "你喜欢什么编码风格、个人偏好"
- AuroraKB: "这个项目的架构决策、已解决问题"

---

## 三、技术方案（简化版）

### 设计原则

**YAGNI (You Aren't Gonna Need It)**：
- ❌ 不做复杂的 Session 管理系统
- ❌ 不做访问频率统计
- ❌ 不做 TF-IDF 关键词提取
- ✅ 只做解决痛点的最小功能

### 核心机制

#### 3.1 自动项目上下文标记

**无需 Session 表，只需两个字段**：

```sql
-- 在现有 documents 表增加字段
ALTER TABLE documents
  ADD COLUMN project_path TEXT,        -- 项目路径（自动获取）
  ADD COLUMN priority_level INTEGER DEFAULT 1;  -- 优先级

-- 索引
CREATE INDEX idx_documents_project_path ON documents(project_path);
CREATE INDEX idx_documents_priority ON documents(priority_level DESC);
```

**自动生成逻辑**：

```python
import os
import hashlib
from datetime import datetime

def auto_generate_context():
    """自动生成项目上下文标识"""
    # 从当前工作目录获取项目路径
    project_path = os.getcwd()

    # 生成简短哈希（用于显示）
    path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]

    # 日期（用于时间隔离）
    date = datetime.now().strftime("%Y%m%d")

    return {
        "project_path": project_path,
        "session_tag": f"{path_hash}_{date}",  # 可选的显示标签
    }
```

#### 3.2 文档类型优先级

```python
# aurora_api/config.py

DOCUMENT_TYPE_PRIORITY = {
    "decision": 3,      # 架构决策（最高优先级）
    "resolution": 2,    # 已解决问题
    "context": 1,       # 项目背景
    "conversation": 0,  # 普通对话
}

# 示例
{
    "content": "决定使用 JWT + Redis session 实现认证",
    "document_type": "decision",  # → priority_level = 3
    "project_path": "/Users/you/projects/app"
}
```

#### 3.3 增强搜索（简单 Boost）

```python
# aurora_api/services/search.py

async def search_with_project_context(
    query: str,
    current_project_path: str = None,
    boost_same_project: float = 1.5,    # 同项目文档 × 1.5
    boost_by_priority: bool = True,     # 按优先级加权
    limit: int = 10
):
    """基于项目上下文的搜索"""

    # 1. 向量相似度搜索（基础）
    base_results = await vector_search(query, limit=limit*2)

    # 2. 简单后处理 boost
    for doc in base_results:
        score = doc["similarity_score"]

        # 同项目 boost
        if current_project_path and doc["project_path"] == current_project_path:
            score *= boost_same_project

        # 优先级 boost
        if boost_by_priority:
            priority = DOCUMENT_TYPE_PRIORITY.get(doc["document_type"], 0)
            score *= (1 + priority * 0.2)  # decision: +60%, resolution: +40%

        doc["final_score"] = score

    # 3. 重新排序
    results = sorted(base_results, key=lambda x: x["final_score"], reverse=True)

    return results[:limit]
```

#### 3.4 Subagent 上下文注入 Hook

```python
# aurora_mcp/server.py

@mcp.resource("project://context")
async def get_project_context():
    """Subagent 可以调用的项目上下文资源"""
    project_path = os.getcwd()

    # 快速获取相关决策和解决方案
    context_docs = await search_with_project_context(
        query="architecture tech stack decisions",
        current_project_path=project_path,
        document_types=["decision", "resolution"],
        limit=5
    )

    return {
        "project_path": project_path,
        "key_decisions": [doc["content"] for doc in context_docs],
        "tech_stack": extract_tech_stack(context_docs)
    }
```

#### 3.5 多 Agent 协作支持

**项目根目录统一识别**：

```python
import os

def find_project_root(start_path: str = None) -> str:
    """
    向上查找项目根目录，解决不同 agent 在不同子目录工作的问题

    Claude Code 在: /Users/you/projects/myapp
    Codex 在:       /Users/you/projects/myapp/backend
    Gemini 在:      /Users/you/projects/myapp/frontend

    统一识别为: /Users/you/projects/myapp
    """
    current = start_path or os.getcwd()

    while current != '/':
        # 检查项目根目录标识
        if os.path.exists(os.path.join(current, '.git')):
            return current
        if os.path.exists(os.path.join(current, 'pyproject.toml')):
            return current
        if os.path.exists(os.path.join(current, 'package.json')):
            return current

        current = os.path.dirname(current)

    return os.getcwd()  # fallback
```

**自动 Agent 标识（可选）**：

```python
# aurora_mcp/tools/ingest.py

async def run(client, **kwargs):
    """自动添加 agent 标识和项目路径"""
    metadata = kwargs.get("metadata", {})

    # 可选：从环境变量自动获取 agent ID
    agent_id = os.getenv("AURORA_AGENT_ID")
    if agent_id:
        metadata["author"] = agent_id

    metadata["timestamp"] = datetime.now().isoformat()

    # 统一项目路径
    if not kwargs.get("project_path"):
        kwargs["project_path"] = find_project_root()

    kwargs["metadata"] = metadata
    return await client.ingest(kwargs)
```

**就这么简单！**

不需要复杂的 namespace 隔离、角色过滤等机制。向量搜索的语义相似度已经足够智能：
- Gemini 搜 "login API" → 自然找到 Codex 保存的 API 文档
- Codex 搜 "UI components" → 自然找到 Gemini 保存的组件
- 所有内容在同一个 project_path 下，自动共享

---

## 四、实现计划

### 阶段 1: 核心功能（半天，2-3 小时）

**数据库迁移**：
```bash
# scripts/migrations/add_project_context.sql
ALTER TABLE documents ADD COLUMN project_path TEXT;
ALTER TABLE documents ADD COLUMN priority_level INTEGER DEFAULT 1;
CREATE INDEX idx_documents_project_path ON documents(project_path);
CREATE INDEX idx_documents_priority ON documents(priority_level DESC);
```

**修改 Ingest**：
```python
# aurora_api/api/ingest.py
async def ingest_document(request: IngestRequest):
    # 自动添加项目路径
    if not request.project_path:
        request.project_path = os.getcwd()

    # 自动设置优先级
    priority = DOCUMENT_TYPE_PRIORITY.get(request.document_type, 1)

    # 保存
    doc = Document(
        content=request.content,
        project_path=request.project_path,
        priority_level=priority,
        ...
    )
```

**增强 Search**：
```python
# aurora_api/api/search.py
async def search_documents(request: SearchRequest):
    # 自动获取当前项目
    current_project = os.getcwd()

    # 使用项目上下文搜索
    results = await search_with_project_context(
        query=request.query,
        current_project_path=current_project,
        boost_same_project=1.5,
        ...
    )
```

**更新 MCP 工具**：
```python
# aurora_mcp/tools/ingest.py
INPUT_SCHEMA = {
    "content": {...},
    "namespace": {...},
    "document_type": {
        "type": "string",
        "enum": ["decision", "resolution", "context", "conversation"],
        "description": "文档类型: decision=架构决策, resolution=已解决问题"
    },
    "project_path": {
        "type": "string",
        "description": "项目路径（可选，默认自动获取当前目录）"
    }
}
```

### 阶段 2: 使用体验优化（1 天）

**简化部署**：
```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: aurora_kb
      POSTGRES_USER: aurora_user
      POSTGRES_PASSWORD: aurora_pass
    ports:
      - "5432:5432"
    volumes:
      - aurora_data:/var/lib/postgresql/data

volumes:
  aurora_data:
```

**使用文档**：
```markdown
# USAGE_GUIDE.md

## 快速开始

1. 启动数据库
   docker-compose up -d

2. 配置 MCP (所有 AI agent 共享同一配置)
   见 mcp_config_example.json

3. 使用示例
   - 保存决策: "总结刚才的架构决策并保存，类型设为 decision"
   - 跨 agent: 切换到另一个 agent，它会自动看到决策
   - Subagent: 启动 subagent 前会自动注入项目上下文
```

### 阶段 3: 验证和演示（1 天）

**录制演示视频**：
1. 场景 1: 在 Claude Code 中做决策 → 保存
2. 场景 2: 切换到 Cursor → 自动读取
3. 场景 3: 启动 Explore subagent → 自动注入上下文

**性能测试**：
- 搜索延迟 < 200ms
- 1000 条文档下的召回准确率
- Boost 算法的效果验证

---

## 五、使用场景示例

### 场景 1: 跨 Agent 决策共享

**在 Claude Code 中**：
```
你: "我们决定用 FastAPI + PostgreSQL + pgvector 架构，
     用内嵌后端模式简化部署。请总结并保存这个决策。"

Claude: "好的，我会保存这个架构决策。"
[调用 aurora_ingest]
{
  "content": "架构决策: FastAPI + PostgreSQL + pgvector，内嵌后端模式...",
  "document_type": "decision",
  "project_path": "/Users/you/projects/AuroraKB"
}
✅ 已保存，priority_level=3
```

**切换到 Cursor**：
```
你: "继续开发数据库连接模块"

Cursor: [自动搜索项目上下文]
"我看到项目使用 FastAPI + PostgreSQL + pgvector 架构，
 采用内嵌后端模式。我会按照这个架构继续开发..."
```

### 场景 2: Subagent 上下文注入

**主对话**：
```
你: "用 Explore agent 分析代码结构"

Claude: "启动 Explore agent..."
[注入项目上下文]
```

**Explore agent 自动获得**：
```json
{
  "project_path": "/Users/you/projects/AuroraKB",
  "key_decisions": [
    "架构: FastAPI + PostgreSQL + pgvector",
    "部署: 内嵌后端模式",
    "已解决: httpx 代理问题 (trust_env=False)"
  ],
  "tech_stack": {
    "backend": "FastAPI",
    "database": "PostgreSQL + pgvector",
    "mcp": "FastMCP"
  }
}
```

**Explore agent**：
```
"我看到项目使用 FastAPI 架构，已启用 pgvector 扩展。
 我会重点分析 aurora_api/ 和 aurora_mcp/ 模块..."
```

### 场景 3: 问题解决历史

**遇到问题**：
```
你: "localhost 连接一直失败，503 错误"

Claude: [搜索 project_path + "503" + "localhost"]
"我找到相关的已解决问题:
 之前遇到过 httpx 代理问题，解决方案是设置 trust_env=False"
```

### 场景 4: 多 Agent 团队协作（完整流程）

**项目背景**：
```
项目: MyApp (/Users/you/projects/myapp)
目标: 开发全栈应用
团队: Claude Code + Codex + Gemini CLI
```

#### 第 1 天：Claude Code - 架构设计

**在项目根目录** (`/Users/you/projects/myapp`):

```
你: "设计一个前后端分离的全栈应用架构，并保存关键决策"

Claude Code:
[规划架构...]
"好的，我会保存以下架构决策："

[调用 aurora_ingest]
{
  "content": "架构决策\n
    - 前后端分离架构\n
    - 后端: FastAPI + PostgreSQL + Redis\n
    - 前端: React + TypeScript + Vite\n
    - 通信: REST API + WebSocket (实时功能)\n
    - 认证: JWT tokens (access + refresh)\n
    - 部署: Docker Compose",

  "namespace": "myapp",  # 简单使用项目名
  "document_type": "decision",
  "project_path": "/Users/you/projects/myapp",
  "metadata": {
    "author": "claude_code",
    "scope": "architecture",
    "date": "2025-12-17"
  }
}
✅ 已保存 (priority_level=3)
```

#### 第 2 天：Codex - 后端开发

**切换到后端目录** (`/Users/you/projects/myapp/backend`):

```
你: "实现用户认证 API"

Codex:
[自动搜索 AuroraKB: project_path="/Users/you/projects/myapp" + "authentication"]

找到架构决策:
- "认证用 JWT tokens (access + refresh)"
- "后端用 FastAPI"

Codex: "我看到架构决策是用 JWT + FastAPI，我会实现以下 API..."

[实现代码...]

[调用 aurora_ingest]
{
  "content": "认证 API 实现\n
    端点:\n
    - POST /api/auth/register: 用户注册\n
    - POST /api/auth/login: 返回 JWT access + refresh tokens\n
    - POST /api/auth/refresh: 刷新 access token\n
    - POST /api/auth/logout: 登出（黑名单 token）\n
    \n
    Token 格式:\n
    - access_token: 15分钟过期\n
    - refresh_token: 7天过期\n
    \n
    存储: Redis (token 黑名单)",

  "namespace": "myapp",  # 同一个项目，同一个 namespace
  "document_type": "resolution",
  "project_path": "/Users/you/projects/myapp",  # 自动识别项目根目录
  "metadata": {
    "author": "codex",
    "scope": "backend",
    "component": "auth_api",
    "endpoints": [
      "/api/auth/register",
      "/api/auth/login",
      "/api/auth/refresh",
      "/api/auth/logout"
    ]
  }
}
✅ 已保存 (priority_level=2)
```

#### 第 3 天：Gemini - 前端开发

**切换到前端目录** (`/Users/you/projects/myapp/frontend`):

```
你: "创建登录和注册页面"

Gemini:
[自动搜索 AuroraKB: project_path + "auth API"]

找到后端 API 文档:
- "POST /api/auth/login"
- "POST /api/auth/register"
- "Token 格式: access_token + refresh_token"

Gemini: "我看到后端提供了认证 API，我会创建对应的前端页面..."

[实现代码...]

[调用 aurora_ingest]
{
  "content": "登录注册 UI 实现\n
    组件:\n
    - LoginForm.tsx: 登录表单\n
    - RegisterForm.tsx: 注册表单\n
    - AuthLayout.tsx: 认证页面布局\n
    \n
    API 调用:\n
    - 登录: POST /api/auth/login\n
    - 注册: POST /api/auth/register\n
    \n
    Token 存储:\n
    - access_token: sessionStorage (安全性)\n
    - refresh_token: httpOnly cookie\n
    \n
    路由保护:\n
    - PrivateRoute 组件检查 access_token\n
    - 自动刷新机制 (axios interceptor)",

  "namespace": "myapp",
  "document_type": "resolution",
  "project_path": "/Users/you/projects/myapp",  # 自动识别项目根目录
  "metadata": {
    "author": "gemini",
    "scope": "frontend",
    "component": "auth_ui",
    "depends_on": [
      "POST /api/auth/login",
      "POST /api/auth/register"
    ]
  }
}
✅ 已保存 (priority_level=2)
```

#### 第 4 天：集成测试

**Codex 发现前端需求**:

```
你 (in Codex): "前端需要什么额外的 API 支持？"

Codex:
[搜索 AuroraKB: project_path + "frontend" + "depends_on"]

"我看到前端依赖以下 API:
 - POST /api/auth/login ✅ 已实现
 - POST /api/auth/register ✅ 已实现

 前端使用 sessionStorage 存储 access_token，
 我建议添加 CORS 配置支持..."
```

**Gemini 发现后端变更**:

```
你 (in Gemini): "后端 API 有什么更新？"

Gemini:
[搜索 AuroraKB: project_path + "auth" + "backend"]

"我看到后端最近更新:
 - 添加了 /api/auth/logout 端点
 - Token 黑名单机制 (Redis)

 我会更新前端添加登出功能..."
```

#### 第 5 天：Claude Code - 整体审查

**切回 Claude Code**:

```
你: "项目进度如何？总结一下各模块的状态"

Claude Code:
[搜索 AuroraKB: project_path="/Users/you/projects/myapp"]

"项目进度总结:

📐 架构决策 (by claude_code):
  ✅ 前后端分离架构已确定
  ✅ 技术栈: FastAPI + React + PostgreSQL

🔧 后端实现 (by codex):
  ✅ 认证 API 完成 (4个端点)
  ✅ JWT token 机制实现
  ✅ Redis 黑名单功能

🎨 前端实现 (by gemini):
  ✅ 登录/注册页面完成
  ✅ Token 存储机制
  ✅ 路由保护实现

⚠️ 待办事项:
  - 集成测试
  - CORS 配置
  - 错误处理优化"
```

#### 协作配置示例

**所有 Agents 共享的 MCP 配置**：

```json
// Claude Code 配置
{
  "mcpServers": {
    "aurora_kb": {
      "command": "uv",
      "args": ["run", "python", "-m", "aurora_mcp.server"],
      "cwd": "/path/to/AuroraKB",
      "env": {
        // 数据库配置
        "DATABASE_URL": "postgresql://...",

        // Embedding 配置
        "OPENAI_API_KEY": "sk-...",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",  // 可自定义
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "EMBEDDING_DIMENSIONS": "1536",

        // 可选：Agent 标识
        "AURORA_AGENT_ID": "claude_code"
      }
    }
  }
}

// Codex 配置（可选标识）
{
  "env": {
    "AURORA_AGENT_ID": "codex"
  }
}

// Gemini 配置（可选标识）
{
  "env": {
    "AURORA_AGENT_ID": "gemini"
  }
}
```

**关键机制**：

1. **统一项目识别**：`find_project_root()` 确保所有 agents 使用同一 project_path
2. **可选 agent 标识**：`metadata.author` 记录来源（便于追踪）
3. **向量搜索**：自动找到语义相关的内容，无需复杂过滤
4. **优先级排序**：decision > resolution，确保关键信息优先

**就这么简单！** 不需要复杂的 namespace 规则、角色过滤等。

---

## 六、成功指标

### 定量指标

- ✅ 部署时间 < 5 分钟（Docker Compose）
- ✅ 搜索延迟 < 200ms
- ✅ 决策召回准确率 > 90%
- ✅ 跨 agent 上下文丢失率 < 10%

### 定性指标

**单 Agent 使用**：
- ✅ 用户不需要手动管理 namespace
- ✅ Subagent 启动时自动知道项目背景
- ✅ 架构决策自动追踪和召回

**多 Agent 协作**：
- ✅ 不同 agents 在不同子目录工作时自动识别同一项目
- ✅ Claude Code 的决策，Codex/Gemini 自动看到
- ✅ Codex 的 API 文档，Gemini 自动使用
- ✅ 根据 agent 角色自动过滤相关 namespace
- ✅ 所有 agents 无需重复说明项目背景

### 协作效率提升

**预期提升**：
- ⏱️ 上下文重复说明时间：从 5 分钟/次 → 0
- 📈 跨 agent 决策一致性：从 60% → 95%
- 🔄 API 文档同步延迟：从 1 天 → 实时
- 💡 问题解决方案复用率：从 20% → 80%

---

## 七、与之前方案的对比

| 维度 | Session_持久化_MVP | 当前方案 |
|------|-------------------|---------|
| **数据库改动** | +2 张表 | +2 字段 |
| **代码复杂度** | ~500 行 | ~100 行 |
| **实现时间** | 2-3 天 | **半天** ✅ |
| **维护成本** | 高 | **低** ✅ |
| **聚焦痛点** | 不明确 | **清晰** ✅ |
| **过度设计** | 是 | **否** ✅ |

---

## 八、后续可能的扩展

**仅在实际需要时考虑**：

1. **Web UI 查看**：可视化项目决策历史
2. **导出/导入**：Markdown 格式导出决策文档
3. **团队共享**：多用户权限管理
4. **时间衰减**：旧决策降权（如果项目演进快）
5. **决策树**：决策之间的依赖关系可视化

**当前不做**：
- ❌ 访问频率统计
- ❌ TF-IDF 关键词提取
- ❌ 复杂的 SessionContext 关联
- ❌ 多阶段搜索算法

---

## 九、下一步行动

### 立即可做（今天）

1. ✅ 清理旧设计文档
   - 删除或归档 `Session_持久化设计方案_MVP.md`
   - 删除或归档 `CODEX_PROMPT_SESSION_MVP.md`
   - 删除 `ALTERNATIVE_CONFIG_APPROACH.md`

2. ✅ 创建本文档
   - `CORE_VALUE_DESIGN.md`

3. ✅ 更新 README
   - 添加清晰的使用场景说明
   - 强调跨 agent 协作价值

### 本周可做

1. 实现核心功能（2-3 小时）
2. 编写使用文档和示例
3. 测试跨 agent 场景

### 下周可做

1. 录制演示视频
2. 发布到 GitHub
3. 收集早期用户反馈

---

## 十、关键原则

1. **YAGNI**: 只做必要的，不做可能需要的
2. **实用主义**: 先解决痛点，再考虑完美
3. **渐进演进**: 从最小可用版本开始，根据反馈迭代
4. **保持简单**: 复杂度是敌人，简单是美德

---

**文档状态**: 待实现
**预计完成时间**: 2025-12-18
**负责人**: Yourself + Claude
