# Loomy macOS General E2E 适配

在 Apple Silicon Mac 上验证 Loomy 0.9.39（`com.loomy.desktop`），原生模型身份为
`imodel/spark-x2.6`、推理强度 `high`。实现包含标准执行、批次队列、原生证据采集、
候选冻结、正式回执与离线复验。沿用框架既有准备、评分及回传协议。

## 正式包与自动化接口

本机正式包的 `electron/main.js` 使用 `app.isPackaged` 决定开发状态，并调用
`sanitizePackagedRemoteDebuggingSwitches`。`electron/utils/remote-debugging.js`
会移除 `--remote-debugging-port`，同时忽略正式包的 `LOOMY_REMOTE_DEBUGGING_PORT`。
因此改变启动参数不能开启该版本的 Electron CDP；开发构建或官方开放调试的包才适合
采用 CDP。适配通过 macOS AX 操作安装的正式客户端，无需修改或重新打包应用。

执行前冻结应用、精确 GUI 进程、辅助功能 helper、原生后端二进制及只读数据库来源。
目录按完整路径选择并再次核验，保持客户端已有的目录权限策略；发送前核对完整
Prompt、模型及 High。发送意图和次数先落盘，每个 attempt 最多调用一次发送；
已发送或状态不确定时仅观察原请求。受控的零发送准备恢复及源码修复保留原状态、
journal 与旧源码身份，不能授权重发已 armed 请求。

采集通过只读 SQLite 在线备份保留绑定 session 及递归子会话、原始 message/part、
最终回复和工具记录。Loomy 记忆前缀独立保留，冻结原题必须逐字且唯一匹配。
同一主应用的后端替换保留独立谱系，终态快照界定正式执行范围，后续客户端维护会话
独立归档。全单元执行及全部原生采集完成后，才统一清理和 finalize，以免提前清理
以某题 Workspace 为 cwd 的共享后端。

入口与命令见：

- [Loomy 执行说明](../../tools/report/skills/general-e2e/execute-general-e2e/drivers/loomy/README.md)
- [Loomy 采集说明](../../tools/report/skills/general-e2e/collect-general-e2e/drivers/loomy/README.md)

组件 `loomy=0.1.8`，执行 Skill `0.15.8`，采集 Skill `0.12.9`。采集 `0.12.9`
修复离线校验读取 execution-record 顶层 `resource_metrics_path` 的路径，旧冻结证据保持原样。

## 六类真实验证

从旧 `general-custom60-v1` 每类选择一题，使用同一冻结批次
`loomy-macos-general-validation-r3`，未修改题目、GT、权重及原准备包。
六题均完成真实客户端执行、正式采集和离线 verify-only；每题发送次数为 1，原生记录
均为 `spark-x2.6/high`。未运行语义评分或赋予任务分数。

| 类别 | 任务 | 原生工具调用数 |
| --- | --- | ---: |
| 效率流程 | expense_policy_check | 8 |
| 代码智能 | temperature_cli_fix | 6 |
| 社交互动 | colleague_leave_reply | 0 |
| 检索 | local_release_note_lookup | 5 |
| 创意综合 | release_note_rewrite | 0 |
| 安全对齐 | untrusted_document_injection | 3 |

队列支持 1–3 个槽位，UI 派发串行；本次原生用户创建至主助手完成区间的峰值重叠为 2，
据此只确认两题真实重叠。开发过程中包含准备失败、源码修复和人工等待，整批墙钟耗时
不用于推断客户端性能。旧失败与修复清单完整保留，未重发已提交请求。

六题轨迹均为 `complete`。Token、缓存、推理 Token 及模型请求计数的原生字段语义
尚未准入，标准值保留 `null/unavailable`；因此采集回执为 `partial`，唯一缺项是
`resource_metrics_complete_coverage`。该缺项由框架现有标准评分准入规则接受，
不能解释为能力零分或完整资源覆盖。工具数以原生 call ID 核对，原生耗时标记为推导值。

本地验证原件保留在 worktree 的 `.agents/loomy-validation/`（不进入 Git）：

- `r3/round/Loomy/`：原 execution unit、六题正式证据、源码修复清单及采集回执。
- `r3-final/validation-report.json`：任务、attempt/session、模型、发送次数、资源及候选摘要。
- `r3-final/verify-v0129-{1..6}.log`：六题在采集 `0.12.9` 下的离线复验结果。
- `final-checks/`：Node 与 Python 回归日志。

Node 32 项与 Python 65 项回归全部通过，覆盖原生身份及归一化、只读数据库、一次发送、队列恢复、通用 finalizer、应用发现、
Skill 布局、发行构建、准备及 round workspace。旧发行包、历史评测结果及主工作区原有
未提交文件保持原样。
