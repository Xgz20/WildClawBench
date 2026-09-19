# DoubaoWork Web 下一批接入边界

COMMON 于 2026-09-19 对已发布源码 `dc5ff64` 的 Web 公共入口完成只读复核。本文件约定下一批实现范围，不表示该批代码已完成。来源任务仍为 MAC-DOUBAOWORK-WEB，所有桌面验证继续由控制任务分配。

## 可信绑定不依赖不存在的原生字段

现有 [Web Driver 契约](../../../../tools/report/skills/web-e2e/execute-web-e2e/references/driver-contract.md)允许 DOM/视觉终态和完整路径或稳定标识确认工作空间。Doubao 原始 trajectory 不含 cwd、时间戳或 Agent 终态；这些原生字段继续保留 null/unverified，不设为永久硬阻塞。正式收口可以采用可审计的等价证据链，但当前旧 canary 尚不满足。

平台必须建立并归档：

1. 当前 conversation → project → 完整 tooltip/workspace 的归属链；保存 DOM 事实、时间、截图和 artifact 哈希，不仅是“匹配成功”布尔值。排除同 basename、错项目和旧会话。
2. 发送前 Prompt SHA/bytes、发送后绑定 conversation 的 user message 回读、恢复后同会话复核。若规范化空行或尾段，明确算法和原文来源；不靠标题或最近更新时间猜测身份。
3. 每次 `inspectPage` 的 `current_conversation_id` 等于已绑定 ID；`resumeDevelopmentRun` 不能只在初次导航时检查，后续切换会话必须失败关闭。
4. 已验证的正向 UI 完成标识，并确认该会话没有 busy/stop/pending/error。文本稳定或文件稳定单独不构成 Agent 终态。工具子任务的 completed 不冒充主任务结束。
5. 已绑定原生目录的轨迹原件、规范化 transcript、UI 回复及截图、binding 索引，各自记录相对路径、SHA-256、大小、scope 与 completeness。采集时间不冒充原生事件时间。
6. 精确候选进程清理、残留检查、实际经过的 quiet window，以及之后的候选冻结。存在进程/轨迹/UI 冲突就保持 NEEDS_ATTENTION。

旧 canary 缺精确 live revision 和完整最后回复/截图，继续保持其开发状态；不得事后改造为正式通过。

## 修改归属与公共复用

| 负责人 | 文件 / 符号 | 本批范围 |
| --- | --- | --- |
| Doubao 平台 | `drivers/doubaowork/driver.mjs`、专属 state/native/platform 模块及 tests | 上述绑定、终态证据、每次观察身份核验、精确 cleanup、标准 CLI/state 投影及本平台 finalize；同时交付反例与可消费接口 |
| COMMON | `drivers/workbuddy/batch.mjs::BATCH_PROFILES`、`buildDriverArgs`、`buildExecutionReceipt` | 接入平台已验证 CLI/state；默认 ui_slots=1/run_slots=1；增加 Doubao 专属严格证据 gate，不改变旧 Harness 语义 |
| COMMON | `drivers/metrics/collect.mjs::collectLocalMetrics` | 注册 Doubao 专属 parser；保留既有 WorkBuddy/Qwen native cwd 检查，不能为 Doubao 放宽它们 |
| COMMON | execute 脚本、run macOS application 路由、版本/布局/发行测试 | 新入口、路由与依赖闭包；不得只加 profile 就宣布执行支持 |

表中 Driver 路径均相对于 `tools/report/skills/web-e2e/execute-web-e2e/`。平台先提交自己目录中的模块和 fixture；公共文件由 COMMON 统一接线，避免并行修改。

`workbuddy/lib.mjs` 中 `resolveExecutionIdentity`、`createExecutionRecord`、`updateExecutionRecord`、`snapshotTree` 已支持 Harness profile，可以复用。各旧 Driver 的私有 finalize 含客户端专属逻辑，不能直接调用它替代 Doubao 收口。

`metrics/capture.mjs::captureResourceMetrics` 已透传 `state.session`，可携带验证后的 binding 索引；多 raw/UI artifacts 放在 automation sidecar 与 `collection.sources[]`。优先保持现有 Web v1 正式记录/回执与 metrics 表达，不引入 General trace v2 或新 Web schema 来解决单客户端问题。

当前通用 batch 只检查 `terminal_process_cleanup.success`，旧 WorkBuddy cleanup 在非 Windows 可返回 supported=false/success=true。Doubao 专属 gate 必须验证 supported、来源、身份、残留和实际 quiet-window，拒绝继承该宽松结果。正式 record writer、评分、回传和报告可沿用现有协议；缺少的原始计数保持 null + known subtotal + coverage，不把 14 个已知工具调用填为完整总量。

## 合入与验证顺序

平台绑定/cleanup 模块及反例 → COMMON 注册和严格 gate → 组合与 ZIP 脱仓测试 → 新冻结批次单题 → execution/receipt → 评分/报告。反例至少包括错会话/错项目、旧回复、Prompt 不匹配、pending/error、缺少正向终态、同名无关进程、PID 复用、迟到进程、artifact/候选漂移以及未支持 cleanup。

UI 的真实语义只由新受控时段验证。离线 fixture、原生历史样本和现有旧 canary 分开登记，不用缺失指标阻塞可完成的适配开发。
