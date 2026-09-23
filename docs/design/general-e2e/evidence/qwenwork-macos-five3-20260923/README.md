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
- 发送临界中断、QwenWork 活动任务期间的客户端重启/重连、未知授权/追问自动处理、QwenWork 真实残留进程清理与无关进程保护尚未完成适用故障矩阵的真机验收；Token 启动器只证明在数据库空闲时可安全换成带开关的新进程。Codex Desktop 重启按用户要求暂缓。可见 UI 的“标准”档位仍不能提供可信实际模型 ID；macOS x86_64 结果不外推 Apple Silicon、Windows 或 60 题全量。
