# 小说文本向量化处理系统

Novel Text Vectorization Pipeline - 将长篇小说智能切分并向量化，构建高质量的RAG知识库。

## 功能特点

- 📚 **智能章节拆分**: 自动识别章节标题，支持多种格式
- 🎬 **LLM场景切分**: 使用大语言模型智能识别场景边界
- 🏷️ **元数据标注**: 自动提取人物、地点、时间、情感等元数据
- 🔍 **向量化入库**: 增强文本后向量化，存入Qdrant数据库
- 👤 **角色档案**: 自动生成主要角色的详细档案
- 🔄 **断点续传**: 支持中断恢复，已完成部分自动跳过
- 📊 **详细报告**: 完成后生成处理统计报告

## 系统架构

```
原始txt → 章节拆分 → LLM场景切分 → 元数据标注 → 向量化 → 角色档案
         Step 1      Step 2        Step 3      Step 4    Step 5
```

## 开发文档

- `QUICKSTART.md`: 快速开始
- `PROJECT_STRUCTURE.md`: 项目结构说明
- `FOLLOWUP_DEVELOPMENT_PLAN.md`: RP后续能力规划
- `FRONTEND_DEVELOPMENT_PLAN.md`: 前端长期方案（React + TypeScript, Liquid Glass Premium）

## 安装

### 1. 克隆项目

```bash
git clone <repository-url>
cd novel-vectorizer
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置API密钥

先复制模板：

```bash
cp config.example.yaml config.yaml
```

再编辑 `config.yaml`，配置你的LLM和Embedding API:

```yaml
llm:
  base_url: "https://api.openai.com/v1"
  api_key: "your-llm-api-key"
  model: "gpt-4o"
  annotate_model: "gpt-4o-mini"

embedding:
  base_url: "https://api.openai.com/v1"
  api_key: "your-embedding-api-key"
  model: "text-embedding-3-small"
  dimensions: 1536
```

**注意**: LLM和Embedding可以使用不同的API服务商。

## 使用方法

### 准备小说文件

将txt格式的小说文件放入 `data/input/` 目录:

```bash
data/input/红楼梦.txt
```

### 运行完整流水线

```bash
python3 main.py --input data/input/红楼梦.txt
```

### 只运行特定阶段

```bash
# 只运行场景切分
python3 main.py --step 2

# 重做指定章节的场景切分
python3 main.py --step 2 --redo-chapter 5

# 强制重新处理所有章节
python3 main.py --input data/input/红楼梦.txt --force
```

### 重跑语义（修复后）

- 默认重复运行不会回退已完成状态（例如 `vectorized` 不会被 Step2/Step3 回退）。
- `--redo-chapter N` 只重做指定章节，并清理该章节下游产物引用。
- Step4 对同一章节重跑时会先删除该章节旧向量，再写入新向量，避免重复和覆盖错误。

### 单独运行各阶段

```bash
# 阶段1: 章节拆分
python3 step1_split_chapters.py data/input/红楼梦.txt

# 阶段2: 场景切分
python3 step2_scene_split.py

# 阶段3: 元数据标注
python3 step3_annotate.py

# 阶段4: 向量化
python3 step4_vectorize.py

# 阶段5: 角色档案
python3 step5_character_profile.py
```

## 配置说明

### 场景切分参数

```yaml
scene_split:
  min_length: 400      # 最小场景长度（字符）
  max_length: 1000     # 最大场景长度（字符）
  target_length: 600   # 目标场景长度（字符）
  coverage_threshold: 0.9  # 覆盖率阈值
```

### 向量数据库配置

```yaml
vector_db:
  collection_name: "novel_scenes"
  distance_metric: "Cosine"  # 可选: Cosine, Euclidean, Dot
```

### 角色档案配置

```yaml
character_profile:
  top_n_characters: 20  # 生成档案的角色数量
  min_scenes: 5         # 最少出场次数
```

## 输出说明

### 目录结构

```
data/
├── input/              # 原始小说文件
├── chapters/           # 章节文本文件
│   ├── chapter_0001.txt
│   ├── chapter_0002.txt
│   └── chapter_index.json  # 章节索引
├── scenes/             # 场景切分结果
│   ├── chapter_0001_scenes.json
│   └── chapter_0002_scenes.json
├── annotated/          # 标注后的场景
│   ├── chapter_0001_annotated.json
│   ├── character_name_map.json  # 人物名称映射
│   └── ...
└── profiles/           # 角色档案
    ├── 贾宝玉.md
    ├── 林黛玉.md
    └── ...

vector_db/              # Qdrant向量数据库
logs/                   # 运行日志
```

### 场景JSON格式

```json
{
  "source_file": "chapter_0001.txt",
  "chapter_id": "chapter_0001",
  "chapter_title": "第一回 甄士隐梦幻识通灵",
  "total_scenes": 12,
  "coverage_rate": 0.97,
  "scenes": [
    {
      "scene_index": 0,
      "text": "原文内容...",
      "char_count": 672,
      "scene_summary": "甄士隐梦中遇见一僧一道",
      "metadata": {
        "characters": ["甄士隐", "僧人", "道士"],
        "location": "梦境",
        "time_description": "夜晚",
        "event_summary": "甄士隐梦见僧道对话",
        "emotion_tone": "神秘",
        "key_dialogues": ["..."],
        "character_relations": ["..."],
        "plot_significance": "high"
      }
    }
  ]
}
```

## 检索使用示例

```python
from qdrant_client import QdrantClient

# 连接向量数据库
client = QdrantClient(path="vector_db")

# 按人物检索
results = client.scroll(
    collection_name="novel_scenes",
    scroll_filter={
        "must": [
            {"key": "characters", "match": {"any": ["林黛玉"]}}
        ]
    },
    limit=10
)

# 向量检索
from utils.embedding_client import EmbeddingClient
import yaml

with open('config.yaml') as f:
    config = yaml.safe_load(f)

emb_client = EmbeddingClient(config)
query_vector = emb_client.embed(["林黛玉在贾府的生活"])[0]

results = client.search(
    collection_name="novel_scenes",
    query_vector=query_vector,
    limit=5
)
```

## 角色扮演查询系统（RP）

项目已包含完整的 RP 查询链路实现（问题理解 -> 多路召回 -> 重排 -> 世界书构建 -> 会话记忆 -> 回答约束）。

### 1. 代码内直接调用

```python
from api.rp_query_api import RPQueryService

service = RPQueryService.from_config_file("config.yaml")

ctx = service.query_context(
    message="许七安和朱县令是什么关系？",
    session_id="session-1",
    unlocked_chapter=13,
    active_characters=["许七安"]
)

resp = service.respond(
    message="继续推进剧情",
    session_id="session-1",
    worldbook_context=ctx["worldbook_context"],
    citations=ctx["citations"]
)
print(resp["assistant_reply"])
```

### 2. CLI 示例

```bash
python3 example_rp_query.py \
  --session demo-session \
  --message "许七安和朱县令是什么关系？" \
  --unlocked 13 \
  --active-character 许七安
```

### 3. API 端点（可选 FastAPI）

安装可选依赖：

```bash
pip install fastapi uvicorn
```

启动（示例）：

```bash
uvicorn api.rp_query_api:create_app --factory --host 0.0.0.0 --port 8011
```

可用端点：
- `POST /api/v1/rp/query-context`
- `POST /api/v1/rp/respond`
- `GET /api/v1/rp/session/{id}`

### 4. 前端（React + TypeScript）

项目已新增 `frontend/` 前端工程（会话入口 + RP聊天三栏界面 + 引用/调试面板）。

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

默认前端地址：`http://localhost:5173`  
默认后端地址：`http://localhost:8011`（可通过 `VITE_API_BASE_URL` 覆盖）

### 5. RP参数调优（config.yaml）

```yaml
rp_query:
  vector_top_k: 30
  filter_top_k: 20
  profile_top_k: 10
  worldbook_top_n: 8
```

## 性能优化建议

### 1. 使用不同模型节省成本

```yaml
llm:
  model: "gpt-4o"              # 场景切分用高质量模型
  annotate_model: "gpt-4o-mini"  # 元数据标注用小模型
```

### 2. 调整批量处理大小

```yaml
annotation:
  batch_size: 5  # 增加批量大小可减少API调用次数

embedding:
  batch_size: 50  # Embedding通常可以用更大的批量
```

### 3. 速率限制

```yaml
llm:
  rate_limit_per_minute: 30  # 根据API限制调整
```

### 4. 并发调用（加速场景切分/标注/角色档案）

```yaml
llm:
  concurrent_requests: 4  # 并发请求数（仍会按 rate_limit_per_minute 做全局节流）
```

## 常见问题

### Q: 场景覆盖率过低怎么办?

A: 系统会自动补充遗漏片段。如果覆盖率仍然低于阈值，可以:
- 降低 `coverage_threshold` (如 0.85)
- 检查LLM返回的marker是否准确
- 使用 `--redo-chapter N` 重新处理特定章节

### Q: 如何处理特殊格式的章节?

A: 在 `config.yaml` 中添加自定义正则表达式:

```yaml
chapter_split:
  patterns:
    - "第[一二三四五六七八九十百千0-9]{1,4}[章回]"
    - "Chapter\\s+\\d+"
    - "你的自定义模式"
```

### Q: 向量维度不匹配怎么办?

A: 确保config中的dimensions与embedding模型实际输出一致:

```yaml
embedding:
  dimensions: 1536  # text-embedding-3-small
  # dimensions: 3072  # text-embedding-3-large
```

### Q: 如何使用国内API服务?

A: 修改base_url即可，支持所有OpenAI兼容格式的API:

```yaml
llm:
  base_url: "https://your-provider.com/v1"
  api_key: "your-key"

embedding:
  base_url: "https://another-provider.com/v1"
  api_key: "another-key"
```

## 技术栈

- **LLM调用**: OpenAI SDK (兼容格式)
- **向量数据库**: Qdrant (本地文件模式)
- **文本处理**: chardet, thefuzz
- **配置管理**: PyYAML

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request!

## 作者

Novel Vectorization Pipeline
