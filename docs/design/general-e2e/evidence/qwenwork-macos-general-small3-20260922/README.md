# QwenWork macOS General 三题单槽 canary

日期：2026-09-22（Asia/Shanghai）。范围为 QwenWorkCN 1.0.6 / macOS x86_64 的三个固定 smoke 任务，单槽顺序执行；覆盖文件任务、工具/文件任务和纯回复任务，以及 automated、hybrid、llm_judge 三种评分类型。不代表五题三路、Windows、Apple Silicon 或 60 题全量准入。

## 正式结果

- 批次：`qwenwork-macos-general-20260922-small3-r6`；unit：`qwenwork-macos-x86-64`；任务范围：`01_Productivity_Flow_task_005_support_handoff`、`02_Code_Intelligence_task_001_temperature_cli_fix`、`03_Social_Interaction_task_003_colleague_leave_reply`。
- 三题均只发送一次 Prompt，均取得唯一 session/conversation/sub-chat/local project/cwd 绑定；三题均在同一 attempt 恢复后取得可信 `completed`。发送边界、恢复和 UI 路由异常均保留原 journal；恢复没有新建 attempt，也没有重复发送。
- 三题正式 collect/finalizer/verify-only PASS，候选冻结稳定；Qwen `file-history-snapshot` 系统 metadata 行允许缺少行内 session/cwd，但用户、助手、附件内容行仍逐行绑定，segment 目录和显式 workspace 证据一致。
- 评分使用 `gpt-6-astra/high`。三题均 `score_status=valid`：support handoff `1.0000`，temperature CLI `1.0000`，colleague leave `0.8875`，平均 `0.9625`（百分制 96.25）。其中 colleague 评分线程遇到一次 Codex capacity error，控制器保留原 thread 后继续完成，没有新建替代会话。
- 资源观测：模型请求 18、工具调用 18；原生任务耗时合计 132.684 秒，流程耗时合计 296.934 秒；输入/输出/总 Token、Cache Read、Cache Write、HTTP 尝试数全部保持 `null/unavailable`，没有从日志默认推断或补零。
- 回传包：package ID `bf6d7e3f9cd4561a2ccd967e128d972e7056c7ed55a0825f6505c3e5f473b77b`，archive SHA-256 `e2fb950af259783ac06f7164b4d5cac693e658db3f0098847ad15159eae96972`；包内不含评分 runtime。
- 报告：输入验证 PASS；领导版 Markdown、审计 Markdown、同源 JSON、10 Sheet Excel 和 PNG/公式预览均 PASS。批次状态 `prepare/import-return/report=COMPLETED`。

正式原件根：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260922-small3-r6`。报告目录：`prepared/qwenwork-macos-general-20260922-small3-r6/reports/qwenwork-small3-r6/`。release source revision 为 `1f018446a5a0be60487c40405ce6f9863b2d2319`，suite SHA-256 `d8bcafd934c39ab13223d79bb1bd45d28333faeae13ee5a1df47e06bdf9516b2`；release root 和 suite verify 均通过。

## 当前边界和下一步

这轮证明 QwenWork macOS General 已具备三题单槽的执行、恢复、原生采集、候选冻结、评分、回传和报告闭环。它没有证明默认三路后台并发、动态补位、客户端重启、发送临界中断、未知授权/追问安全暂停、真实残留进程保护、Apple Silicon、Windows 或全量 60 题。

代码接续已补齐 QwenWork 专属批量入口 `drivers/qwenwork/batch.mjs`（execute-general-e2e `0.10.12`）：冻结 manifest/attempt/config，默认 `run_slots=3`，按可信终态动态补位，恢复只复用原 attempt，并对队列外 active session fail-closed。Qwen focused Driver/Probe/Collector/Adapter 加队列与 active-session 反例共 52 项 Node 测试、General scoring orchestration 19 项 Python 测试、脱仓 execute 构建 19 项 Python 测试通过；这些是离线实现证据，未提升真实并发准入。

五题 smoke 的本地运行根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260922-five3-r7` 目前只有前两题正式完成；第三题曾在发送后即时查询竞态中进入 `NEEDS_ATTENTION`，随后数据库读到唯一已完成 session，应使用原 attempt 的 fresh-probe resume 继续收口，禁止新发；第四、第五题尚未开始。当前现场只读复核（`probe-current-followup-20260922.json`）显示 QwenWorkCN `1.2.0`、SDK `1.0.46`、x86_64、active/pending `0`，但 CDP `9250` 不可用且 runtime profile 未匹配，因此本轮没有继续 UI 操作或 Prompt 发送。

后续 r13 运行根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260922-five3-queue-r13` 已完成五题执行队列：5/5 `COMPLETED`，五个唯一 attempt，`dispatch_attempt_count=1`，第三题及其余延迟 session 均通过同 attempt resume 收口。receipt：`observed_max_concurrency=1`、`dynamic_refill_count=0`、`native_interval_coverage=0/5`、`concurrency_evidence.status=INSUFFICIENT_EVIDENCE`；该批次未进行正式 collect、评分、回传或报告。

下一步仍是 fresh probe + 第三题同 attempt resume；在当前客户端重新提供可归属的 CDP 独占时段后，先完成五题默认三路/动态补位和正式 collect，再补发送临界中断、客户端重启、未知授权/追问安全暂停及进程清理故障矩阵。Codex 重启仍按用户要求暂缓。Token/cache profile 继续保持 unavailable，直到当前 QwenWork runtime 的原生语义得到独立验证。
