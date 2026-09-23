# G3-03 Codex 评分任务编排证据

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

## 结论

2026-09-18 在 macOS 开发机上完成 `orchestrate-general-e2e` `0.2.0/interface_only` 的 Codex Desktop 项目注册与可恢复单题任务编排子能力。控制器可以从正式 execution record 和独立 scoring ZIP 创建每题私有评分 attempt，冻结 Judge 配置，并持久化 project、thread、host、cursor、wait sequence 和 deadline。

本项没有创建真实 Codex Judge task，也没有运行语义裁判或生成有效 `score.json`、总分和 submission。测试中的 thread、cursor、模型名和项目清单均为 fixture；`THREAD_COMPLETED` 只表示编排任务终态，不能解释为评分有效。正式取证、逐 criterion 判定、确定性校验和合分由 G3-04 实现。

## 已交付能力

- 每题调用 `score-general-e2e prepare/verify` 建立独立私有 attempt，冻结 unit/report/scoring ZIP、score Skill 入口、runtime lock、Prompt、任务顺序和 Judge 配置。
- 只接受模型与推理强度均已配置的 `codex-agent-judge-v1`；`api-judge-v1`、空值、`unconfigured-*` 和未知推理强度失败关闭。
- Codex Desktop 项目注册器随 Skill 独立分发，支持 macOS 原生目录选择和 Windows PowerShell UI Automation；已有项目只能按规范化绝对路径唯一匹配后复用。
- 首版固定 `score_slots=1`。当前题未取得明确终态前不切换下一题；deadline 到达后继续等待原 thread，不自动补发替代任务。
- 恢复状态保留 project/thread/host/cursor/wait sequence/deadline/history；项目路径、Desktop 版本、thread host、wait sequence、Prompt、attempt manifest、注册证据、Skill 或 runtime lock 漂移均拒绝继续。
- 控制器和注册器不启动 Docker；General E2E 评分仍使用 G3-02 的本地受管规则 Worker。

## 验证结果

| 检查 | 结果 | 证据边界 |
| --- | --- | --- |
| 编排器聚焦测试 | 6/6 PASS | fixture 覆盖独立 attempt、已有项目复用、host、cursor、deadline、单槽、配置和漂移门禁 |
| General E2E Python | 87/87 PASS | 静态、fixture、Node wrapper 和脱仓包测试；不是真实 Judge 评分 |
| 旧 `eval_e2e` | 60/60 PASS | 兼容回归；旧 Docker 评分路径未被本项调用 |
| Codex Desktop 项目注册器 | 11/11 PASS | Web/General 两份独立分发副本中当前一致的注册器源码，其参数、loopback、CDP 兼容和 macOS/Windows helper 合同测试通过 |
| Skill 结构 | 13/13 PASS | Web 6 + General 7 个 Skill 的 `quick_validate.py` |
| General layout | PASS | 7 个 Skill、5 个共享组件、0 errors |
| 独立发行 | PASS | 临时 General release build、release-root verify、suite verify；7 个 Skill 均通过 |

关键实现和测试入口：

- [编排控制器](../../../../../tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/orchestrate_general_e2e.py)
- [操作契约](../../../../../tools/report/skills/general-e2e/orchestrate-general-e2e/references/codex-orchestration.md)
- [聚焦测试](../../../../../tests/general_e2e/test_general_scoring_orchestration.py)

## 平台与未完成项

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| macOS 编排代码与发行包 | PASS | fixture、注册器合同、独立包 help 和依赖闭包通过 |
| macOS 真实 Judge task | NOT_RUN | O-01 尚未冻结真实评分模型和推理强度；未调用 `create_thread` |
| Windows 代码路径 | IMPLEMENTED | `.cmd` launcher、应用发现、版本读取和 PowerShell 文件夹选择已有静态/合同覆盖 |
| Windows 真机 | NOT_RUN | 尚未验证真实 Codex Desktop 项目注册、任务创建、等待和恢复 |

G3-04 开始真实评分前必须先完成 O-01，并在控制 Harness 中冻结真实 model/thinking。后续真实 attempt 必须使用新的运行证据，不能复用本页 fixture 结论充当生产准入。
