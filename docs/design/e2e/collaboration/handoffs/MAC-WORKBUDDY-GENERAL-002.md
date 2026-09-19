# MAC-WORKBUDDY-GENERAL-002：真实发送前失败收口与输入就绪修复

| 字段 | 值 |
| --- | --- |
| 交接 ID / 创建时间 | `MAC-WORKBUDDY-GENERAL-002` / 2026-09-19 20:59 +08:00 |
| 来源任务 / 唯一负责人 | `MAC-WORKBUDDY-GENERAL` / `01a0b8d2-0ea9-7012-ac4f-c2bd69dc8b7b` |
| 目标任务 | COMMON 控制任务 `01a0b79a-09d7-7271-810a-7796036b8f35` |
| 基线 / 实现 SHA / 必需依赖 | 组件绑定基线 `b3ac3da374165d74a41a3198e13d05928d671552`；输入修复 `5bea7621e4c90222d3f2e0000ab1ca6093af6e0b`；依赖已接收 COMMON-002 / `general-contracts=1.2.0` / `desktop-app-discovery=1.2.0` |
| 集成分支 / 集成状态与 SHA | `feature/astroncode-eval` / 新修复未集成、未 push；由 COMMON 审查后登记原始→集成 SHA |
| 修改范围 | WorkBuddy `ui.mjs` / `execute.mjs`、专属 execution tests、P2/canary 证据索引与任务卡；未修改共享 finalizer、公共 Schema 或 COMMON 元数据 |
| 关联任务与验收 ID | Mac P2/P3；C02/C04/C07/C09/C13–C16、CV02/CV03/CV04/CV07/CV11/CV12、G04/G05 |

本交接新增于已消费的 `MAC-WORKBUDDY-GENERAL-001` 之后，不改写或撤销旧交接。它记录旧 P2 canary 的最终发送边界、用户现场恢复和后续修复；COMMON-003 如仅包含此前已审查的 P2 和已知输入缺口，不得据此把 `5bea762` 写成真机验证通过。

## 变化与兼容性

旧实现通过 `textContent + InputEvent` 填入 Prompt，DOM 内容及 SHA 可正确回读，但真实 WorkBuddy 编辑器内部状态未更新，发送控件保持 disabled。canary 的 `dispatchPrompt` 因可用发送控件为 0 而退出；没有点击或发送。

`5bea762` 将输入路径改为：

1. 再次确认唯一可见编辑器为空并精确获得焦点；
2. 只调用一次 CDP `Input.insertText`；
3. 轮询并要求唯一编辑器内容与完整 Prompt 精确一致；
4. 要求唯一发送控件存在且 enabled；
5. 上述条件全部通过后，才将 journal 写为 `intent_persisted`、`dispatch_attempt_count=1` 并 armed。

因此 DOM 内容正确但控件 disabled 时现在属于发送前失败：`phase=FAILED`、`send_status=not_sent`、`dispatch_attempt_count=0`、dispatch=0，不强点 disabled 控件。armed 之后的既有不重发语义不变。CLI、journal schema、原生身份映射、状态机终态语义、公共组件版本和其他 Harness 不变。

## 已有证据与未验证范围

旧 release 的 source revision 为 `b3ac3da374165d74a41a3198e13d05928d671552`，suite SHA-256 为 `54f4f7934413646b89b5fc3fba50db9d2a4ee4e750eeec8d70971759e1e8ad3e`。独立 prepare 对任务 `01_Productivity_Flow_task_001_expense_policy_check` 的 execution/scoring 双包和 batch verify 均 PASS；Prompt SHA-256 为 `deb5f6554a69c93afe1e6ad1f1fb6d678adedfc8860dda0875afaa6d4281e621`。

真实 canary attempt 为 `3e554524-6599-4182-aecc-3257977867c0`。journal 记录一次 reservation，实际 candidate click 0、send 0、native session 0；conversation/request/cwd 均未绑定，phase 为 `NEEDS_ATTENTION`。同 attempt 的 `--resume --observe-once` 只观察，没有 redispatch。该 attempt 永不重发、重置或替换身份，也不计为模型失败或已执行任务。

用户旧草稿恢复证据显示正文和 HTML 哈希与备份完全一致，仅动态 `style` 属性不同；candidate Prompt 已移除，Workspace/conversation 为空，模型/权限未变。私有目录为 0700、文件为 0600；正文和截图不入 Git、候选或评分包。完整原件留在来源机器：

```text
/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/slot02/
```

Git 可取得的脱敏索引为 [WorkBuddy P2 离线门禁与 canary 收口证据](../../../general-e2e/evidence/workbuddy-macos-p2-offline-20260919/README.md)。本地目录名沿用 `slot02`，控制桌面最终状态为 `SLOT03_RELEASED`；两者不能解释为仍持有桌面。

`5bea762` 验证结果：

```text
node --check ui.mjs / execute.mjs                            PASS
node --test tests/general_e2e/workbuddy_*.test.mjs          25/25
node --test tests/general_e2e/*.test.mjs                    93/93
相关 Python（仓库 .venv）                                   60/60
npm ci && npm ls --depth=0（WorkBuddy 专属目录）            PASS / empty
git diff --check                                             PASS
```

新增 fixture 覆盖 `Input.insertText` 单次调用、DOM 内容正确但 disabled 的超时，以及 disabled 在 armed 前失败时 attempt count 0 / dispatch 0。隔离开发浏览器 fixture 被浏览器安全策略拒绝，且不得用原始 CDP 或其他浏览器面绕过，所以当前只有离线有状态 client 证明；尚未证明真实 WorkBuddy 的编辑器事件路径。

## 接收方动作

| 接收任务 | 要求级别 | 下一动作/真实入口与配置 | 通过条件/验收 ID | 失败或缺依赖时 |
| --- | --- | --- | --- | --- |
| COMMON | REQUIRED_BEFORE_EXECUTION | 审查并集成 `5bea762`；复跑 WorkBuddy 25 项、General Node 全量和相关 Python；登记原始→集成 SHA | 新修复保持 armed 前 enabled 门禁，其他 Harness/公共契约无回归 | 不修改旧 canary journal，不用 `b3ac3da...` 的 release 继续真机验证；回报具体失败 |
| COMMON | REQUIRED_BEFORE_EXECUTION | 从 `5bea762` 或更高已审查 revision 重建独立 release/execute Skill；记录新的 source revision、Skill ZIP 与 suite SHA | release build/verify、单题 prepare/batch verify 均 PASS；新包确实包含 `Input.insertText` 修复 | 保留离线结论，不分配真机执行 |
| COMMON 控制任务 | REQUIRED_BEFORE_EXECUTION | 只在重新分配桌面 slot 后运行全新 attempt；重探进程/CDP、原生 session、UI 空闲、模型 `xopglm52`、权限 `default-sandbox` 和 Workspace | 一次实际发送；conversation/request/cwd 唯一绑定；同 attempt resume 不重发 | 任一发送边界或身份不明即 `NEEDS_ATTENTION`；释放 slot；旧 attempt 永不重发 |
| COMMON | REQUIRED_BEFORE_CLAIM | 接入 WorkBuddy 专属 collector、trace-index v2 和基于公共 macOS task-process 原语的真实 cleanup hook | 原生 v2 输出、完整性/候选冻结和真实子进程清理证据通过 | 不声明正式 collect、评分闭环或生产准入 |
| COMMON 控制任务 | INFORMATIONAL | 私有草稿/截图继续留在来源机器 0700/0600 目录，不复制到集成、candidate 或 scoring | Git 仅保留长度、哈希、一致性和权限结论 | 若需交付原件，另走受控私有路径，不经 Git |

## 接续与风险

后续真机验证必须使用新 release、新 slot 和新 attempt。旧 attempt 的 reservation 已消费，即使已知实际 click/send 为 0，也不能复用 journal 或把 attempt count 改回 0。释放时的 WorkBuddy PID/CDP 状态可能漂移，不能当作下次运行配置；每次都必须重新探测。

回退方式是继续使用 `b3ac3da...` 做只读或离线分析，但禁止用它发送 Prompt。`5bea762` 尚未获得真实编辑器事件证明，也没有 WorkBuddy 专属 collect/cleanup 证明；测试和提交不能扩大为客户端生产可用结论。
