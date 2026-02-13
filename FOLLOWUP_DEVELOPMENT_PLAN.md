# 角色扮演游戏数据库调用查询系统 - 后续开发计划

## 1. 目标与成功标准

### 1.1 目标
- 建立一个可在角色扮演对话中稳定调用小说知识库的查询系统。
- 保证“相关信息能被召回、引用证据可追溯、结果可控注入提示词、支持会话连续性”。
- 面向现有数据管线（Step1~Step5）扩展，不推翻当前结构。

### 1.2 成功标准（上线验收）
- 检索准确性：离线评测 Recall@10 >= 0.85，MRR@10 >= 0.70。
- 引用正确性：返回结果 100% 附带来源（chapter + scene_index + excerpt）。
- 幻觉控制：回答中“无证据断言”占比 <= 5%。
- 性能：P95 查询时延 <= 800ms（不含最终大模型生成）。
- 稳定性：连续 24h 压测错误率 < 0.5%。

## 2. 范围与非目标

### 2.1 本期范围
- 查询理解（意图识别、实体抽取、上下文拼接）。
- 多路召回（语义向量 + 结构化过滤 + 角色档案补充）。
- 结果重排与证据封装（世界书片段构建）。
- 会话记忆（玩家进度、当前场景、活跃角色）。
- API 与评测体系（离线集 + 回归测试 + 观测指标）。

### 2.2 非目标
- 不在本期重做小说切分/标注算法核心逻辑。
- 不在本期做多租户权限系统。
- 不在本期做前端 UI 重构（只提供 API/CLI 能力）。

## 3. 当前基础能力（可复用）
- 向量库：`vector_db` 本地 Qdrant，集合 `novel_scenes`。
- 已有载荷字段：`text/chapter/chapter_title/scene_index/scene_summary/characters/location/event_summary/...`（见 `step4_vectorize.py`）。
- Embedding 能力：`utils/embedding_client.py`。
- 查询示例：`example_usage.py`（scroll/filter/query 示例）。
- 角色档案：`data/profiles/*.md`（可作为静态人设知识源）。

## 4. 目标系统架构

### 4.1 逻辑分层
1. `Query Understanding`（问题理解层）
2. `Retrieval Orchestrator`（召回编排层）
3. `Re-ranker`（重排层）
4. `Worldbook Builder`（世界书构建层）
5. `Session Memory`（会话记忆层）
6. `Response Grounding`（回答约束层）

### 4.2 建议新增模块
- `services/query_understanding.py`
- `services/retrieval_orchestrator.py`
- `services/retrievers/vector_retriever.py`
- `services/retrievers/filter_retriever.py`
- `services/retrievers/profile_retriever.py`
- `services/reranker.py`
- `services/worldbook_builder.py`
- `services/session_state.py`
- `services/guardrails.py`
- `api/rp_query_api.py`（如果项目接 API 服务）

## 5. 功能设计（完备版）

### 5.1 查询理解
- 输入：用户本轮消息 + 最近 N 轮对话 + 会话状态。
- 输出：
  - `intent`：剧情回顾/人物关系/地点追问/设定求证/下一步行动建议。
  - `entities`：角色名、地点、事件关键词、时间线锚点。
  - `constraints`：章节上限（防剧透）、活跃角色、地点优先级。
- 实现建议：
  - 第一版先规则+词典（高可控）
  - 第二版再加小模型抽取（容错）

### 5.2 多路召回
- 通道A：语义召回（`query_points`）
  - 输入 query embedding，top_k=30
- 通道B：结构化过滤召回
  - 按 `characters/location/plot_significance/chapter` 条件 `scroll` 补充 top_k=20
- 通道C：角色档案召回
  - 从 `data/profiles/*.md` 选取命中角色的设定摘要
- 合并策略：去重后最多保留 60 条候选

### 5.3 重排与相关性评分
- 评分建议：
  - `semantic_score`（向量相似度）40%
  - `entity_overlap`（角色/地点命中）30%
  - `narrative_fit`（事件摘要关键词匹配）20%
  - `recency_in_session`（会话最近提及）10%
- 产出 top_n=8 证据片段供世界书构建。

### 5.4 世界书构建
- 输出结构（建议 JSON）：
  - `facts[]`: 每条含 `fact_text/source_chapter/source_scene/excerpt/confidence`
  - `character_state[]`: 角色目标、情绪、关系摘要
  - `timeline_notes[]`: 按章节排序的关键事件
  - `forbidden`: 无证据禁止扩写的点
- Token 预算：
  - 证据片段 70%
  - 角色状态 20%
  - 规则约束 10%

### 5.5 防幻觉与防剧透
- 防幻觉：
  - 所有事实陈述必须关联至少一个 `source`。
  - 若证据不足，返回“未检索到明确证据”。
- 防剧透：
  - 会话状态维护 `max_unlocked_chapter`。
  - 查询时加 `chapter <= unlocked` 过滤。

### 5.6 会话记忆
- 短期记忆（最近 10~20 轮）：支持代词消解、延续剧情。
- 长期记忆（会话摘要）：记录已发生事件、玩家选择、关系变化。
- 建议持久化：
  - 单小说/默认：`data/sessions/{session_id}.json`
  - 多小说隔离：`data/novels/<novel_id>/sessions/{session_id}.json`

### 5.7 调用接口设计
- `POST /api/v1/rp/query-context`
  - 输入：`message, session_id, novel_id?, unlocked_chapter, active_characters`
  - 输出：`worldbook_context, citations, debug_scores`
- `POST /api/v1/rp/respond`
  - 输入：`message + worldbook_context (+ novel_id?)`
  - 输出：`assistant_reply + citations`
- `GET /api/v1/rp/session/{id}`
  - 输入：query 参数 `novel_id?`
  - 输出：会话状态与进度

## 6. 数据模型与索引优化

### 6.1 现有 payload 增补（建议）
- `chapter_no`（int，便于比较过滤）
- `aliases`（角色别名列表）
- `entity_tags`（如“办案/朝堂/修行”）
- `spoiler_level`（用于开放进度控制）

### 6.2 索引策略
- 已有：`characters/location/chapter/plot_significance`
- 增补：`chapter_no`、`entity_tags`
- 目标：降低过滤召回时延，稳定 P95。

## 7. 评测与测试计划

### 7.1 离线评测集
- 构建 200 条测试查询，覆盖：
  - 人物关系追问
  - 事件回顾
  - 地点与时间问题
  - 多角色冲突场景
  - 防剧透边界问题

### 7.2 指标
- 检索：Recall@k、MRR、nDCG
- 生成：事实一致率、引用覆盖率、剧透违规率
- 性能：P50/P95 时延、QPS、错误率

### 7.3 自动化测试
- `tests/test_query_understanding.py`
- `tests/test_retrieval_orchestrator.py`
- `tests/test_worldbook_builder.py`
- `tests/test_spoiler_guardrails.py`
- `tests/test_rp_api_contract.py`

## 8. 分阶段里程碑

### Phase 1（MVP，3~4天）
- 完成 Query Understanding（规则版）
- 打通向量召回 + 过滤召回 + 基础去重
- 产出最小世界书 JSON
- 交付：CLI 可演示端到端查询

### Phase 2（可靠性，3~5天）
- 增加重排评分器
- 接入角色档案召回
- 加入防剧透/防幻觉守卫
- 交付：离线评测报告 v1

### Phase 3（产品化，4~6天）
- 封装 API
- 接入会话状态持久化
- 增加 debug 观测字段（命中来源、分数拆解、耗时）
- 交付：可供前端/游戏引擎调用的稳定接口

### Phase 4（优化，持续）
- 调优排序权重
- 扩展章节覆盖
- 增加缓存（query embedding cache / hot query cache）

## 9. 开发任务清单（可执行）

1. 新增服务模块骨架与数据结构定义。
2. 实现 `vector + filter + profile` 三通道召回。
3. 实现统一重排与去重策略。
4. 实现世界书构建器（带证据引用）。
5. 实现会话状态存取与防剧透过滤。
6. 新增 API 接口与参数校验。
7. 增加离线评测脚本与测试数据模板。
8. 补齐单元测试与回归测试。
9. 编写运维文档（日志字段、排障流程、性能基线）。

## 10. 风险与应对
- 风险：角色别名不统一导致召回漏失。
  - 应对：引入别名字典与模糊匹配兜底。
- 风险：模型抽取意图不稳定。
  - 应对：规则优先，小模型仅增强。
- 风险：上下文过长导致提示词溢出。
  - 应对：硬性 token 预算 + 分层摘要。
- 风险：中后期章节未入库时回答偏差。
  - 应对：回复中显式提示知识覆盖范围。

## 11. 验收清单（上线前必过）
- 能正确返回可引用证据的世界书上下文。
- 查询结果可按会话进度自动防剧透。
- 无证据时明确拒答或降级回答。
- 关键 API 契约稳定，测试全绿。
- 监控可观测：召回命中率、时延、错误码完整。

## 12. 本文档与现有代码对应关系
- 向量检索能力基于：`example_usage.py`、`utils/embedding_client.py`。
- 载荷字段来源：`step4_vectorize.py`。
- 角色静态知识来源：`data/profiles/*.md`。
- 本计划为后续“RP 查询系统”开发主线，不影响现有 Step1~Step5 处理流程。
