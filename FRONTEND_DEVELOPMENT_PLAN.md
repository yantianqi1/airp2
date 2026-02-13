# 前端开发文档（长期方案升级版：Liquid Glass Premium）

## 1. 目标与设计基线

### 1.1 目标
- 基于 `Vite + React + TypeScript` 构建长期可维护的 RP 前端。
- 完整打通会话、检索、回复、引用展示。
- 视觉上采用“液态玻璃”方向，追求高端、克制、精致。

### 1.2 设计基线
- 设计灵感参考 macOS 新一代液态玻璃质感，但不复制官方资产。
- 主风格为“明亮高透 + 层次景深 + 精准动效”。
- 默认浅色高端主题，支持后续扩展深色。

## 2. 视觉方向（Liquid Glass Premium）

### 2.1 核心视觉原则
- `透`：UI 面层可见背景氛围，不使用硬白大色块。
- `薄`：边框轻、阴影轻、分割轻，避免厚重企业后台感。
- `稳`：动效短且稳，不做炫技跳跃。
- `准`：重要信息（回复、引用、章节限制）有明确视觉层级。

### 2.2 色彩系统（避免通用紫色套路）
- 主色：`Ocean Blue`（操作高亮）
- 辅色：`Mint`（成功/可用）
- 警示：`Amber`（限制/剧透边界提示）
- 中性色：`Frost White / Graphite`

建议 token：

```css
:root {
  --bg-0: #f3f6fb;
  --bg-1: #eaf1f8;
  --glass-fill: rgba(255, 255, 255, 0.42);
  --glass-stroke: rgba(255, 255, 255, 0.62);
  --text-1: #0f1728;
  --text-2: #3e4a62;
  --brand: #3a7bff;
  --mint: #2db79f;
  --amber: #f2a93b;
  --shadow-soft: 0 12px 40px rgba(27, 39, 77, 0.14);
}
```

### 2.3 字体系统（高端感）
- 中文：`PingFang SC`, `Hiragino Sans GB`, `Source Han Sans SC`
- 英文数字：`SF Pro Display`, `Avenir Next`, `Geist`
- 避免默认 `Arial/Roboto/Inter` 直出。

### 2.4 背景与质感
- 背景采用渐变 + 轻噪点 + 大尺寸柔光色块。
- 卡片采用 `backdrop-filter: blur(...) saturate(...)`。
- 所有玻璃面板需有“内高光 + 外阴影 + 半透明描边”三层结构。

## 3. 交互与动效规范

### 3.1 动效节奏
- 页面初始：容器上浮 + 透明度进入（280ms）。
- 新消息：轻微上移 + 淡入（180ms）。
- 侧栏切换：横向位移 + 模糊过渡（220ms）。

### 3.2 动效原则
- 动效只为传达层级变化和状态反馈。
- 禁止高频弹跳、旋转、无意义粒子。
- 提供 `prefers-reduced-motion` 降级策略。

### 3.3 反馈状态
- 请求中：按钮进入“液态加载态”，消息区骨架屏。
- 成功：引用条目标注轻微高亮。
- 失败：错误卡片使用半透明红橙警示层。

## 4. 信息架构与页面结构

### 4.1 路由
- `/`：会话入口（新建 / 恢复）
- `/chat/:sessionId`：RP 主界面

### 4.2 主界面布局（Desktop）
- 左栏（20%）：会话控制
  - `session_id`
  - `unlocked_chapter`
  - `active_characters`
  - 调试模式开关
- 中栏（55%）：对话区
  - 消息流
  - 输入框
  - 操作按钮
- 右栏（25%）：证据区
  - citations
  - worldbook facts
  - debug scores

### 4.3 移动端布局（Mobile）
- 默认单栏消息流。
- 引用与调试区以抽屉形式展开。
- 输入区固定底部，注意安全区（iOS notch）。

## 5. 组件设计规范

### 5.1 `AppShellGlass`
- 作为全局玻璃容器，负责背景层和三栏网格。
- 支持桌面悬浮窗风格圆角（18~24px）。

### 5.2 `SessionConfigPanel`
- 使用分组卡片管理章节限制和活跃角色。
- `active_characters` 用可删除标签组件。

### 5.3 `ChatMessageList`
- 用户气泡：偏品牌色玻璃胶囊。
- 助手气泡：中性玻璃卡片，底部挂载引用条。
- 每条助手消息支持“展开/折叠证据摘要”。

### 5.4 `ChatComposer`
- 多行输入框 + 发送按钮 + 调试按钮。
- 输入框聚焦时玻璃高光增强，边框细亮线。

### 5.5 `CitationPanel`
- 每条引用展示 `chapter / scene / excerpt`。
- 点击引用可定位到对应回复并高亮。

### 5.6 `DebugPanel`
- 折叠展示：
  - `debug_scores`
  - `query_understanding`
  - 请求耗时

## 6. 技术实现（长期可维护）

### 6.1 技术栈
- 构建：`Vite`
- 框架：`React 18`
- 语言：`TypeScript`
- 路由：`React Router`
- 远程状态：`@tanstack/react-query`
- 本地状态：`Zustand`
- 请求库：`Axios`
- 校验：`Zod`
- 动效：`Framer Motion`
- 测试：`Vitest + React Testing Library + MSW`

### 6.2 样式策略
- `CSS Variables + CSS Modules`（推荐）
- 统一放置设计 token：`src/shared/styles/tokens.css`
- 组件样式内强制引用 token，不允许硬编码颜色散落。

## 7. 前后端接口对接（与现有后端直连）

后端基地址：
- 开发环境：`http://localhost:8011`
- 环境变量：`VITE_API_BASE_URL`

### 7.1 `POST /api/v1/rp/query-context`
- 用途：检索上下文（worldbook + citations + debug）。
- 前端触发：
  - 调试模式下发送前调用；
  - 用户点击“仅检索证据”。
- 请求体：
  - `message`（必填）
  - `session_id`（必填）
  - `unlocked_chapter?`
  - `active_characters?`
  - `recent_messages?`
- 响应映射：
  - `worldbook_context` -> 右侧证据面板
  - `citations` -> 引用列表
  - `debug_scores/query_understanding` -> 调试面板

### 7.2 `POST /api/v1/rp/respond`
- 用途：返回最终助手回复。
- 前端触发：
  - 用户发送消息（默认主路径）。
- 请求体（推荐完整透传）：
  - `message`
  - `session_id`
  - `worldbook_context?`
  - `citations?`
  - `unlocked_chapter?`
  - `active_characters?`
  - `recent_messages?`
- 响应映射：
  - `assistant_reply` -> 助手气泡
  - `citations` -> 消息底部引用
  - `worldbook_context` -> 刷新证据面板

### 7.3 `GET /api/v1/rp/session/{session_id}`
- 用途：恢复会话。
- 前端触发：
  - 会话页面首次加载；
  - 用户手动刷新会话。
- 响应映射：
  - `turns` -> 历史消息
  - `max_unlocked_chapter/active_characters` -> 左栏配置

## 8. 状态与数据流

### 8.1 React Query
- `useQuery(getSession)`
- `useMutation(queryContext)`
- `useMutation(respond)`

### 8.2 Zustand
- `sessionId`
- `unlockedChapter`
- `activeCharacters`
- `messages`
- `latestWorldbookContext`
- `latestCitations`
- `debugMode`

### 8.3 推荐调用流程
- 生产模式：仅调 `respond`（后端内部可自动检索）。
- 调试模式：先 `query-context`，再 `respond`。

## 9. 工程目录建议

```text
frontend/
  src/
    app/
      router.tsx
      providers.tsx
    pages/
      SessionEntryPage.tsx
      ChatPage.tsx
    features/
      chat/
      session/
      evidence/
      debug/
    shared/
      api/
        client.ts
        rp.ts
      types/
        rp.ts
      lib/
        zodSchemas.ts
      styles/
        tokens.css
        glass.css
```

## 10. 分阶段实施计划（优化后）

### Phase 0：视觉系统定义（0.5 天）
- 完成色彩、字体、阴影、圆角、动效 token。
- 输出静态视觉样稿（首页 + 聊天页）。

### Phase 1：前端工程搭建（0.5 天）
- 初始化 Vite + React + TS。
- 接入路由、状态、请求层、lint/test 基建。

### Phase 2：高保真静态界面（1 天）
- 实现三栏布局与液态玻璃组件。
- 完成桌面与移动端适配。

### Phase 3：接口联调（1 天）
- 打通 `session/query-context/respond` 三接口。
- 实现消息流、引用、调试信息渲染。

### Phase 4：动效与稳定性（1 天）
- 完成关键动效与降级策略。
- 完成错误态、超时重试、空状态。
- 前端测试与联调验收。

## 11. 验收清单（设计 + 功能）

### 11.1 功能验收
- 可创建/恢复会话。
- 可发送消息并得到回复。
- 每条回复可查看引用。
- 调试模式可查看检索分数与理解结果。

### 11.2 设计验收
- 玻璃层级清晰，未出现“糊成一片”。
- 文字对比度满足可读性（WCAG AA）。
- 动效自然、克制，不卡顿。
- 移动端不破版，输入区操作稳定。

## 12. 后端协作建议

- 后端启动：
  - `uvicorn api.rp_query_api:create_app --factory --host 0.0.0.0 --port 8011`
- 建议在 FastAPI 增加 CORS：
  - 允许 `http://localhost:5173`
- 后续可增加流式回复接口（SSE）以提升沉浸感。
