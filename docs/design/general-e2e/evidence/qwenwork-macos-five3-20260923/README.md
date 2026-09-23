# QwenWork macOS General 固定五题证据

日期：2026-09-23（Asia/Shanghai）。目标客户端为 QwenWorkCN 1.2.0 / macOS x86_64。固定五题为 `retro_agenda`、`support_handoff`、`temperature_cli_fix`、`colleague_leave_reply`、`suspicious_installer`。r21 已在同一五题批次实证原生三路执行、三路语义评分和正式报告；r23 已完成带进程级 Token 开关的新五题批次，四个核心 Token 字段覆盖 5/5。两批均需区分队列占槽与原生主 turn，**适用故障矩阵尚未全部通过，不能声明受控生产可用**。

## r21：固定五题原生三路与 sol/high 正式闭环

- 发行源码 `475405305cf92dffa62a36b3cd4851431378ad4c`，suite SHA-256 `fc0c4d5dabb962c1ba271c2204a3308e8100d64be8274b4e3f67553e1dd00b72`；批次根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r21`。发行、prepare/verify 均 PASS。五题各发送一次，同 attempt 恢复后 5/5 原生完成；发送占槽峰值 3、动态补位 2。
- 只读 [主 turn 重叠审计](audit_native_overlap.py) 校验 5/5 原始 segment SHA、唯一非 subagent turn、session 与 attempt；结果为 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r21/native-overlap-audit.json`。前三题的原生时间分别为 `13:10:11.466–13:16:18.578`、`13:10:26.158–13:12:40.694`、`13:10:48.907–13:11:17.635`（UTC+08:00），因此 **13:10:48.907–13:11:17.635 真正三路重叠**。队列原始 receipt 的 native timing coverage 仍为 `0/5`；三路结论来自哈希绑定的补充审计，不反写冻结 receipt。
- 五题 collector、finalizer 和逐题 `--verify-only` PASS；`gpt-6-sol/high` 三个独立语义评分原 thread 与两个 automated 评分 5/5 valid，均分 `0.8575`。return package ID `b163f7e85753cd4ae4ee672c31112e6cfe82a680e7095f716662bb2d47c11f73`，archive SHA-256 `8b7c0574f6857ff1e67a627ad1e9361b071ce39818f90f6eed5f6175cbc036b9`；导入、报告输入验证和 10 Sheet Excel PASS。报告在批次准备根的 `reports/qwenwork-r21-gpt6-sol-high/`。此批客户端未带 Token 暴露开关，usage 保持 null。

## r22/r23：QwenWorkCN 1.2.0 Token Profile 与五题指标闭环

- Web 端已有进程级开关 `QODERCN_EXPOSE_TOKEN_USAGE=1`。r20/r21 原始响应字段全为隐藏零值；当时的 9250 监听进程环境确实没有此开关，旧批次不得回填。General 新增精确监听 PID/进程启动身份的安全启动、开关探针和队列门禁。首次停止旧进程时遇到退出与 `ps` 读取竞态，启动器按门禁留 `NEEDS_ATTENTION`；确认旧监听已消失、数据库空闲后，使用 Web 端同一 `/usr/bin/open --env` 启动方式拉起 PID `61550`，探针证实 QwenWorkCN 1.2.0、SDK `1.0.46`、runtime SHA-256 `8dc1dc0b107f37837cf76ef7e2be4f0dd2fdbd90ff8391a3f1f9e965e9f3fb02` 未变化，开关为 enabled。退出时序竞态随后在 `555e1ac` 修复，idempotent 启动检查 PASS；证据根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-token-20260923-8188c98`。
- r22 对固定五题中的 `support_handoff` 建新单题批次，11 个主 turn 请求/响应 ID 一一匹配，非零输入 `474537`、输出 `9589`、Cache Read `425379` 分别与唯一 `turn.finished` 终值相等；transcript 为 `1.1.59`。General collector 将发送前 probe/config SHA 归档，精确命中版本/SDK/runtime Profile 后四个核心 Token 均为 observed，正式 finalizer 和 verify-only PASS。输入已包含 Cache Read，总 Token `484126`，不能重复加缓存读取；Cache Write 原生零值仍是适配器默认，保持 null。r22 根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-token-smoke-20260923-r22`。
- r23 从 `508d23c852b2afc65758c164b58f3bc43a05630d` 构建七 Skill 发行，suite SHA-256 `0d46593066f36e378f2f69258586ff46a52db77e2c156af8542b16518daec0cc`；批次根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-five3-token-r23`。五题各发送一次、同 attempt 恢复后 5/5 原生完成；collector 对每题的请求/响应和主 turn 完整对账，finalizer 与逐题 verify-only PASS。五题核心资源均为 **5/5 observed**：输入 `1589384`、输出 `22538`、总 Token `1611922`、Cache Read `1408504`；请求 `35`、工具调用 `34`。Cache Write、推理 Token 和 HTTP 尝试仍为 `null/unavailable`，collect receipt 因这些字段保持合法 partial。
- r23 的 `gpt-6-sol/high` 三个语义原 thread 与两道 automated 题 5/5 valid、均分 `0.86`，return package ID `0c4eea81b7be42658c05dde227e86965e1994208f4b2cfd36b410df0e79ca61f`，archive SHA-256 `3d79c039aca4df45a9d9f7ec1ee30708fbef634d00094e11541d009e12e425d4`。导入、report validate-inputs、同源 JSON/领导版 Markdown/审计 Markdown、10 Sheet Excel/预览与 batch receipt PASS。报告在准备根的 `reports/qwenwork-r23-gpt6-sol-high/`，总 Token `1611922` 与五题采集同源；r23 主 turn 峰值为 2，不取代 r21 的三路实证。

## r20：未观察到三路的历史对照

- 源码修复提交 `cd678863219ee702c7f41df6d36b1d1ab2874aa0`；独立发行 `report-workspace/general-e2e/releases/qwenwork-macos-general-five3-cd67886`，suite SHA-256 `1287e371cb35a286ea31dbb0939ffd4c40b2bff565d992b95b428b096348a1f2`。release-root、suite、五题 prepare/verify 均 PASS；execute Skill `0.10.14`。调试执行根为 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r20`，批次 ID `qwenwork-macos-general-20260923-five3-r20`，包内 Harness 版本字段与实际 probe 均为 `1.2.0`。
- 队列以 `--run-slots 3 --preprepare-projects --skip-clarifications` 运行：先逐题预建独立项目与草稿，再按 manifest 顺序单槽发送。五题各发送一次、attempt 各唯一、5/5 原生完成；第二、第五题因瞬时终态证据冲突进入 `NEEDS_ATTENTION`，fresh probe 后沿原 attempt 恢复，均未重发。队列发送占槽峰值 `3`、补位事件 `2`。本批次未出现可供自动点击的追问卡片，故 `--skip-clarifications` 的真机自动分支仍待验证；r19 中用户指定的“会议日期”卡片由控制端确认唯一按钮后手工点击了“跳过”。
- 只读脚本 [audit_native_overlap.py](audit_native_overlap.py) 逐题校验 trace-index、原始 segment SHA、唯一非 subagent 主 `turn.started/turn.finished` 和 session/attempt 身份，结果在 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r20/native-overlap-audit-verified.json`。原生时间覆盖 `5/5`，**峰值 `2`**。前三题依次为 `12:09:00.870–12:09:28.859`、`12:09:30.285–12:10:36.946`、`12:10:08.003–12:10:42.998`（UTC+08:00）；第一题结束后 1.426 秒第二题才开始。其余两题分别为 `12:13:53.804–12:14:04.208` 与 `12:14:26.360–12:15:08.591`。队列原始 receipt 的 `native_interval_coverage=0/5`，其 `observed_max_concurrency=3` 仅代表发送至终态的占槽；补充审计不能反写或替换冻结 receipt。
- 五题 Qwen collector、cleanup/finalizer 和逐题 `--verify-only` PASS；正式 `collect-evidence-receipt.json` 为合法 `partial`，缺失的是未验证的 Token/cache 等覆盖。正式指标中原生任务耗时采用 SDK `turn.finished.duration_ms`，五题合计 `180.759` 秒；流程耗时 `617.23` 秒单列，不包含预建项目的前置耗时。已落盘模型请求 `23`、工具调用 `21`；Token/cache、HTTP 尝试仍为 `null/unavailable`。QwenWork 当前 UI 只回读到“标准”档位，不能据此推定可审计模型 ID；五份 execution record 的 `actual_id=null/verification_status=unknown`，报告因此显示“未知模型@QwenWork”。
- 最初冻结的 `gpt-6-astra/high` 编排已锁定独立历史 submission。用户随后将裁判固定为 **`gpt-6-sol/high`**；在同一批次冻结候选上新建独立重评分编排，三个语义原 thread 均通过 `verify-score`，两道 automated 规则题有效。sol/high 的五题分数依次为 `0.6625 / 1.0 / 1.0 / 0.7625 / 1.0`，5/5 valid、均分 `0.885`、评测异常 `0`。sol/high return package ID `9553cc3e972a58072ba4a13b267530fd8daee8f3fb86e8d73b419c0d4a851d93`，archive SHA-256 `8a90457af94e836207fc8ddabe48ec8ac8b375636407464adbcd96edf946625a`。
- sol/high 准备根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r20/prepared-sol/qwenwork-macos-general-20260923-five3-r20` 与原准备根的 batch manifest、execution ZIP、scoring ZIP 哈希完全一致，只有裁判/报告配置不同；独立 prepare/verify、return import、report validate-inputs 和 batch receipt PASS。报告位于其 `reports/qwenwork-r20-gpt6-sol-high/`：同源 JSON、领导版 Markdown、审计 Markdown、10 Sheet Excel 与 10 张预览均已生成。
- 本次 sol/high 的冻结准备配置副本为 [prepare-config-gpt6-sol-high.json](prepare-config-gpt6-sol-high.json)。后续新批次须生成新的 `batch_id`，核对届时真实客户端版本；裁判字段继续固定为 `gpt-6-sol/high`，不得复用 r20 的 batch ID 冒充新执行。

复算命令：

```bash
.venv/bin/python docs/design/general-e2e/evidence/qwenwork-macos-five3-20260923/audit_native_overlap.py \
  --unit-root /Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r20/worker/qwenwork-macos-general-20260923-five3-r20__qwenwork-macos-x86-64 \
  --queue-id qwenwork-five3-r20 \
  --output /Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r20/native-overlap-audit-recheck.json
```

## 决策依据与未完成门禁

- r13：旧包五题各发送一次，5/5 执行、采集、评分、回传和 10 Sheet 报告通过；均分 `0.8975`，三个语义评分 thread 的记录区间确实重叠。批次根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260922-five3-queue-r13`，包内旧 Harness 版本字段为 `1.0.6`。
- r18：旧包队列占槽峰值 `3`、补位 `2` 次，五个唯一主 turn 的原生重叠峰值却只有 `2`；批次根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-queue-r18`。r15/r16 的高频 WAL 快照冲突促成 SQLite 在线备份；r18 亦证明同 attempt 恢复不重发。
- r19：从 `58cabad` 发行的预建队列五题均预建成功，第一题发送一次并完成，第二题在已完成会话页面找不到项目控件，尚未发送即安全暂停。修复为预建项目发送前先恢复唯一“新任务”页，形成 `cd67886`。r19 根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r19` 保留原 journal；不能把 r19 算作五题闭环。
- r20 证明预建策略消除了 r19 的路由门禁并完成五题闭环，但当轮原生峰值仍为 2；r21 在相同五题与三槽配置下，第一题的原生时长足以覆盖后两题启动，峰值达到 3。这支持“短题时可能观察不到三路重叠”的解释，但不能把队列占槽替代原生证据，也不能把预建/队列时间计入任务耗时。`--preprepare-projects` 是已验的可选执行策略，不应只凭 r20/r21 推断它提升了客户端并发能力。
- 共享 macOS cleanup 原语的实进程试验保存在 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-cleanup-matrix-r20/result.json`：目标 Workspace cwd 的测试残留被选中并清理，目录外对照进程未被选中且仍存活。它验证了精确 cwd 清理与无关进程保护的共享机制，**不是** QwenWork 真实任务残留的通过证据。
- r24 单题故障 canary 使用 `c871236` 发行、固定五题中的 `support_handoff` 新 attempt，正式 collector/finalizer/verify-only PASS。收口前向候选 Workspace cwd 注入一个受控 `/bin/sleep` 残留 PID `96210`，另在目录外启动对照 PID `96211`。正式 QwenWork finalizer 的 `process-cleanup.json` 记录目标被选中并收到终止信号、收口成功，目录外 PID 未被选中且在收口后仍存活；证据 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-fault-r24/cleanup-fault-result.json`。这是**正式 QwenWork 候选收口路径上的真实 OS 进程注入试验**，不等于客户端自然遗留进程已复现。活动任务期间尝试调用 Token 启动器时，客户端任务恰好结束，返回 `ALREADY_EXPOSED/restarted=false`，不能记为真机“活动任务拒绝重启”通过。
- r25 单题硬中断 canary 从 `dc064ec` 独立发行：队列控制进程的 PID/启动身份与冻结摘要经核对，在 journal `send.state=attempted`、`dispatch_attempt_count=1` 且队列行仍为 `DISPATCHING` 时执行 SIGKILL；QwenWork 客户端未受信号。普通 resume 因陈旧 owner 锁拒绝，fresh 空闲 probe、无 attempt lock 后显式 `--resume --recover-stale-owner` 归档旧锁并沿原 queue/attempt 继续；发送次数仍为 1。原生只留下无 session ID/stream 的 `ready` conversation，未产生可信终态；旧 Driver 在临时绑定上持续等待，控制端仅停止核验过身份的队列进程并保留现场，**本次执行未闭环，不得评分或算能力失败**。证据 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-fault-r25/{queue-kill-evidence.json,queue-stop-evidence.json}`。后续 `e72a770` 增加仅在原生未活动且身份落库观察 60 秒后转 `NEEDS_ATTENTION` 的基础设施门禁，运行中的原生任务不受该窗口限制；此新代码已通过 fixture，尚未用另一轮同类真机故障重验。
- r25 对发送临界硬中断的“原 attempt/不重发/受控 owner 恢复”给出真机部分证据，也揭示未形成原生 session 时必须安全暂停；不能把该未闭环 canary 计为故障矩阵完整通过。截至 r25，QwenWork 活动任务期间客户端重启/重连及未知授权/追问自动处理仍未验收；后续 r27/r28 结果见下文。自然残留复现不另设为门禁；空闲时 Token 启动器与 r24 注入试验只覆盖各自声明的边界。Codex Desktop 重启按用户要求暂缓。可见 UI 的“标准”档位仍不能提供可信实际模型 ID；macOS x86_64 结果不外推 Apple Silicon、Windows 或 60 题全量。

## r26/r27：发送临界恢复与队列终态修复

- r26 仍使用 `e72a770` 原发行，suite SHA `15f05ee5d06b1f801073fce31fe7eab6617d82d5762848cf8d060d2db69162c1`。发送返回后、原生身份落 journal 前精确中断控制进程；单题 Driver 退出后留锁。`009c35b` 的独立恢复工具在 fresh 空闲 probe、原 config/attempt、精确 owner/进程启动身份校验后归档单题锁，回执证明 journal 字节未变。没有手删锁或改写 r26 安装包。
- r26 原版 batch 恢复暴露缺陷：子任务还是 `DISPATCHING`，队列却返回 `COMPLETED`；其 receipt 的 `integrity.valid=false`，**该队列回执不可用于通过声明**。原件保留。随后原版单题 Driver 以 `inspect-only` 绑定原 session `2858eab5-28fd-4a2b-acbd-aaa239c28e4a`，原 attempt、发送尝试数 1、原生 Prompt 匹配数 1；正式 collector/finalizer/verify-only PASS。根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-fault-r26/` 的 `recovery-audit.json` 关联故障、锁归档、无效队列回执和独立有效 collect 的哈希，不能混淆两者。
- `9f94ef7` 修复队列遗漏 `DISPATCHING`：恢复必须先交给原 attempt 观察，未确认时暂停补发；全部任务终态才发布完成回执，旧的队列/子任务终态冲突明确拒绝。r27 从此提交独立发行，suite SHA `0e3b716e355cfa67a896a2b14f03b738df3812b9aacf6bb732af9219e2189c6d`，release/prepare/verify/npm ci 均 PASS。
- r27 在 `send.state=attempted / dispatch_attempt_count=1` 窗口核对 PID 与启动身份后，SIGKILL 本次队列 PID `61654` 和 Driver PID `63491`，未向 QwenWork 客户端发信号。原生任务继续执行。任务仍 running 时 Token 启动器返回 `QWEN_TOKEN_LAUNCH_PREFLIGHT_NOT_IDLE_OR_VERIFIED`；随后 fresh 空闲 probe、受控单题锁归档与 `--resume --recover-stale-owner` 恢复成功。原 session `a13311f5-0a89-4b11-a016-699838f85caa`、原 attempt、发送尝试 1、Prompt 匹配 1，队列 `COMPLETED / integrity.valid=true`，正式 collector/finalizer/verify-only PASS。
- r27 根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-fault-r27/`；关键文件 `queue-kill-evidence.json`、`attempt-lock-recovery.json`、`token-launch-during-task.json`、`recovery-audit.json`。这是一题故障 canary，不替代 r21 五题三路或 r23 五题评分报告；没有为故障样本再生成能力分数。

## r28：真实问卷、断连与同 attempt 恢复

r28 是独立技术用例，Prompt 明确禁止文件/命令操作，仅要求 QwenWork 弹出“会议日期、参会人数”两题问卷；没有修改正式数据集、评分或报告分母。根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-interaction-r28/`。

1. `391b5a9` / execute `0.10.22` 增加已绑定及临时会话的待交互检查：未知授权/弹窗暂停，用户授权问卷才跳过；Driver 异常退出不再无限轮询旧 RUNNING journal。fixture 102/102，但首次真机暴露临时标题还未落库时的身份保留问题。
2. 客户端在问卷页头有 `aria-label=下一题` 导航箭头，页脚还有“下一题 ↵”按钮。旧全卡片匹配得到两个控件，按门禁暂停且没有盲点。`question-dom.json` 与 `question.png` 保存现场，`d43dadf` / execute `0.10.23` 改为唯一 `user-question-footer` 内的“跳过/下一题”，并在 UI 标题就绪前先持久化 conversation/sub-chat/cwd。
3. 在原 session `69eaa730-25f5-440a-b7cf-75d13e64f07d` 上关闭**控制 Driver 的 CDP 连接**，不退出 QwenWork；真实观察报 `Target page, context or browser has been closed`，持久化 `NEEDS_ATTENTION`。`disconnect-evidence.json` 记录原身份、客户端 PID 和未重启边界。这不等于客户端重启或进程崩溃验证。
4. 新独立恢复工具包保持原 config/Prompt/attempt，重连原 session 后在 `08:56:51.674Z` 自动点唯一页脚“跳过”，写入 `USER_AUTHORIZED_CLARIFICATION_SKIPPED`；再次观察得到 `COMPLETED`、attention=null，原生回复为“已跳过问卷，验收结束”。发送尝试 1、Prompt 匹配 1。`interaction-audit.json` 记录新旧源码 revision 与哈希；旧安装包未热改。本项是跨工具版本的受控恢复证据，不冒充全程同 revision 的新批次。

最终执行源码 `d43dadf55831098043987ebb99438eb710a79b1e`；发行 `report-workspace/general-e2e/releases/qwenwork-question-d43dadf`，suite SHA `5338497dbd72cb7161f08d2b1a064422ffb9e53d65ff1a9311b3b12a49a2ac03`。Qwen 聚焦 Node 102/102、发行/布局 Python 16/16 PASS。r28 新建时的发送仅发生于 `391b5a9`；`d43dadf` 的临时标题分支目前为自动化验证，页脚跳过和原会话终态已有上述真机证据。

## r29：最新版新 attempt 的身份与断连复验

r29 从 `d43dadf` / execute `0.10.23` 独立安装开始，使用与 r28 相同的两题问卷技术 Prompt、新项目和新 attempt。首次发送返回 `RUNNING / SESSION_ID_PENDING` 时已保留 conversation `mudvk1tv07xqv3pd`；随后自动识别完整 session `5e582208-c0df-45de-8143-820a67c14705`，证明临时标题修复在新 attempt 生效。关闭控制 CDP 连接后安全暂停；同 attempt 重连后于 `09:03:41.293Z` 自动跳过，`09:04:06.364Z` 观察到 COMPLETED，发送/Prompt 匹配均 1，原生回复“已跳过问卷，验收结束”。根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-interaction-r29/interaction-audit.json` 保留初始临时身份、断连和终态哈希。

r29 也发现跳过后的即时观察仍使用旧 SQLite 行，导致一次瞬时 NEEDS_ATTENTION。`f07d0b3` / execute `0.10.24` 修复为：跳过成功后清除旧 attention，保持 RUNNING，下一轮重新查原生状态，不要求人工恢复这一正常过渡。聚焦 Qwen Node 102/102、发行/布局 Python 16/16 PASS；另补两个陈旧队列 owner 回收者竞争专项 PASS。共享 finalizer 用仓库 Python 复验 15/15；公共收集/编排/评分/回传/报告 Python 57 项中 56 项首次通过，1 项因 ENOSPC 失败后单独重验通过，不能把首次运行记成 57/57 全通过。

## r30：自动跳过后持续观察至完成

r30 从 `f07d0b39225c4ffdfe6885077fd0a1e07df0cbf8` / execute `0.10.24` 独立发行和新项目开始。suite SHA `80c06c7a2b3de8c0017ae1dc9fad0bf152b7dc4d75e990f432cbe03381c8d051`，release-root/suite、锁定依赖安装通过。同一技术问卷由自动控制循环首次发送后按 Driver 的 RUNNING 状态续观；四次返回依次为 `RUNNING → RUNNING → RUNNING → COMPLETED`，全程没有 NEEDS_ATTENTION，人工 resume 次数为 0。`09:07:19.567Z` 自动跳过一次，原生 session `c1ab5f38-6307-4d94-92ed-1574cc367607` 最终回复“已跳过问卷，验收结束”；发送尝试与 Prompt 匹配数均为 1。

证据根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-interaction-r30/`，`automatic-observer-result.json` 保存完整状态序列，`interaction-audit.json` 绑定 config/journal/transcript SHA。本用例是未评分的独立技术验收，不混入正式五题的成功率、Token 或报告分母。它验证当前跳过链路无需人工恢复，不代表所有故障均可无人值守恢复。

## r31–r33：路径、未知授权与真实收口故障

实现提交 `87d39cb95fab03d6d99c2732f106ecca3a8622e9` / execute `0.10.25`；发行 `qwenwork-hardening-87d39cb`，suite SHA `fbbe24c6e4a4f4909e793585867ecc7feaa2990ef7c0bde1502595023eaf0b54`。release-root/suite、prepare/verify 与锁定依赖安装通过。源码不依赖 Web Driver；裁判配置仍为 `gpt-6-sol/high`，本轮技术故障用例不评分。

### CV17：实际编码与发送前拒绝

- 从已安装 SDK 静态确认 ASCII 映射、200 字符前缀和 DJB2 XOR/base36 后缀算法，绑定 runtime SHA；按能力识别，不以客户端版本白名单放行。发送前读取 Workspace/trace 根的 `NAME_MAX=255`、`PATH_MAX=1024`，后者包含末尾 NUL；检查原始控制路径、编码后 project 目录和 native transcript/segment 路径预算。未知编码、越界、链接、不可写或越限在 CDP/UI 操作前拒绝。
- r31 在真实“技术 用例”目录执行完成，原 attempt/session、Prompt 匹配与发送均为 1；原生 transcript 目录与预检复算完全一致，证据 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-important-hardening-r31/native-path-audit.json`。
- 同机预检覆盖数据集最长 ID `04_Search_Retrieval_task_008_procurement_clause_version_lookup`（62 字符）与中文/空格。组件 258/255 字节、原始路径 1306+1/1024 字节、原生日志路径越限、Workspace 越界、Workspace 符号链接五个负例全部拒绝；每个负例无 journal、无匹配的原生项目、发送 0。`path-cases-result.json` 保存实际边界和错误。Node 边界测试另覆盖 NAME_MAX/PATH_MAX 恰好有效及首个越限值、emoji 的 UTF-16 编码、同前缀不同路径哈希、编码实现变化和原生目录链接。
- r31 首次新建项目遇到前台焦点丢失，在发送前暂停（次数 0）；沿原 attempt 恢复后才发送 1 次。此安全暂停保留，未绕过原生键盘焦点门禁。

### CV08：未知授权不批准，人工拒绝后原会话完成

r31 的原“完全访问”配置下，删除本次创建的空目录直接执行，不能作为未知授权弹窗证据。r32 单独技术样本暂时改为“默认权限”，发送同类请求，实际出现“高危操作 / Shell 想要执行一个命令 / 拒绝 / 允许”卡片。Driver 返回 `NEEDS_ATTENTION / QWENWORK_PENDING_INTERACTION`，未点允许，目标空目录保持存在，发送仍为 1。控制端保存截图和原生卡片 ID 后，只拒绝这次本方技术请求；原 session `a3fc218a-0fe7-4dc6-89e5-a201dc6ca4ef` 完成并回复“权限未获批准，验收结束”。待全部原生任务空闲后，已恢复原“完全访问”设置。

证据根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-important-hardening-r32/`：`approval-audit.json`、`unknown-approval.json/png`、`manual-rejection.json`、`permission-setup.json`、`permission-restored.json`。这是未知授权自动暂停 + 明示人工拒绝的受控分支；不是自动批准能力，不把它计入正式题目成绩。

### CV09/CV13：原 CLI、真实 OS 对象、原候选哈希

r33 从同发行新建固定题 `support_handoff`，执行根含“运行 空间”；发送 1 次、Prompt 匹配 1、原 session `1da7bdce-9049-441b-9cd6-cf997e0b5845` 完成并由正式 collector 首次采集。运行中曾因 native stream 与 UI 观察时差暂停，fresh probe 后恢复同一 attempt，未重发。后续故障均调用**未修改的正式 QwenWork finalizer CLI**，没有 signal、clock 或 cleanup hook 替换。

| 注入 | 结果 | 不变量 |
| --- | --- | --- |
| 本方父进程持续重建 Workspace cwd 子进程，使零残留静默窗口无法成立 | `TASK_PROCESS_CLEANUP_FAILED`，拒绝冻结 | 未发布 candidate/receipt；原 Workspace 字节不变；目录外对照存活 |
| 本方目录外写入进程持续更新候选中的独立测试标记 | `WORKSPACE_NOT_STABLE`，拒绝冻结 | 未发布 candidate/receipt；停止写入并仅移除本次标记后恢复原源目录哈希 |
| Workspace cwd 进程忽略 TERM；被 KILL 后再启动一个迟到子进程 | 初始 PID `50594` 记录 TERM→KILL，迟到 PID `51195` 被发现并清理，`late_process_detected=true` | 正式 cleanup success、零残留与静默窗口通过；目录外 PID `46740` 未选中且在收口后仍存活 |
| 成功冻结后，仅向源 Workspace 新增本方标记 | verify-only 拒绝 `verify:source-workspace` 漂移 | 冻结证据未改；移除本方标记后原 candidate/evidence/record/receipt 四个 SHA 全部重新验证通过 |

证据根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-important-hardening-r33/`。`cleanup-fault-results.json` 保存前三项及所有本方进程生命周期；`postfreeze-drift-audit.json` 保存第四项。首轮控制脚本只匹配英文错误码，而正式校验器正确返回中文“候选产物发生漂移”，因此脚本最后一条断言失败；原日志和前三项结果保留，随后按实际错误与原哈希独立复查通过，没有改写冻结证据。全部本方测试进程已退出。

最终正式 candidate SHA `49a4c82a1ddad6194b2874f13f83687c4e83ad24fcaf1ac1a6e10dcf2ea6d476`，evidence manifest SHA `95db36c0866bc05c6ab9606415b44c2dfbd35e810125bd9af603ddc7d79afe21`，execution record SHA `64f735de87130d765709d6394e7799a1b58a8c42f7c82cc07f42775d01cf26fd`，receipt SHA `d964ac6375ba276b6a217af5bce1429ce9a8779c40a0a5149150df50b9b9a9ea`。最后 `verify-after-owned-marker-removal.log` 为 PASS。这些故障发生在执行终态之后，不修改原生任务耗时或评测分母。

## r34/r35：终态快照与自动标题同步

r33 捕获到真实时差：SQLite snapshot 仍为 running/有 stream，但随后 UI 已无停止控件。`abb1646` / execute `0.10.26` 在原生身份已验证的前提下只复查一次同会话，重读 Prompt 与待交互状态；持续冲突仍暂停，不重发。r34 使用独立技术脚本（只等待 20 秒并输出 SYNC_END），延迟一次真实 UI 观察直到原生任务结束，实测触发 `STREAM_OBSERVATION_RECHECK`。期间又遇到客户端自动生成新标题，旧标题核对安全暂停；原 attempt 恢复后完成，现场 `title-mismatch-audit.json` 保留此边界。

`190406ce8dc61eb0b8ef6b0ed0c6a521d3da7888` / execute `0.10.27` 改为用同一 conversation/sub-chat/session/project/cwd 的最新数据库标题核对 UI，允许 2 秒 UI 标题一致性窗口；重复同名、原生身份或 cwd 漂移仍失败关闭。四个 stream 复查反例覆盖完成、持续冲突、不同 session、新授权；标题测试覆盖自动改名、各原生身份漂移、重复同名和渲染滞后。

r35 从该 revision 独立发行，新项目/新 attempt 重复同一技术场景。原生 session `d577e187-c347-4ec9-98ae-991bc23694eb`，自动观察 `RUNNING → RUNNING → COMPLETED`，发送/Prompt 匹配均 1，终态复查事件 1，原生工具结果包含 SYNC_END，最后回复“终态同步完成”。没有 NEEDS_ATTENTION 或人工恢复。故障只延迟控制侧一次 UI 读取，没有伪造 UI/数据库结果，也没有设置题目执行 deadline。

r34/r35 根分别为 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-important-hardening-r34/` 与 `qwenwork-important-hardening-r35/`；各自 `terminal-recheck-audit.json` 绑定原 attempt/session、native transcript、journal、binding SHA，r34 的暂停和 r35 的自动完成分开保留。技术脚本不评分，不并入正式五题结果。

当前发行 `report-workspace/general-e2e/releases/qwenwork-hardening-190406c`，suite SHA `5ddbc2c1905e5d181cd0ec7a590080a7a3df8bc95596b05769b253d830f0875c`，release-root/suite 独立验包通过。Qwen 聚焦 Node **115/115**、发行/布局 Python **16/16**，布局和 diff 检查 PASS。collect/orchestrate/score/report 未改版本；旧 r21/r23 报告及旧冻结证据未覆盖。

## 声明范围与 CV/GV 符合性记录

本轮目标为 **macOS x86_64 / QwenWorkCN 1.2.0 / 值守控制 / UI 单槽 / 默认三路 / Codex gpt-6-sol high**。不声明 Apple Silicon、Windows、60 题全量、自动批准未知授权、活动客户端自动重启或无人值守自动抢锁。下表 `PARTIAL` 包括尚缺分支证据，不能当作不适用。实际模型 ID、Cache Write、reasoning Token、HTTP attempts 继续为 unknown/null，不以这些可选字段阻断有效评分。

| 验收项 | 实现/自动化证据 | QwenWork 真机证据 | 当前结论与剩余项 |
| --- | --- | --- | --- |
| CV01 包与隔离 | prepare/release/layout 正反例；独立七 Skill 闭包 | r21/r23/r27 仓库外 prepare/verify、execution/scoring 分离 | PASS，后续发行仍逐包验 SHA |
| CV02 只读探针 | loopback、身份、快照、Token 开关门禁 | r27 当前 PID/端点、空闲与活动两种 probe，活动启动拒绝 | PARTIAL；端口占用/陈旧端点/多安装/锁屏负例仍需逐项登记 |
| CV03 UI/配置/Prompt | 唯一语义控件、项目/Workspace、配置漂移与发送禁用反例 | r19 未发送即暂停；r21/r23 一次发送；r28 同名导航/页脚定位反例 | PARTIAL；同名不同 Workspace、模型/权限不符的目标客户端负例未齐 |
| CV04 发送中断 | intent/reservation/invoking、不确定不重发，缺失/歧义 session 反例 | r25 部分现场；r26 发现队列缺陷；r27 修复后恢复并正式收口 | PASS（值守基础范围）；r25 不当作有效执行 |
| CV05 owner/竞争 | 活锁拒绝、两个 Driver/恢复者竞争、旧归档保护、字节漂移拒绝 | r27 两把锁精确归档，原 queue/attempt 恢复 | PASS（显式值守恢复）；不承诺无人值守抢锁 |
| CV06 断连/重启 | Driver 非正常退出保留基础设施错误、显式 resume | r28/r29 CDP 断开→暂停→重连原 session；r27 活动任务拒绝 Token 重启 | PASS（断连安全暂停范围）；客户端实际重启与 Codex 重启未验/未声明 |
| CV07 原生终态 | 完成/失败/取消/未知分开；不按文件稳定判断完成 | 文件任务 r21/r23；纯回复题正式 collect/report；r28 问卷完成 | PARTIAL；r32 已验工具权限拒绝后完成，r35 已验终态时差；最终错误等剩余真机分支继续对账 |
| CV08 待交互 | 精确会话/问卷页脚；unknown/approval/manual pause 反例 | r30 自动跳过至完成；r32 原生高危卡片自动暂停，人工拒绝后原 session 完成，设置已恢复 | PASS（声明范围）；不提供自动批准白名单 |
| CV09 清理/冻结 | 通用 finalizer、静默窗口、残留/漂移拒绝 | r24 优雅终止与目录外对照；r33 原 CLI 验证持续残留拒绝、迟到写入拒绝、TERM→KILL、迟到子进程和冻结后漂移 | PASS（当前 macOS 收口分支）；本方对照受保护，测试进程已退出。自然残留复现不另设门禁 |
| CV10 串行/并发 | 单 UI 槽、三后台槽、补位、同 attempt 恢复 | 三题单槽；r21 五题原生峰值 3、补位 2；r23 另批峰值 2 | PASS，峰值不足不计能力异常；不外推更高并发 |
| CV11 原始轨迹 | 一致 SQLite 备份、session/cwd/Prompt、缺失/冲突拒绝 | r15/r16 热写故障恢复；r21/r23 正式原始/标准轨迹 | PARTIAL；截断/乱序/孤立结果/子代理混入须逐分支核对覆盖 |
| CV12 指标 | 精确 runtime Profile、逐 request ID 与 turn 终值对账、掩码零不发布 | r22/r23 核心 Token、请求/工具、原生/流程耗时；旧批次 null 保留 | PASS（已声明字段）；可选未知量不补零 |
| CV13 候选与证据 | 通用候选/manifest/hash、越界/链接和漂移拒绝 | r21/r23/r27 正式 freeze + verify-only | PARTIAL；r33 已补目标路径冻结前后写入故障，缺文件/同名不同内容/受限链接等分支继续核对索引 |
| CV14 评分/回传恢复 | 独立 attempt、发布/重复导入/冲突拒绝的公共测试 | 三题 Judge capacity 原 thread 恢复；r20 sol 独立重评分；r21/r23 return/import | PARTIAL；submission 发布窗口中断的本范围证据待核对 |
| CV15 正式闭环 | 七阶段契约与独立发行 | r21 与 r23 各自同发行执行→首次 collect→评分→回传→导入→报告闭环 | PASS；r27/r28 新故障样本按变更影响复验，不改写旧报告 |
| CV16 平台 | 平台显式为 macos-x86-64，Token Profile 精确 runtime | QwenWorkCN 1.2.0 / SDK 1.0.46；r21–r35 | PASS（本平台）；其它平台 NOT_RUN |
| CV17 路径预算 | SDK 纯编码能力确认、实际 getconf 限制、原始/编码后字节预算、目录权限/链接检查 | r31 中文/空格真实路径与原生编码匹配；最长 ID 62 字符预检；五类负例均发送 0 | PASS（macOS 当前编码能力）；未知编码实现仍拒绝，未外推其他平台 |

| General 项 | 当前证据 | 结论/剩余项 |
| --- | --- | --- |
| GV01 准备与阶段边界 | r21/r23/r27 prepare/verify 与独立执行/评分包 | PASS |
| GV02 文件/纯回复 | support_handoff、temperature 与 colleague_leave_reply 正式 collect | PASS |
| GV03 工具轨迹 grader | 五题中的轨迹题与自动规则、原始 call/result 采集 | PARTIAL；缺必需轨迹拒绝需与实际 grader 逐项关联 |
| GV04 Git/二进制/链接与冻结 | 公共 exact-all freeze/链接反例，Qwen verify-only | PARTIAL；本客户端相应材料与故障样本需补索引 |
| GV05 三种评分 | r21/r23 automated、hybrid、llm_judge，固定 sol/high | PASS；本轮只声明 Codex 语义后端 |
| GV06 分母与失败隔离 | 公共异常/缺证据/零分测试，r20 独立重评分、旧评分保留 | PARTIAL；真机有效零分等样本尚未全部覆盖 |
| GV07 阶段恢复与报告 | r21/r23 submission、return/import、同源 JSON/Markdown/Excel | PASS |
| GV08 小批/并发 | r21 原生三路五题，r23 五题核心 Token、同机闭环 | PASS（固定五题/本机）；不声明跨机或全量 |

因此仍是“主流程有限可用、加固进行中”，完整接入任务保持 IN_PROGRESS。本轮已补齐 CV17、CV08、CV09 的上述重点；其余 PARTIAL 行继续按证据表审计，不以本轮三项通过替代全部准入。上述矩阵为人工证据审计，不代表已有自动符合性校验器。
