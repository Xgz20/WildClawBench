# G2-05 AstronStudio 候选冻结与正式执行回执证据

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

## 结论

2026-09-18 使用 `collect-general-e2e` 正式收口器，对 G2-02 已完成、G2-03/G2-04 已归档轨迹与资源指标的 S1、S4 真机 attempt 完成任务进程零残留确认、5 秒 Workspace 静默、exact-all 候选冻结、证据清单和正式 collect receipt。两题均通过 `--verify-only`，正式 execution record 与 collect receipt 也通过 General E2E 契约验证。

本次复用已完成 attempt，没有发送新 Prompt，也没有重启 AStudio。收口前的只读 probe 确认 AStudio `3.3.1` 主进程、`127.0.0.1:9240` loopback CDP 归属、`GLM-5.2 / High / 完全访问` 和活动/待处理会话数为 0。该 probe 只证明收口前环境安全，不替代执行阶段证据。

## 真机结果

| 样本 | 正式状态 | 进程收口 | Workspace 静默 | 候选 | 正式产物 SHA-256 |
| --- | --- | --- | --- | --- | --- |
| S1 `02_Code_Intelligence_task_001_temperature_cli_fix` | `COMPLETED / completed`，evidence `complete` | 前后目标均 0，安静 `5637 ms` | 静默前、静默后、复制后三个 SHA 相同 | 6 文件，5066 bytes，`87cf47353206e9ceb4c4d9bb67a4326bc76ef7376cf26b03c82da5514362e070` | manifest `a85eaf831baf8f51fce3f60b3edf0433c20ba8e5e39b24ec79612b73c60c2f5d`；record `ff2a90088d2a57d5426a8468e0554ac744657cc3832000cbe64bcd34685cbdb5`；receipt `d4c6eca1ab4852cca5884e91bf1be9ae639f53812914ff437925758a5cc7fed5` |
| S4 `01_Productivity_Flow_task_003_retro_agenda` | `COMPLETED / completed`，evidence `complete` | 前后目标均 0，安静 `6011 ms` | 静默前、静默后、复制后三个 SHA 相同 | 1 文件，1 byte，`1ac1d99d2123fd4eaa234d95e989f85787d08473cd4e6b3d66648ade5af65592` | manifest `23937f80965b9f10551939aebbbb0d7ea01d46f0e757c6e973bbd42d5fceb14d`；record `1a3c175d7d98e5d042689e6f3f3a9b07780abe2d4d5a38c2dbc63612e058af37`；receipt `cf76d9014456827bc88e6191caa411feca0c4c80cb64a411005a33a5b116c4fd` |

原始执行 Workspace 与冻结候选仍保存在忽略提交的 worker unit 中，供 `--verify-only` 重算。这里提交的是正式 JSON 摘要副本，不复制候选文件、完整 trace 或资源文件，因此本目录本身不是可送评分的独立 execution unit。

## 证据文件

S1：

- [execution record](s1/execution-record.json)
- [collect receipt](s1/collect-evidence-receipt.json)
- [candidate artifact](s1/candidate-artifact.json)
- [process cleanup](s1/process-cleanup.json)
- [evidence manifest](s1/evidence-manifest.json)

S4：

- [execution record](s4/execution-record.json)
- [collect receipt](s4/collect-evidence-receipt.json)
- [candidate artifact](s4/candidate-artifact.json)
- [process cleanup](s4/process-cleanup.json)
- [evidence manifest](s4/evidence-manifest.json)

## 实现与失败门禁

- 正式收口器在发布前绑定 unit/dataset/task/attempt、Prompt digest、一次发送、thread/turn/session/cwd 和终态。
- macOS 进程识别使用 Workspace 绝对路径或 cwd 精确 seed，包含后代；信号发送前校验 PID、启动时间和命令 SHA。真实专项测试额外启动 cwd 位于临时 Workspace 的 `/bin/sleep`，成功识别并终止且未影响无关进程。
- 候选默认 exact-all，不套用 Web E2E 的 `.git/node_modules` 过滤；S1 的 `__pycache__` 因而被如实保留。绝对或越界 symlink、特殊文件、禁止目录均失败关闭。
- 回归覆盖清理失败、静默窗口漂移、冻结候选内容/权限漂移、原始 Workspace 漂移、manifest 漏项、正式输出不可覆盖、timeout 部分轨迹、infrastructure error partial receipt 和越界 symlink。
- receipt 已存在检查在进程操作和 evidence 发布前完成；receipt 采用不覆盖的原子发布。stable candidate 的 path/SHA/frozen_at 以及 completed receipt 的逐任务状态均有契约语义校验。

## 验收边界

G2-05 证明 macOS 上两个已完成真机 attempt 可以形成可验证的正式执行回执，并完成 `collect-general-e2e` `0.4.0/operational` 的候选冻结主链路。它不证明 Windows 适配，也不把 MAC-07 标记为通过：真实中断、客户端重启、未知交互和 timeout 故障注入仍待后续用例完成。
