# 项目文件结构说明

## 目录树

```
airp2/
│
├── 📄 README.md                    # 详细文档
├── 📄 QUICKSTART.md                # 快速开始指南
├── 📄 PROJECT_STRUCTURE.md         # 项目结构说明
├── 📄 FOLLOWUP_DEVELOPMENT_PLAN.md # RP 后续能力规划
├── 📄 FRONTEND_DEVELOPMENT_PLAN.md # 前端长期方案（Liquid Glass）
├── 📄 NOVEL_LIBRARY_DEVELOPMENT_PLAN.md # 多小说工作台方案
├── 📄 REPAIR_PLAN.md               # 修复计划（幂等/状态机等）
├── 📄 config.yaml                  # 配置文件
├── 📄 requirements.txt             # Python依赖
├── 📄 .gitignore                   # Git忽略规则
├── 🐳 Dockerfile                   # 容器镜像构建
├── 🐳 docker-compose.yml           # 运行示例（可按需改为本地 build）
│
├── 🔧 main.py                      # 主流程控制
├── 🔧 test_setup.py                # 环境检查脚本
├── 🔧 example_usage.py             # 使用示例
├── 🔧 example_rp_query.py          # RP查询与回复示例
│
├── 📝 步骤脚本/
│   ├── step1_split_chapters.py    # 阶段1: 章节拆分
│   ├── step2_scene_split.py       # 阶段2: 场景切分
│   ├── step3_annotate.py          # 阶段3: 元数据标注
│   ├── step4_vectorize.py         # 阶段4: 向量化入库
│   └── step5_character_profile.py # 阶段5: 角色档案
│
├── 🧠 services/                    # RP + 多小说工作台服务层
│   ├── novel_registry.py           # 多小说注册表/工作区路径管理
│   ├── pipeline_runner.py          # 在 Novel 工作区内运行 Step1~5
│   ├── pipeline_jobs.py            # 后台 Job 状态机 + 日志
│   ├── query_understanding.py      # 查询理解
│   ├── retrieval_orchestrator.py   # 召回编排
│   ├── reranker.py                 # 统一重排
│   ├── worldbook_builder.py        # 世界书构建
│   ├── session_state.py            # 会话状态存储
│   ├── guardrails.py               # 防幻觉/防剧透
│   └── retrievers/                 # 多路召回通道
│
├── 🌐 api/                         # API入口
│   └── rp_query_api.py             # RP + Novels/Jobs API + 静态页托管
│
├── 🎨 frontend/                    # React 前端（Library + Chat）
│   └── src/...
│
├── 🛠️ utils/                       # 工具模块
│   ├── __init__.py
│   ├── llm_client.py              # LLM调用客户端
│   ├── embedding_client.py        # Embedding客户端
│   ├── text_utils.py              # 文本处理工具
│   ├── fuzzy_match.py             # 模糊匹配工具
│   └── validation.py              # 数据校验工具
│
├── 📁 data/                        # 数据目录
│   ├── input/                     # 输入小说文件
│   │   └── 示例小说.txt
│   ├── chapters/                  # 章节文本 (生成)
│   ├── scenes/                    # 场景JSON (生成)
│   ├── annotated/                 # 标注数据 (生成)
│   ├── profiles/                  # 角色档案 (生成)
│   ├── novels/                    # 多小说工作区（隔离）
│   │   ├── index.json             # Novel 注册表
│   │   └── <novel_id>/...         # 每本小说独立 input/chapters/scenes/...
│   └── jobs/                      # pipeline job 状态持久化（json）
│
├── 📁 vector_db/                   # 向量数据库 (生成)
│   └── <novel_id>/...              # 多小说隔离向量库目录（Qdrant local）
└── 📁 logs/                        # 运行日志 (生成)
    └── novels/<novel_id>/job_*.log # 多小说 job 日志
```

## 核心文件说明

### 配置与文档

- **config.yaml**: 全局配置文件
  - LLM API配置
  - Embedding API配置
  - 文件路径配置
  - 处理参数配置

- **README.md**: 完整项目文档
  - 功能介绍
  - 安装指南
  - 详细使用说明
  - API配置示例

- **QUICKSTART.md**: 快速上手指南
  - 5分钟快速开始
  - 常用命令
  - 故障排查

- **NOVEL_LIBRARY_DEVELOPMENT_PLAN.md**: 多小说工作台方案与里程碑
- **FRONTEND_DEVELOPMENT_PLAN.md**: 前端长期方案（Liquid Glass Premium）
- **FOLLOWUP_DEVELOPMENT_PLAN.md**: RP 检索/世界书/防剧透后续规划
- **REPAIR_PLAN.md**: 主流程幂等与修复项清单

### 主程序

- **main.py**: 流水线主控制程序
  - 协调5个处理阶段
  - 进度管理
  - 错误处理
  - 生成处理报告

- **test_setup.py**: 环境检查工具
  - 检查依赖是否安装
  - 检查配置是否正确
  - 检查示例文件

- **example_usage.py**: 向量数据库使用示例
  - 按人物检索
  - 按地点检索
  - 语义搜索
  - 组合过滤
  - 统计分析

### 处理阶段脚本

**step1_split_chapters.py** - 章节拆分
```
输入: data/input/小说.txt
输出: data/chapters/chapter_*.txt
     data/chapters/chapter_index.json
```

**step2_scene_split.py** - 场景切分
```
输入: data/chapters/chapter_*.txt
输出: data/scenes/chapter_*_scenes.json
使用: LLM API (识别场景边界)
```

**step3_annotate.py** - 元数据标注
```
输入: data/scenes/chapter_*_scenes.json
输出: data/annotated/chapter_*_annotated.json
      data/annotated/character_name_map.json
使用: LLM API (提取元数据)
```

**step4_vectorize.py** - 向量化
```
输入: data/annotated/chapter_*_annotated.json
输出: vector_db/ (Qdrant数据库)
使用: Embedding API (生成向量)
```

**step5_character_profile.py** - 角色档案
```
输入: data/annotated/*.json
输出: data/profiles/*.md
使用: LLM API (生成档案)
```

### 工具模块

**utils/llm_client.py**
- OpenAI兼容API调用
- 重试机制
- 速率限制
- JSON解析
- 统计追踪

**utils/embedding_client.py**
- Embedding API调用
- 批量处理
- 向量维度验证
- 统计追踪

**utils/text_utils.py**
- 文件编码检测
- 文本清理
- 标点符号规范化
- 句子切分
- 文本片段提取

**utils/fuzzy_match.py**
- 模糊文本匹配
- 场景边界定位
- 相似度计算

**utils/validation.py**
- 场景覆盖率检查
- 重叠检测
- 长度校验
- 元数据结构验证
- 人物名称验证

## 数据流转

```
原始小说 (txt)
    ↓
[Step 1] 章节拆分
    ↓
章节文本 (txt) + 索引 (json)
    ↓
[Step 2] LLM场景切分
    ↓
场景数据 (json)
    ↓
[Step 3] LLM元数据标注
    ↓
标注数据 (json) + 人物映射 (json)
    ↓
[Step 4] Embedding向量化
    ↓
向量数据库 (Qdrant)
    ↓
[Step 5] LLM生成档案
    ↓
角色档案 (markdown)
```

## 生成的数据格式

### chapter_index.json
```json
{
  "source_file": "示例小说.txt",
  "total_chapters": 3,
  "chapters": [
    {
      "chapter_id": "chapter_0001",
      "file": "chapter_0001.txt",
      "title": "第一回 初遇江湖",
      "char_count": 1234,
      "status": "vectorized"
    }
  ]
}
```

### chapter_*_scenes.json
```json
{
  "chapter_id": "chapter_0001",
  "total_scenes": 5,
  "coverage_rate": 0.97,
  "scenes": [
    {
      "scene_index": 0,
      "text": "...",
      "char_count": 234,
      "scene_summary": "..."
    }
  ]
}
```

### chapter_*_annotated.json
```json
{
  "scenes": [
    {
      "scene_index": 0,
      "text": "...",
      "metadata": {
        "characters": ["林风", "沈小姐"],
        "location": "客栈",
        "event_summary": "...",
        "plot_significance": "high"
      }
    }
  ]
}
```

### character_name_map.json
```json
{
  "林风": ["林风", "林公子", "少年"],
  "沈小姐": ["沈小姐", "白衣女子"]
}
```

## 使用流程

1. **准备工作**
   ```bash
   pip install -r requirements.txt
   python3 test_setup.py
   ```

2. **配置API**
   - 编辑 config.yaml
   - 设置 LLM 和 Embedding API密钥

3. **运行处理**
   ```bash
   python3 main.py --input data/input/你的小说.txt
   ```

4. **查看结果**
   ```bash
   python3 example_usage.py
   ```

5. **使用数据**
   - 向量检索: 使用 Qdrant Client
   - 角色扮演: 读取 profiles/*.md
   - 元数据分析: 读取 annotated/*.json

## 扩展开发

### 添加新的元数据字段

1. 修改 `step3_annotate.py` 中的提取prompt
2. 更新 `utils/validation.py` 中的验证规则
3. 修改 `step4_vectorize.py` 中的payload结构

### 自定义场景切分规则

1. 修改 `step2_scene_split.py` 中的切分prompt
2. 调整 `config.yaml` 中的长度参数

### 添加新的检索方式

1. 参考 `example_usage.py` 中的示例
2. 使用 Qdrant 的过滤和检索API
3. 结合元数据字段做复杂查询

## 性能优化

- 使用小模型做标注可节省50%+成本
- 增加批量大小可减少API调用次数
- 调整场景长度可平衡质量与数量
- 设置合理的速率限制避免被封禁

## 维护建议

- 定期备份 vector_db/ 目录
- 保存重要的 annotated/ 数据
- 记录 character_name_map.json 供后续使用
- 查看 logs/ 了解处理细节
