# AuroraKB 可移植性改进方案

## 当前问题分析

### 硬依赖清单

#### 1. PostgreSQL 特定代码

**位置**: `aurora_api/database.py:48`
```python
await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
```
- 依赖 PostgreSQL 扩展系统
- 其他数据库无法执行

**位置**: `aurora_api/services/search.py:38`
```python
distance_expr = func.cosine_distance(Document.embedding_vector, query_vector)
```
- pgvector 专有函数 `cosine_distance`
- SQLite/MySQL 等不支持

**位置**: `aurora_api/models/document.py:18`
```python
from pgvector.sqlalchemy import Vector
embedding_vector = Column(Vector(1536), nullable=False)
```
- pgvector 特定数据类型
- 不可跨数据库迁移

#### 2. 部署复杂度

- ❌ 需要手动安装 PostgreSQL 17
- ❌ 需要安装 pgvector 扩展（编译或包管理器）
- ❌ 需要配置数据库用户权限
- ❌ Docker 部署需要自定义镜像（postgres + pgvector）

#### 3. 受限场景

- ❌ **云服务受限**: AWS RDS/Azure 等托管数据库可能不支持 pgvector
- ❌ **边缘部署**: 嵌入式设备难以运行 PostgreSQL
- ❌ **快速原型**: 新用户需要复杂的环境配置
- ❌ **单元测试**: 需要真实 PostgreSQL 实例

---

## 改进方案对比

### 方案 1: 数据库抽象层（推荐）

**适用场景**: 需要支持多种部署环境

#### 架构设计

```
┌─────────────────────────────────────────────┐
│         FastAPI Service Layer              │
└───────────────┬─────────────────────────────┘
                ▼
┌─────────────────────────────────────────────┐
│      VectorStore Abstract Interface         │
│  • ingest()  • search()  • retrieve()       │
└───────────────┬─────────────────────────────┘
                ▼
    ┌───────────┴──────────────┬──────────────┐
    ▼                          ▼              ▼
┌──────────┐        ┌──────────────┐   ┌──────────┐
│PostgreSQL│        │   Pinecone   │   │  Chroma  │
│+pgvector │        │   (Cloud)    │   │ (Embed)  │
└──────────┘        └──────────────┘   └──────────┘
```

#### 实现步骤

**Step 1**: 定义抽象接口
```python
# aurora_api/vector_stores/base.py
from abc import ABC, abstractmethod

class VectorStore(ABC):
    @abstractmethod
    async def ingest(self, content: str, embedding: List[float],
                    namespace: str, metadata: dict) -> UUID:
        pass

    @abstractmethod
    async def search(self, query_embedding: List[float],
                    limit: int, filters: dict) -> List[dict]:
        pass

    @abstractmethod
    async def retrieve(self, doc_id: UUID) -> dict:
        pass
```

**Step 2**: 实现 PostgreSQL 后端（保持当前功能）
```python
# aurora_api/vector_stores/postgres.py
class PostgresVectorStore(VectorStore):
    """Current implementation, no breaking changes"""
    async def search(self, query_embedding, limit, filters):
        # 使用 pgvector 的 cosine_distance
        return await self._pg_vector_search(...)
```

**Step 3**: 实现轻量级后端（快速原型）
```python
# aurora_api/vector_stores/chroma.py
class ChromaVectorStore(VectorStore):
    """Embedded vector DB, no external dependencies"""
    async def search(self, query_embedding, limit, filters):
        # ChromaDB 自带向量搜索
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit
        )
```

**Step 4**: 配置化选择
```env
# .env
VECTOR_STORE_BACKEND=postgres  # 或 chroma, pinecone, weaviate
```

#### 优点
- ✅ 向后兼容：PostgreSQL 作为默认后端
- ✅ 灵活部署：可选轻量级后端（Chroma/SQLite-VSS）
- ✅ 云原生：支持托管服务（Pinecone/Weaviate）
- ✅ 易测试：可用内存后端做单元测试

#### 缺点
- ⚠️ 增加代码复杂度（约 +30% 代码量）
- ⚠️ 需要维护多个后端实现
- ⚠️ 性能差异（不同后端的向量索引效率不同）

---

### 方案 2: Docker 一键部署（最小改动）

**适用场景**: 只需简化部署，不需要切换数据库

#### 实现方式

**创建预构建镜像**:
```dockerfile
# Dockerfile.postgres
FROM pgvector/pgvector:pg17

# 预配置数据库
COPY database/migrations/*.sql /docker-entrypoint-initdb.d/
ENV POSTGRES_DB=aurora_kb
ENV POSTGRES_USER=aurora_user
ENV POSTGRES_PASSWORD=aurora_pass
```

**一键启动**:
```yaml
# docker-compose.yml
services:
  postgres:
    image: aurorakb/postgres:latest  # 预构建镜像

  api:
    image: aurorakb/api:latest
    depends_on:
      postgres:
        condition: service_healthy
```

#### 优点
- ✅ 零代码改动
- ✅ 一键启动：`docker-compose up`
- ✅ 环境一致性保证

#### 缺点
- ⚠️ 仍然依赖 PostgreSQL
- ⚠️ 不适合嵌入式场景
- ⚠️ Docker 镜像较大（~500MB）

---

### 方案 3: SQLite + sqlite-vss（轻量级替代）

**适用场景**: 单用户、原型开发、边缘部署

#### 技术方案

使用 [sqlite-vss](https://github.com/asg017/sqlite-vss) 实现向量搜索：

```python
# aurora_api/vector_stores/sqlite_vss.py
import sqlite_vss

class SQLiteVectorStore(VectorStore):
    async def search(self, query_embedding, limit, filters):
        # SQLite VSS 向量搜索
        results = await self.db.execute("""
            SELECT * FROM documents
            WHERE vss_search(embedding_vector, ?)
            LIMIT ?
        """, (query_embedding, limit))
        return results
```

#### 优点
- ✅ 零外部依赖（单文件数据库）
- ✅ 极简部署（Python + SQLite）
- ✅ 适合边缘设备

#### 缺点
- ⚠️ 性能不如 pgvector（大规模数据）
- ⚠️ 不适合多用户并发

---

### 方案 4: 云服务优先（SaaS 化）

**适用场景**: 快速上线、无需自建基础设施

#### 推荐服务

**Pinecone** (最成熟):
```python
# aurora_api/vector_stores/pinecone.py
import pinecone

class PineconeVectorStore(VectorStore):
    async def ingest(self, content, embedding, namespace, metadata):
        self.index.upsert(
            vectors=[(str(uuid.uuid4()), embedding, metadata)],
            namespace=namespace
        )
```

**Weaviate Cloud**:
```python
# aurora_api/vector_stores/weaviate.py
import weaviate

class WeaviateVectorStore(VectorStore):
    async def search(self, query_embedding, limit, filters):
        return self.client.query.get("Document", ["content"]) \
            .with_near_vector({"vector": query_embedding}) \
            .with_limit(limit).do()
```

#### 优点
- ✅ 零运维成本
- ✅ 自动扩展
- ✅ 高可用性保证

#### 缺点
- ⚠️ 持续费用（按向量数量计费）
- ⚠️ 数据外部托管（隐私考虑）
- ⚠️ 供应商锁定

---

## 推荐实施路径

### 阶段 1: 短期（1-2 周）- Docker 简化部署
**目标**: 解决部署复杂度问题

1. 创建 pgvector 预构建镜像
2. 完善 docker-compose.yml
3. 添加健康检查和自动初始化
4. 编写部署文档

**影响**:
- 代码改动: 0%
- 部署复杂度: ↓ 80%

---

### 阶段 2: 中期（1 个月）- 抽象层设计
**目标**: 支持多种向量数据库

1. 定义 VectorStore 抽象接口
2. 重构现有代码为 PostgresVectorStore
3. 实现 ChromaVectorStore（轻量级）
4. 配置化后端选择

**影响**:
- 代码改动: +30%
- 支持场景: ↑ 300%（PostgreSQL/Chroma/内存）

---

### 阶段 3: 长期（2-3 个月）- 云原生支持
**目标**: 生产环境多样化部署

1. 实现 Pinecone/Weaviate 后端
2. 性能基准测试（不同后端对比）
3. 迁移工具（PostgreSQL → 云服务）
4. 成本计算器

**影响**:
- 代码改动: +50%
- 部署选项: 6+ 种

---

## 关键设计原则

### 1. 向后兼容
```python
# 默认行为不变
VECTOR_STORE_BACKEND=postgres  # 默认值

# 现有用户无需修改配置
```

### 2. 渐进式迁移
```python
# 允许混合使用
# 旧数据在 PostgreSQL，新数据在 Pinecone
async def search(...):
    results_pg = await postgres_store.search(...)
    results_cloud = await pinecone_store.search(...)
    return merge_results(results_pg, results_cloud)
```

### 3. 性能透明度
```python
# 每个后端标注性能特征
@dataclass
class BackendCapabilities:
    max_vectors: int  # PostgreSQL: unlimited, Pinecone: 按计费
    search_latency_p99: float  # PostgreSQL: 50ms, Chroma: 10ms
    supports_filters: bool
```

---

## 实施优先级

### 高优先级（必须做）
1. ✅ Docker 一键部署（解决 80% 用户痛点）
2. ✅ 文档完善（安装/配置/故障排查）

### 中优先级（建议做）
3. ⚠️ VectorStore 抽象层（提升架构质量）
4. ⚠️ ChromaDB 后端（支持嵌入式场景）

### 低优先级（可选）
5. 💡 云服务集成（特定用户需求）
6. 💡 SQLite-VSS 后端（边缘场景）

---

## 成本收益分析

| 方案 | 开发成本 | 维护成本 | 收益 |
|------|---------|---------|------|
| Docker 简化 | 1 周 | 低 | 部署效率 ↑ 80% |
| 抽象层 | 3 周 | 中 | 支持场景 ↑ 300% |
| 云服务 | 2 周/服务 | 高 | 运维成本 ↓ 90% |
| SQLite-VSS | 1 周 | 低 | 嵌入式可用 |

---

## 参考资料

### 向量数据库对比
- **PostgreSQL + pgvector**: 开源、自托管、性能优秀
- **Pinecone**: 托管服务、高性能、按量计费
- **Weaviate**: 开源+托管、GraphQL API
- **ChromaDB**: 嵌入式、适合原型
- **Qdrant**: Rust 实现、高性能、自托管友好

### 相关项目
- [LangChain VectorStores](https://python.langchain.com/docs/modules/data_connection/vectorstores/)
- [LlamaIndex Storage](https://docs.llamaindex.ai/en/stable/module_guides/storing/)

---

## 总结

**当前状态**: 强依赖 PostgreSQL + pgvector，部署复杂度高

**建议路径**:
1. **立即执行**: Docker 一键部署（最小改动，最大收益）
2. **中期规划**: VectorStore 抽象层（架构升级）
3. **按需扩展**: 云服务集成（特定场景）

**核心原则**: 向后兼容、渐进式迁移、性能透明
