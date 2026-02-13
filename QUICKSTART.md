# 快速开始指南

## 5分钟快速上手

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥

先复制模板：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，替换以下两处API密钥:

```yaml
llm:
  api_key: "your-llm-api-key-here"    # 替换为你的LLM API密钥

embedding:
  api_key: "your-embedding-api-key-here"  # 替换为你的Embedding API密钥
```

**提示**: 如果使用同一个API服务，可以设置相同的密钥。

### 3. 运行测试检查

```bash
python3 test_setup.py
```

这会检查:
- ✓ 所有依赖是否已安装
- ✓ API密钥是否已配置
- ✓ 示例文件是否存在

### 4. 运行示例

使用提供的示例小说:

```bash
python3 main.py --input data/input/示例小说.txt
```

或者使用你自己的小说:

```bash
python3 main.py --input data/input/你的小说.txt
```

### 5. 查看结果

处理完成后，查看以下目录:

```bash
# 场景切分结果
cat data/scenes/chapter_0001_scenes.json | head -50

# 标注结果
cat data/annotated/chapter_0001_annotated.json | head -50

# 角色档案
cat data/profiles/*.md
```

## 常用命令

### 完整流程

```bash
# 全部执行
python3 main.py --input data/input/小说.txt

# 强制重新执行
python3 main.py --input data/input/小说.txt --force
```

### 分步执行

```bash
# 只执行章节拆分
python3 main.py --step 1 --input data/input/小说.txt

# 只执行场景切分
python3 main.py --step 2

# 只执行元数据标注
python3 main.py --step 3

# 只执行向量化
python3 main.py --step 4

# 只执行角色档案生成
python3 main.py --step 5
```

### 重做特定章节

```bash
# 重做第5章的场景切分
python3 main.py --step 2 --redo-chapter 5

# 重做第3章的元数据标注
python3 main.py --step 3 --redo-chapter 3
```

### 重跑行为说明

- 默认重复执行会自动跳过已完成的下游章节，避免状态回退。
- 使用 `--redo-chapter` 只重做目标章节。
- 向量化重跑同章节会替换该章节旧向量，不会无限追加重复点。

## API服务推荐

### OpenAI官方

```yaml
llm:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-..."
  model: "gpt-4o"
  annotate_model: "gpt-4o-mini"

embedding:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-..."
  model: "text-embedding-3-small"
  dimensions: 1536
```

### 国内API服务示例

大多数国内服务都兼容OpenAI格式，只需修改base_url:

```yaml
llm:
  base_url: "https://your-provider.com/v1"
  api_key: "your-key"
  model: "模型名称"

embedding:
  base_url: "https://your-provider.com/v1"
  api_key: "your-key"
  model: "embedding模型名称"
```

### 本地模型 (Ollama等)

```yaml
llm:
  base_url: "http://localhost:11434/v1"
  api_key: "not-needed"
  model: "qwen2.5"

embedding:
  base_url: "http://localhost:11434/v1"
  api_key: "not-needed"
  model: "nomic-embed-text"
  dimensions: 768
```

## 性能与成本优化

### 1. 使用小模型做标注

```yaml
llm:
  model: "gpt-4o"              # 场景切分用大模型(精度要求高)
  annotate_model: "gpt-4o-mini"  # 元数据标注用小模型(节省成本)
```

### 2. 调整场景长度

```yaml
scene_split:
  min_length: 300      # 减少可能降低质量
  max_length: 800      # 减少可减少API调用
  target_length: 500
```

### 3. 批量处理

```yaml
annotation:
  batch_size: 5        # 增加可减少API调用次数

embedding:
  batch_size: 100      # Embedding可以用更大批量
```

### 4. 并发调用（提升吞吐，适用于场景切分/标注/角色档案）

```yaml
llm:
  concurrent_requests: 4  # 并发请求数（仍会按 rate_limit_per_minute 做全局节流）
```

## 预期处理时间

基于示例配置 (gpt-4o + gpt-4o-mini):

| 小说长度 | 预估时间 | 预估成本 (USD) |
|---------|---------|---------------|
| 10万字  | 10-15分钟 | $2-5 |
| 50万字  | 1-2小时   | $10-20 |
| 100万字 | 2-4小时   | $20-40 |

实际时间和成本取决于:
- API响应速度
- 速率限制设置
- 选择的模型
- 场景平均长度

## 故障排查

### 问题: 覆盖率过低

```
WARNING - Coverage only 85%, below threshold 90%
```

**解决**:
1. 检查LLM返回的场景标记是否准确
2. 降低阈值: `coverage_threshold: 0.8`
3. 系统会自动补充遗漏片段

### 问题: API调用失败

```
ERROR - LLM call failed: Connection timeout
```

**解决**:
1. 检查网络连接
2. 检查API密钥是否正确
3. 增加重试次数: `max_retries: 5`
4. 增加重试延迟: `retry_delay: 5`

### 问题: 内存不足

```
ERROR - Out of memory
```

**解决**:
1. 减小批量大小: `batch_size: 1`
2. 分步执行，不要一次运行全部步骤
3. 处理完一个阶段后重启程序再运行下一阶段

### 问题: 向量维度不匹配

```
ERROR - Expected 1536 dimensions, got 768
```

**解决**:
修改config.yaml中的dimensions以匹配模型实际输出:

```yaml
embedding:
  dimensions: 768  # 改为实际维度
```

## 下一步

处理完成后，你可以:

1. **使用向量检索**
   ```python
   from qdrant_client import QdrantClient
   client = QdrantClient(path="vector_db")
   ```

2. **查看角色档案**
   ```bash
   ls data/profiles/
   cat data/profiles/主角名字.md
   ```

3. **分析元数据**
   ```python
   import json
   with open('data/annotated/chapter_0001_annotated.json') as f:
       data = json.load(f)
   ```

4. **构建RAG应用**
   - 使用生成的向量数据库做检索
   - 使用角色档案做角色扮演
   - 结合元数据做高级过滤

5. **运行 RP 完整链路**
   ```bash
   python3 example_rp_query.py \
     --session demo-session \
     --message "许七安和朱县令是什么关系？" \
     --unlocked 13 \
     --active-character 许七安
   ```

6. **通过 API 集成游戏引擎（可选）**
   ```bash
   pip install fastapi uvicorn
   uvicorn api.rp_query_api:create_app --factory --host 0.0.0.0 --port 8011
   ```
   - `POST /api/v1/rp/query-context`
   - `POST /api/v1/rp/respond`
   - `GET /api/v1/rp/session/{id}`

7. **可选调优 RP 召回规模**
   ```yaml
   rp_query:
     vector_top_k: 30
     filter_top_k: 20
     profile_top_k: 10
     worldbook_top_n: 8
   ```

## 获取帮助

- 查看详细文档: `README.md`
- 查看配置说明: `config.yaml` 注释
- 查看日志文件: `logs/pipeline_*.log`

祝使用愉快! 🎉
