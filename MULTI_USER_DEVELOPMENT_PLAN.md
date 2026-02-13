# 多用户与数据隔离系统设计与开发计划（AIRP2）

已确认关键决策：

- 公共库：引用式公开（`novels.visibility=public`，不复制数据）
- 数据库：SQLite

## 0. 现状分析（基于当前仓库）

当前系统是“单租户、多小说”：

- API 入口集中在 `api/rp_query_api.py`：
  - Novel CRUD：`/api/v1/novels/*`
  - 上传：`/api/v1/novels/{novel_id}/upload`
  - Pipeline Job：`/api/v1/novels/{novel_id}/pipeline/run`、`/api/v1/jobs/*`
  - RP Chat：`/api/v1/rp/*`（支持 `novel_id` 做多小说路由）
- 多小说隔离依赖文件系统目录：
  - 小说工作区：`data/novels/<novel_id>/...`（由 `services/novel_registry.py` 维护 `data/novels/index.json`）
  - 向量库：`vector_db/<novel_id>/...`（Qdrant local file mode）
  - 会话：`data/novels/<novel_id>/sessions/<session_id>.json`（`services/session_state.py`）
- 无“用户/权限/游客”概念：所有调用者看到同一份 `novels` 列表；只要知道 `novel_id` 就可访问/删除/跑流水线；只要知道 `session_id` 就可读取会话。

结论：需要在“NovelRegistry / SessionStateStore / JobService / API 鉴权”四条链路上引入 **用户身份（user_id）** 与 **访问控制（ACL）**，并把“公开库（Public）”从“用户私有库（Private）”中明确分层。

## 1. 目标与约束

### 1.1 必须满足的需求

- 多用户同时使用（并发访问 API、并发聊天；流水线可按资源策略限制并发）。
- 数据强隔离：
  - 每本小说归属某个用户（owner_user_id）。
  - 小说数据（workspace、vector_db、logs、sessions）按用户 ID 绑定落盘，互不串写。
  - API 强制授权：任何人不可通过猜测 `novel_id`/`job_id`/`session_id` 读取他人私有数据。
- 公开库：
  - 用户可选择把某本小说公开到公共数据库（Public Library）。
  - 公开后其他用户与游客可“浏览/聊天（只读）”。
- 游客模式：
  - 未登录用户可聊天（可选择“无小说模式”或“公共小说”）。
  - 未登录用户不可导入小说、不可启动流水线、不可删除小说。
- 账号体系：
  - 用户名 + 密码注册/登录。

### 1.2 推荐的工程约束（为了“隔离”真实可用）

- **不要依赖“ID 难猜”当作权限**：所有读写都必须检查 owner/visibility。
- 会话与聊天记录归属“用户/游客会话”，不与公共库混存。
- 元数据与授权信息不要继续存在 `index.json`：多进程/多 worker 会有竞争风险；建议落 DB。

## 2. 总体架构（推荐实现）

采用两套存储命名空间 + 一个“公共库视图”：

1. **User Namespace（私有）**
   - 每个用户有独立根目录：`data/users/<user_id>/...`
   - 每本小说：`data/users/<user_id>/novels/<novel_id>/...`
   - 向量库：`vector_db/users/<user_id>/<novel_id>/...`
   - 日志：`logs/users/<user_id>/novels/<novel_id>/...`
   - 会话：`data/users/<user_id>/sessions/<scope>/<session_id>.json`

2. **Public Library（公共库视图，引用式公开）**
   - 不复制数据，不创建 public workspace/vector_db。
   - 公共库是 DB 的一个“公开列表视图”：`novels.visibility = public` 的小说会出现在公共列表中。
   - 公开小说的数据仍在 owner 的 User Namespace 下，由服务端以“只读”方式提供检索与聊天能力。

3. **Guest Namespace（游客）**
   - 游客根目录：`data/guests/<guest_id>/sessions/<scope>/<session_id>.json`
   - 游客只允许使用 RP Chat（读公共库数据源或无小说模式），禁止任何导入与流水线。

“数据源（novel workspace/vector_db/profiles）”与“会话存储（sessions）”必须解耦：

- 同一公共小说，用户 A 与用户 B 的聊天会话都存放在各自的 `sessions` 下，避免互相读到历史。

## 3. 数据模型（DB）

使用 SQLite 作为唯一真源 DB（用户/授权/元数据），避免 `index.json` 的并发一致性问题。

### 3.1 表（最小闭环）

- `users`
  - `id` (uuid)
  - `username` (unique, normalized)
  - `password_hash` (argon2id/bcrypt)
  - `created_at`

- `auth_sessions`
  - `id` (uuid)
  - `session_token` (random, 存库建议保存 hash；cookie 保存原 token)
  - `user_id` (nullable)
  - `guest_id` (nullable)
  - `created_at`, `expires_at`, `revoked_at`, `last_seen_at`

- `novels`
  - `id` (uuid) 作为 `novel_id`
  - `owner_user_id` (uuid) 必填
  - `title`
  - `visibility` ("private"|"public")：引用式公开开关（public 会出现在公共列表，可被他人只读聊天）
  - `status` ("created"|"uploaded"|"processing"|"ready"|"failed"|"deleted")
  - `source_meta` (json)
  - `stats` (json)
  - `last_job_id`, `last_error`
  - `created_at`, `updated_at`

- `pipeline_jobs`
  - `id` (uuid) 作为 `job_id`
  - `novel_id` (uuid)
  - `owner_user_id` (uuid) 用于快速鉴权（冗余但方便）
  - `spec` (json: step/force/redo_chapter)
  - `status`, `progress`, `current_step`, `error`
  - `log_path`
  - `created_at`, `started_at`, `finished_at`

说明：即使继续把 pipeline 实际执行留在“进程内线程”，**job 元数据**也应该放 DB，避免重启/多 worker 时的状态错乱。

## 4. 权限模型（ACL）

定义 `Actor`：

- `actor.type`：`user` | `guest`
- `actor.user_id`：登录用户才有
- `actor.guest_id`：游客会话才有

核心规则：

1. 私有小说（visibility=private）：
   - 只有 owner 用户可读/写。
2. 公开小说（引用式公开，visibility=public）：
   - 任意 actor 可读与聊天；只有 owner 可写。
3. 游客：
   - 禁止：Novel 创建、上传、跑流水线、删除。
   - 允许：RP Chat（无小说 / 公共小说），读取公共小说元信息。
4. 会话：
   - `session_id` 只是客户端标识，不做授权依据。
   - 读取/写入会话必须绑定当前 actor 的 session 目录或 DB 记录。

## 5. API 设计（v1 扩展）

### 5.1 认证

- `POST /api/v1/auth/register`
  - body: `{ username, password }`
- `POST /api/v1/auth/login`
  - body: `{ username, password }`
  - set-cookie: `airp_sid=<session_token>; HttpOnly; SameSite=Lax; Secure(生产)`
- `POST /api/v1/auth/logout`
  - revoke session
- `GET /api/v1/auth/me`
  - return: `{ mode: "user"|"guest", user?: {id, username} }`
- `POST /api/v1/auth/guest`
  - 创建/刷新 guest session（前端启动时调用一次，确保游客也有稳定 guest_id）

### 5.2 Novel（私有库）

- `GET /api/v1/novels`
  - 需要登录；返回当前用户私有小说列表
- `POST /api/v1/novels`
  - 需要登录；创建私有小说
- `GET /api/v1/novels/{novel_id}`
  - owner 可读；若该 novel “引用式公开”则任何 actor 可读（只读字段）
- `PATCH /api/v1/novels/{novel_id}`
  - owner：改 title、改 visibility（是否公开）
- `DELETE /api/v1/novels/{novel_id}`
  - owner：删除（可选是否删除 vector_db）

### 5.3 Public Library（公共库）

- `GET /api/v1/public/novels`
  - 任意 actor 可访问：列出所有 `visibility=public` 的小说（仅返回安全字段，不返回 paths/source 等敏感信息）
- `GET /api/v1/public/novels/{novel_id}`
  - 任意 actor 可访问：获取公开小说详情（安全字段）

### 5.4 上传与流水线（仅 owner）

- `POST /api/v1/novels/{novel_id}/upload`
- `POST /api/v1/novels/{novel_id}/pipeline/run`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/logs`

全部需要：登录 + owner。

### 5.5 RP Chat（允许游客）

- `POST /api/v1/rp/query-context`
- `POST /api/v1/rp/respond`
- `GET /api/v1/rp/session/{session_id}?novel_id=...`

鉴权规则：

- `novel_id` 为空：允许（无小说模式）。
- `novel_id` 非空：必须满足“当前 actor 对该 novel 有 read 权限（owner 或 public）”。
- 会话存储：使用当前 actor 的 session root（与 novel 的 workspace root 解耦）。

## 6. 关键代码改造点（落地到当前工程）

### 6.1 后端结构调整建议

当前所有路由都在 `api/rp_query_api.py`，建议拆出：

- `api/auth_api.py`：注册/登录/游客
- `api/novels_api.py`：novel CRUD、上传、公开开关（visibility）
- `api/jobs_api.py`：job 查询与日志
- `api/rp_api.py`：rp endpoints（保留现有 service 但增加 ACL）
- `api/app.py`：create_app、middleware、依赖注入

### 6.2 服务层新增/重构

- `services/auth/*`
  - Password hash：argon2id/bcrypt
  - Session：创建/校验/续期/注销
- `services/storage_layout.py`
  - 统一计算路径：user/guest 两套 root（public 仅是 visibility 视图，不复制数据）
  - 明确哪些目录可写、哪些只读
- `services/novels_service.py`
  - 从 DB 读写 novel 元数据
  - 返回 data source paths（workspace/vector_db/profiles/...）
- `services/rp_router.py`
  - 构建 RPQueryService 时：
    - data source paths 来自 novel
    - session_store.base_dir 来自 actor（user/guest）并按 novel 分桶
- `services/pipeline_jobs.py`
  - job 增加 owner_user_id
  - 路由层按 owner 鉴权访问 job/logs

### 6.3 前端改造要点

新增页面与状态：

- `/login`、`/register`
- 顶部或侧边栏增加“当前身份：游客/用户名”与“登录/退出”
- `/library`：
  - 登录用户：展示“我的小说 + 公共小说”两个 Tab
  - 游客：仅展示“公共小说”，隐藏“新建/上传/跑流水线/删除”
- axios client：开启 `withCredentials` 以携带 cookie

## 7. 开发计划（里程碑与验收）

时间按“1 名工程师”粗估；如并行前后端可压缩。

### Phase 0：需求定稿（0.5~1 天）

- 已确认公开库策略：引用式公开（`visibility=public`）
- 已确认 DB：SQLite
- 确认游客能否“聊天公共小说”（推荐：可以）

验收：
- 输出本文件的最终版决策（公开策略、DB 选择、权限边界）。

### Phase 1：账号体系 + 会话（1~2 天）

- 后端：
  - `users`、`auth_sessions` 表与迁移
  - 注册/登录/退出/me/guest 接口
  - 中间件：解析 `airp_sid`，注入 `actor`
- 前端：
  - 登录/注册页
  - 全局拉取 `/auth/me`，展示身份

验收：
- 新用户可注册并登录；退出后回到游客。
- 游客访问 `/auth/me` 返回 guest 模式并拥有稳定 guest_id（cookie）。

### Phase 2：Novel 多用户隔离（2~4 天）

- DB `novels` 表 + CRUD
- 存储布局改造：
  - 新小说落盘路径包含 `user_id`
  - 上传、pipeline、日志、向量库路径全部改成 user-scoped
- API 改造：
  - `GET /novels` 仅返回我的
  - `GET /novels/{id}` 仅 owner 可见（除非 public）

验收：
- A 用户创建/上传/跑流水线的小说，B 用户无法 list/get/delete/run（403/404）。

### Phase 3：RP Chat ACL + 会话隔离（1~2 天）

- RP endpoints：
  - 访问 novel 前先 ACL check（owner or public）
  - session_store 改为 actor-scoped（用户/游客互不读取）
- 前端：
  - Chat 仍可用；游客进入 chat 不报错

验收：
- 同一 `session_id` 在不同账号下不会读到彼此 turns。
- 访问他人私有 novel_id 进行检索会得到 403/404。

### Phase 4：公共库（1~3 天）

- 引用式公开：
  - `PATCH /api/v1/novels/{id}` 支持 `visibility=public|private`
  - `GET /api/v1/public/novels` 列出所有 `visibility=public` 的小说（安全字段）

验收：
- 游客可从公共库选择某本小说进入聊天并检索到引用。
- 公共库小说不可被游客上传/跑流水线/删除（403）。

### Phase 5：游客限制与体验收尾（0.5~1.5 天）

- 前端对未登录状态隐藏导入/流水线入口
- 后端对写接口统一返回 401（未登录）或 403（无权限）
- 加上基础防滥用：
  - 登录/注册限频（简单内存计数即可，后续可上 redis）
  - 上传大小与类型继续保持

验收：
- 游客只能聊天；所有导入/运行按钮不可用且后端也拒绝。

### Phase 6：迁移与运维（1~2 天）

- 数据迁移脚本：
  - 把旧 `data/novels/<novel_id>` 移动到某个“管理员用户”名下或发布为 public
  - 同步迁移 `vector_db/<novel_id>`
- 部署文档：
  - `DATABASE_URL`、`AUTH_SECRET`、cookie secure、备份策略

验收：
- 旧数据可被“管理员用户”或公共库正常访问。

## 8. 风险清单与对策

- 文件系统隔离但多 worker 并发写：
  - 元数据与 job 必须落 DB；文件写入保持单 job 或 per-novel lock。
- Qdrant local file mode 的并发读写：
  - 同一 novel 在 pipeline（写）与 RP（读）并发时可能有一致性问题。
  - MVP：pipeline 运行时将 novel 标为 processing，并在 RP 层拒绝读取或提示“处理中”。
- 公开库的版权与合规：
  - 需要明确“公开”含义（是否允许被他人访问、是否可下载、是否可删除）。
