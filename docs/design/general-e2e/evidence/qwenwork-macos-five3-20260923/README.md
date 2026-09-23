# QwenWork macOS General 固定五题证据

日期：2026-09-23（Asia/Shanghai）。目标客户端为 QwenWorkCN 1.2.0 / macOS x86_64；原生 Token/cache profile 尚未验证。固定五题为 `retro_agenda`、`support_handoff`、`temperature_cli_fix`、`colleague_leave_reply`、`suspicious_installer`。本页区分发送占槽与原生主 turn 重叠，**尚不能声明真机原生三路或受控生产可用**。

## 本次 r20：执行、采集、sol/high 评分和报告

- 源码修复提交 `cd678863219ee702c7f41df6d36b1d1ab2874aa0`；独立发行 `report-workspace/general-e2e/releases/qwenwork-macos-general-five3-cd67886`，suite SHA-256 `1287e371cb35a286ea31dbb0939ffd4c40b2bff565d992b95b428b096348a1f2`。release-root、suite、五题 prepare/verify 均 PASS；execute Skill `0.10.14`。调试执行根为 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r20`，批次 ID `qwenwork-macos-general-20260923-five3-r20`，包内 Harness 版本字段与实际 probe 均为 `1.2.0`。
- 队列以 `--run-slots 3 --preprepare-projects --skip-clarifications` 运行：先逐题预建独立项目与草稿，再按 manifest 顺序单槽发送。五题各发送一次、attempt 各唯一、5/5 原生完成；第二、第五题因瞬时终态证据冲突进入 `NEEDS_ATTENTION`，fresh probe 后沿原 attempt 恢复，均未重发。队列发送占槽峰值 `3`、补位事件 `2`。本批次未出现可供自动点击的追问卡片，故 `--skip-clarifications` 的真机自动分支仍待验证；r19 中用户指定的“会议日期”卡片由控制端确认唯一按钮后手工点击了“跳过”。
- 只读脚本 [audit_native_overlap.py](audit_native_overlap.py) 逐题校验 trace-index、原始 segment SHA、唯一非 subagent 主 `turn.started/turn.finished` 和 session/attempt 身份，结果在 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r20/native-overlap-audit-verified.json`。原生时间覆盖 `5/5`，**峰值 `2`**。前三题依次为 `12:09:00.870–12:09:28.859`、`12:09:30.285–12:10:36.946`、`12:10:08.003–12:10:42.998`（UTC+08:00）；第一题结束后 1.426 秒第二题才开始。其余两题分别为 `12:13:53.804–12:14:04.208` 与 `12:14:26.360–12:15:08.591`。队列原始 receipt 的 `native_interval_coverage=0/5`，其 `observed_max_concurrency=3` 仅代表发送至终态的占槽；补充审计不能反写或替换冻结 receipt。
- 五题 Qwen collector、cleanup/finalizer 和逐题 `--verify-only` PASS；正式 `collect-evidence-receipt.json` 为合法 `partial`，缺失的是未验证的 Token/cache 等覆盖。正式指标中原生任务耗时采用 SDK `turn.finished.duration_ms`，五题合计 `180.759` 秒；流程耗时 `617.23` 秒单列，不包含预建项目的前置耗时。已落盘模型请求 `23`、工具调用 `21`；Token/cache、HTTP 尝试仍为 `null/unavailable`。
- 最初冻结的 `gpt-6-astra/high` 编排已锁定独立历史 submission。用户随后将裁判固定为 **`gpt-6-sol/high`**；在同一批次冻结候选上新建独立重评分编排，三个语义原 thread 均通过 `verify-score`，两道 automated 规则题有效。sol/high 的五题分数依次为 `0.6625 / 1.0 / 1.0 / 0.7625 / 1.0`，5/5 valid、均分 `0.885`、评测异常 `0`。sol/high return package ID `9553cc3e972a58072ba4a13b267530fd8daee8f3fb86e8d73b419c0d4a851d93`，archive SHA-256 `8a90457af94e836207fc8ddabe48ec8ac8b375636407464adbcd96edf946625a`。
- sol/high 准备根 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-20260923-five3-r20/prepared-sol/qwenwork-macos-general-20260923-five3-r20` 与原准备根的 batch manifest、execution ZIP、scoring ZIP 哈希完全一致，只有裁判/报告配置不同；独立 prepare/verify、return import、report validate-inputs 和 batch receipt PASS。报告位于其 `reports/qwenwork-r20-gpt6-sol-high/`：同源 JSON、领导版 Markdown、审计 Markdown、10 Sheet Excel 与 10 张预览均已生成。

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
- r20 证明预建策略消除了 r19 的路由门禁并完成五题闭环，但**没有改善原生峰值 2**。因此暂不把“先建全部项目”认定为正式默认策略；正式流程可在不改变五题与证据契约的前提下选择该策略，但须说明其目的是缩短发送阶段的 UI 间隔，不能把预建/队列时间计入原生任务耗时。真正三路仍需新的同批次原生时间证据。
- 发送临界中断、QwenWork 客户端重启/重连、未知授权/追问自动处理、真实残留进程清理与无关进程保护尚未完成适用故障矩阵的真机验收；Codex Desktop 重启按用户要求暂缓。macOS x86_64 结果不外推 Apple Silicon、Windows 或 60 题全量。
