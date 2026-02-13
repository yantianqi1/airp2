# 多小说导入与处理工作台（Novel Library + Pipeline UI）后续开发计划

## 0. 背景

当前项目已具备：
- 离线流水线：`Step1~Step5`（章节拆分、场景切分、标注、向量化、角色档案）
- 在线 RP：`/api/v1/rp/*`（检索、世界书、引用、回复、会话）
- 前端：可用的 RP Console（会话、证据面板、调试面板）

缺口在于：
- 缺少“用户自助导入小说 + 可控运行流水线 + 多本小说隔离管理”的前端与配套后端能力。

## 0.1 当前实现状态（截至 2026-02-13）

已完成（Phase 1 对应的 MVP 骨架）：
- 后端：Novel Registry（`data/novels/index.json`）+ 多小说工作区/向量库隔离（`data/novels/<novel_id>/...` + `vector_db/<novel_id>`）。
- 后端：上传接口（txt，50MB 限制）+ Pipeline Job（单并发后台线程）+ Job 状态与日志 tail。
- 后端：RP 接口支持 `novel_id`（按小说路由到对应向量库/档案/会话目录）。
- 前端：`/library` 小说库页（新建/上传/一键处理/轮询 job/查看日志）+ `/novels/:novelId/chat/:sessionId` 进入聊天并透传 `novel_id`。

关键代码落点：
- 后端：`services/novel_registry.py`、`services/pipeline_runner.py`、`services/pipeline_jobs.py`、`api/rp_query_api.py`
- 前端：`frontend/src/pages/LibraryPage.tsx`、`frontend/src/shared/api/novels.ts`

已实现 API（摘要）：
- Novel：`GET /api/v1/novels`、`POST /api/v1/novels`、`GET /api/v1/novels/{novel_id}`、`DELETE /api/v1/novels/{novel_id}`
- 上传：`POST /api/v1/novels/{novel_id}/upload`、`GET /api/v1/novels/{novel_id}/source`
- Job：`POST /api/v1/novels/{novel_id}/pipeline/run`、`GET /api/v1/jobs/{job_id}`、`GET /api/v1/jobs/{job_id}/logs`
- RP：`/api/v1/rp/*` 支持请求体/查询参数 `novel_id`（按小说隔离检索与会话）

已知限制（待 Phase 2/3 完善）：
- Job 目前为进程内线程，重启服务后不会自动恢复“运行中”任务。
- 暂未实现 `cancel`，也未拆出独立 `/novels/:novelId/pipeline` 控制台页面（目前在 Library 卡片内提供最小能力）。
- Novel 删除默认不删 `vector_db/<novel_id>`（可通过 `delete_vector_db=true` 控制）。

## 1. 产品目标与成功标准

### 1.1 目标
- 用户可在前端导入自己的小说（先支持 `txt`），创建“小说条目（Novel）”。
- 用户可在前端可控地执行 `Step1~Step5`，看到进度、错误与日志。
- 每本小说的数据与向量库隔离，RP 对话可选择某本小说作为知识源。
- 支持“防剧透进度”按会话/小说维度管理。

### 1.2 成功标准（MVP 验收）
- 能在 UI 中完成：上传 txt -> 一键处理到向量库 -> 进入该小说的 RP Chat 并成功检索到引用。
- 多本小说互不串库：切换小说后检索结果不会混入其它小说证据。
- 流水线失败可定位：UI 可看到失败步骤、失败章节、最近 N 行日志。

## 2. 核心设计决策（多小说隔离）

### 2.1 推荐方案：每本小说独立“工作区 + 向量库目录”
- 数据目录：`data/novels/<novel_id>/...`
- 向量库目录：`vector_db/<novel_id>/...`（Qdrant local file mode）
- collection 名称保持固定：`novel_scenes`

优点：
- 彻底隔离（删除/迁移/备份都简单）
- 允许不同小说使用不同 embedding 维度或模型（互不影响）
- 避免单 collection 变大导致 scroll/维护成本上升

### 2.2 数据布局建议
- `data/novels/index.json`：小说注册表（metadata + 状态）
- `data/novels/<novel_id>/input/source.txt`：原始导入文本
- `data/novels/<novel_id>/chapters/`：Step1 输出
- `data/novels/<novel_id>/scenes/`：Step2 输出
- `data/novels/<novel_id>/annotated/`：Step3 输出
- `data/novels/<novel_id>/profiles/`：Step5 输出
- `data/novels/<novel_id>/sessions/`：该小说会话状态（推荐按小说隔离）
- `logs/novels/<novel_id>/`：流水线运行日志

## 3. 后端开发计划（FastAPI + 服务层）

### 3.1 新增服务模块
- `services/novel_registry.py`
  - CRUD：创建/列出/获取/删除 Novel
  - 生成 `novel_id`（slug + 短随机串），保存到 `data/novels/index.json`（后续可升级到 SQLite）
  - 负责计算各步骤路径（chapters/scenes/annotated/profiles/vector_db_path）

- `services/pipeline_jobs.py`
  - Job 模型：`job_id/novel_id/status/current_step/progress/started_at/finished_at/log_path/error`
  - 运行模式（MVP）：单进程后台线程或子进程执行，前端轮询 job 状态
  - 状态持久化：`data/jobs/<job_id>.json`

- `services/pipeline_runner.py`
  - 以“Novel 上下文”构造 step 配置（继承全局 `config.yaml` 的 llm/embedding 参数）
  - 复用现有 `run_step1~run_step5`，把 `config['paths']` 指向该 Novel 的工作区
  - 输出标准化统计：章节数、场景数、覆盖率、向量点数、失败章节列表

### 3.2 API 设计（建议 v1）
- Novel 管理
  - `GET /api/v1/novels`：列表（含处理状态、最后运行时间、统计摘要）
  - `POST /api/v1/novels`：创建（title 可选）
  - `GET /api/v1/novels/{novel_id}`：详情
  - `DELETE /api/v1/novels/{novel_id}`：删除（可选参数：是否连同 vector_db 一并删除）

- 导入上传
  - `POST /api/v1/novels/{novel_id}/upload`：`multipart/form-data` 上传 txt
  - `GET /api/v1/novels/{novel_id}/source`：返回元信息（文件名/大小/行数/字符数）

- 流水线运行与观测
  - `POST /api/v1/novels/{novel_id}/pipeline/run`
    - body：`step?: 1..5, force?: bool, redo_chapter?: number, mode?: "full"|"step"`
  - `GET /api/v1/jobs/{job_id}`：job 状态
  - `GET /api/v1/jobs/{job_id}/logs`：最近日志（MVP：tail N 行）
  - `POST /api/v1/jobs/{job_id}/cancel`：取消（MVP 可不做，Phase2 做）

- RP 接口扩展（多小说）
  - `POST /api/v1/rp/query-context` 增加 `novel_id`
  - `POST /api/v1/rp/respond` 增加 `novel_id`
  - `GET /api/v1/rp/session/{session_id}` 增加查询参数 `novel_id` 或改为 `GET /api/v1/novels/{novel_id}/sessions/{session_id}`

### 3.3 现有 RP 服务需要的改造点
- `RPQueryService` 需要“按 novel 选择数据源”
  - `vector_db_path` 指向 `vector_db/<novel_id>`
  - `profiles_dir/annotated_dir/session_store.base_dir` 指向 `data/novels/<novel_id>/...`
  - 允许缓存 per-novel 的 retriever/qdrant client，避免每次请求都重建

### 3.4 安全与资源控制（MVP 最小集）
- 单实例并发限制：同一时间最多 1 个 pipeline job（避免把 LLM/embedding 打爆）
- 上传文件限制：只允许 `.txt`，限制最大大小（例如 50MB，可配置）
- 作业隔离：作业 log 单独文件；异常要写入 job state

### 3.5 测试与回归
- `tests/test_novel_registry.py`：CRUD + 路径解析
- `tests/test_pipeline_jobs.py`：job 状态机
- `tests/test_rp_multi_novel_isolation.py`：两本小说检索不串库（可用 stub qdrant）

## 4. 前端开发计划（Novel Workbench）

### 4.1 信息架构与路由（建议）
- `/` 或 `/library`：小说库（Novel Library）
- `/novels/:novelId`：小说概览（统计、最近运行、入口）
- `/novels/:novelId/pipeline`：流水线控制台（Step1~5、日志、失败章节）
- `/novels/:novelId/chat/:sessionId`：该小说 RP Chat（复用现有 ChatPage）

### 4.2 核心页面与交互
- 小说库（Library）
  - Novel 卡片：标题、状态（未导入/处理中/已向量化/失败）、场景数、最后更新时间
  - 操作：新建小说、导入 txt、进入工作台、删除

- 导入向导（Import Wizard）
  - 上传 txt（显示编码/字符数/预览前 2000 字）
  - 设置基础参数（可选）：章节识别模式、场景长度、并发
  - CTA：开始处理（创建 pipeline job）

- 流水线控制台（Pipeline）
  - Step 卡片：Step1~5 的状态、最近一次耗时、失败原因
  - 进度：按章节完成率（读取 `chapter_index.json` 聚合）
  - 操作：一键全跑、只跑某一步、`--force`、`--redo-chapter`
  - 日志：tail 输出 + 错误高亮
  - 结果：向量库点数、角色档案数量、覆盖率最低章节提示

- RP Chat（按小说）
  - 在会话设置面板中显示当前小说名与可选切换入口
  - 新会话默认继承该小说的 profiles 与防剧透设置

### 4.3 前端状态管理与数据获取
- React Query：
  - `useQuery(listNovels)`
  - `useQuery(getNovel)`
  - `useMutation(uploadNovel)`
  - `useMutation(runPipeline)`
  - `useQuery(getJob)`（轮询，直到完成/失败）
  - `useQuery(getJobLogs)`（轮询或 SSE）
- Zustand：
  - 现有 chatStore 扩展：增加 `novelId`

### 4.4 视觉与可用性约束
- 延续现有 Liquid Glass 设计 token（`frontend/src/shared/styles/tokens.css`）以保持一致性
- 重点优化可控性：
  - 明确的“正在处理/可取消/可重试/失败原因”
  - 上传前后都能看到“本小说当前数据源”与“将写入的向量库位置”

## 5. 分阶段里程碑（建议）

### Phase 1：多小说后端骨架 + 最小 UI（2~3 天）
- 状态：已完成（2026-02-13）
- [x] Novel Registry + API（list/create/upload）
- [x] Pipeline Job（只支持“一键全跑”，单并发）
- [x] 前端 Library 列表 + 上传 + 启动作业 + job 轮询

交付验收：
- [x] UI 可导入两本小说并分别生成各自 `vector_db/<novel_id>`。

### Phase 2：流水线控制台与可观测（2~4 天）
- 状态：已完成（2026-02-13，cancel 暂未实现）
- [x] Pipeline 页面：Step 状态、失败章节、日志 tail（新增 `/novels/:novelId/pipeline`）
- [x] 支持 `step/force/redo-chapter`（前端控制台已接入，参数透传到 `POST /api/v1/novels/{novel_id}/pipeline/run`）
- [ ] Job cancel（可选）

### Phase 3：RP 多小说打通（1~2 天）
- 状态：已完成（2026-02-13）
- [x] RP API 增加 `novel_id`
- [x] 前端路由改为 `novels/:id/chat/:sessionId` 并透传 `novel_id`
- [x] 会话存储按小说隔离（推荐）

### Phase 4：产品化与体验打磨（持续）
- 支持更多格式：`epub/docx`（需要解析器）
- per-novel 参数保存（覆盖全局 config）
- 流式日志与回复（SSE）
- 备份/导出：导出某本小说的工作区与向量库

## 6. 风险与应对
- 长任务阻塞 API：MVP 用后台线程/子进程 + job 状态轮询；后续上队列/worker
- 模型/维度变更导致库不兼容：每本小说独立 vector_db_path，降低影响面
- 上传大文件失败：前端分片上传可后置，MVP 先限制大小并提示

## 7. 非目标（短期不做）
- 多用户权限、计费与配额
- “跨小说联合检索”
- 复杂的可视化标注编辑器（只做查看与重跑）
