# QwenWork macOS General 集成 canary

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

日期：2026-09-22（Asia/Shanghai）。本证据覆盖 QwenWorkCN 1.0.6 / macOS x86_64 的单题 live integration canary，不是 5 题或 60 题正式评测。

## 已完成

- 只读 probe：安装身份、CDP `9250`、`agents.db` WAL/SHM 快照可读；21 个历史会话初始均有稳定 session/conversation/sub_chat/project/cwd 绑定，token profile 保持 `unverified-null`。
- 离线回归：Qwen Driver 20/20、Probe/Collector/metadata 相关 Node 38/38；锁定 `playwright-core@1.55.0`。
- 代码修复：活动 WAL/SHM 快照复制、原生 Open Panel 选择器、contenteditable 段落读回、发送按钮语义选择、attempt 项目唯一命名、Qwen 真实 metadata 行分类、Qwen 终态页面标题绑定、Qwen CB-B finalizer 和精确平台写入。
- 干净 live 单题：批次 `qwenwork-macos-general-20260922-v6`，`03_Social_Interaction_task_003_colleague_leave_reply` 只发送一次；原生 session `0d900061-e0bf-46de-9987-92cb3f17d2d1`，conversation `muc02cib2bp97ssk`，sub-chat `muc02cibep88q082`，local project `muc028p7blhhu576`；同 attempt 恢复 1 次后终态 `completed`，`target_session_verified=true`、`stop_confirmed=true`、`binding_consistent=true`。
- 资源观测：请求数 1、工具调用 0、流程耗时 111.967s、原生 turn 耗时 8.097s；Token/cache 因 1.0.6 语义未验证保持 unavailable。资源覆盖缺失形成合法 `partial` collect receipt，不阻断内容评分或报告，未知值未补零。
- CB-B collector 能处理真实 transcript 的系统注入行：`runtime-config`、`workspace-directories`、`active-leaf`、`last-prompt` 记录 metadata coverage，不把缺失 cwd 伪造成内容证据；正式 trace completeness 可达到 complete。
- 公共 finalizer 验证通过：候选冻结稳定，正式 execution record 的 session/cwd/Prompt/attempt 绑定一致，真实 workspace cleanup 成功；评分前置检查、语义证据分页、合分和 `verify-score` 全部通过。Judge 使用 `gpt-6-astra/high`，总分 `0.7875`，四项 criterion 为 `0.75 / 1.0 / 0.5 / 1.0`。
- 正式 return/import/report 已闭环：选定 package ID `69fd11e1e0d38e974607b8fcc63861254d783ebf604e47416be728b27c3bc7b0`，回传包不含评分 runtime；报告输入验证、JSON、领导版 Markdown、审计 Markdown、10 Sheet Excel 与预览校验均通过，批次状态 `prepare/import-return/report=COMPLETED`。
- 提交后独立发行验收：实现 revision `56584119fb9e2b316359f0ecf7b7008a453bfd04`，release `qwenwork-macos-general-5658411`，suite SHA-256 `ad21c166cbcacfa0fed452ab3a92c1dfb3f6bdcbef9c39d0cfe973809f03d6b9`；7 个 Skill、release root 和 suite 均验证通过。独立安装的 run/report 0.5.1 从同一冻结输入重建出相同 package ID 和 archive SHA `532150fdaba964ef24532f3718da7d03ca7a02341e38ec75b5b0f168bf85c82b`，并再次生成 10 Sheet 报告 PASS。

## 当前边界

正式原件根：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260922-v6`。execution unit、orchestration、return 包和批次报告均保留在该根下；登记到批次状态的报告为 `prepared-score-v7/qwenwork-macos-general-20260922-v6/reports/qwenwork-v6c-gpt6-astra-high/`，独立发行复验报告为相邻的 `qwenwork-v6d-packaged-5658411/`。旧 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260921-v5` 仍只作为排错证据，不进入正式回传。

单题值守闭环已完成；下一步按固定 smoke 先扩到覆盖文件/纯回复与三种评分类型的小批，再验证五题默认三路执行、动态补位和恢复不重发。QwenWork 后台并发、未知授权/追问、客户端重启、发送临界中断与无关进程保护仍须按加固矩阵补真机证据，不能由本单题正常路径推导通过。

QwenWork 当前 runtime 的 Token/cache profile 仍为 `null/unavailable`，不阻断内容评分；不把历史日志推断为 Token。Windows、Apple Silicon、三路并发和 60 题全量不在本 canary 范围。
