# OpenToken UI 信息架构与优化方案

> 目标：让用户在最短路径内完成第一条 API 请求（First Request）。

## 0. 用户路径总览（AARRR中的 Activation 优先）

1. 首次进入（登录/注册）
2. 创建 API Key（必须）
3. 在 Playground 发第一条请求（必须）
4. 查看结果与成本反馈（增强信任）
5. 进入持续使用（Usage / Logs / Billing）
6. 进行治理与扩展（Settings / Docs）

---

## 1. 全局导航结构（建议）

- Dashboard
- API Keys
- Models
- Playground
- Usage
- Billing
- Logs
- Settings
- Docs

### 导航优化建议

- 左侧固定导航，顶部保留全局状态（余额、告警、账号）。
- `Playground` 和 `API Keys` 使用高亮入口（主 CTA）。
- 新用户阶段显示引导进度条：`Create Key → Test Request → Integrate`。

---

## 2. Dashboard（3秒明确下一步）

### 必备模块

1. Welcome + 环境状态
2. 三个主 CTA：
   - Create API Key
   - Open Playground
   - View Docs
3. 核心指标卡：
   - Balance
   - Requests Today
   - Success Rate
4. 新手引导（可关闭）
5. 最近请求（最近5条）

### 优化点

- 如果用户尚未创建 key，Dashboard 顶部显示醒目阻断提示。
- 如果用户已有 key 但无请求，CTA 自动切到 Playground。

---

## 3. API Keys（10秒拿到可用凭据）

### 页面结构

- Create New Key 表单：
  - Key Name（建议默认：`default-key`）
  - Permissions（All / Limited）
  - Rate Limit（可选）
- 创建成功弹窗：
  - **仅一次**展示完整 key
  - 一键复制
  - “我已保存”确认按钮
- Keys 列表：
  - 名称 / 掩码值 / 创建时间 / 状态 / 操作

### 安全与体验

- 支持 `dev` / `prod` 标签。
- 删除 key 需二次确认。
- 建议支持“最后使用时间”字段，便于清理。

---

## 4. Models（帮助选择，而不是堆模型）

### 信息层级

1. Recommended（最多3个）
2. All Models（可搜索/筛选）
3. 模型详情抽屉（延迟、价格、上下文、功能）

### 选择辅助

- 每个推荐模型附“适用场景”标签：
  - 通用对话
  - 成本优先
  - 推理优先

---

## 5. Playground（零代码验证）

### 双栏布局

左：参数与输入
- Model
- Temperature
- Max Tokens
- Prompt
- Send

右：输出与用量
- Streaming Response
- Input Tokens / Output Tokens
- Estimated Cost
- Latency

### 强化反馈

- 请求成功后显示“复制为 cURL / Python / JS”。
- 请求失败时给出可操作错误（如 401、429、模型不可用）。

---

## 6. Usage（花费可解释）

### 结构

- 时间筛选（Today / 7d / 30d / 自定义）
- 趋势图：Requests、Tokens、Cost
- 汇总卡：总请求、总 token、总花费
- 模型分布：按模型成本排名

### 优化点

- 支持导出 CSV。
- 支持按 API Key 维度查看，便于团队核算。

---

## 7. Billing（充值顺畅 + 对账透明）

### 结构

- 当前余额
- Add Credits
- 固定档位 + 自定义金额
- 交易流水（充值、消费、退款）

### 优化点

- 余额低于阈值自动告警（邮件/站内）。
- 显示“预计还能跑多少请求”（按近期平均成本估算）。

---

## 8. Logs（开发者排障主战场）

### 列表维度

- Time / Model / Status / Tokens / Latency / Cost
- 过滤器：Model、Status、Time、Key

### 详情面板

- Request Payload
- Response Payload
- Error Message
- Trace ID

### 优化点

- 支持一键重放（Replay Request）到 Playground。

---

## 9. Settings（治理与风险控制）

- 账户信息：邮箱、密码、2FA
- API 策略：默认限速、允许模型
- 安全策略：IP 白名单、Key 限制
- Danger Zone：账户注销

---

## 10. Docs（1分钟跑通）

### Quick Start 必须包含

1. 获取 API Key
2. Base URL
3. OpenAI 兼容请求示例（curl / Python / JS）
4. 常见错误码与排查

---

## 11. 最小可用版本（MVP）优先级

P0（必须）
- Dashboard
- API Keys
- Playground
- Logs（基础）
- Docs（Quick Start）

P1（增强）
- Usage 图表
- Billing 完整流程
- Models 推荐系统

P2（进阶）
- 团队协作与角色权限
- 告警中心
- 请求回放/对比

---

## 12. 可执行的前端交付清单

- 页面路由与导航定义
- 每页线框图（low-fi）
- 状态机（空态/加载/错误/成功）
- API 对接字段表（前后端契约）
- 埋点事件（首个 key 创建、首个请求成功）

