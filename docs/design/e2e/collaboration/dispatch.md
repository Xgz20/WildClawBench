# 首轮任务派发记录（历史）

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../general-e2e/README.md) 为准；本文件不再例行更新。

维护方：COMMON。派发日期：2026-09-19，Asia/Shanghai。这里保存归属与启动核验；开发进展和接收结果由各自任务卡维护。

本文件只记录首轮派发，不作为后续任务的创建模板。后续任务统一遵循[控制分支派发与回收合并流程](integration-workflow.md)，从控制分支当前 HEAD 创建新的 worktree；已回收的旧平台 worktree 不直接承接下一项需求。

三个 macOS worktree 均从 `03c38f280a64ad9bc9308c768f0f5795050355cc` 创建；随后采用包含 [COMMON-001](handoffs/COMMON-001.md) 的已发布台账与新公共基线。

| 任务 ID | 实际 Codex 任务 ID | 分支 / 主项目内 worktree | 启动核验 |
| --- | --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | `01a0b8d2-0ea9-7012-ac4f-c2bd69dc8b7b` | `feat/workbuddy-macos-general-e2e` / `.agents/workbuddy-macos-general-e2e` | 已启动；首轮 cwd/分支/base/clean 检查通过 |
| MAC-QWENWORK-GENERAL | `01a0b8d2-1cfc-7c11-8d78-3eb34c18b5b6` | `feat/qwenwork-macos-general-e2e` / `.agents/qwenwork-macos-general-e2e` | 已启动；首轮 cwd/分支/base/clean 检查通过 |
| MAC-DOUBAOWORK-WEB | `01a0b8d2-243e-7551-932d-f203d6842f32` | `feat/doubaowork-macos-web-e2e` / `.agents/doubaowork-macos-web-e2e` | 已启动；首轮 cwd/分支/base/clean 检查通过 |
| WIN-ASTRONSTUDIO-GENERAL | 尚待 Windows 本机创建/接收 | 计划 `feat/astronstudio-windows-general-e2e` / `.agents/astronstudio-windows-general-e2e` | 启动包与交接已准备；没有 Windows 验证 |

三个客户端选用独立长期任务，便于分别恢复和保存现场。公共接口由有界 subagent 在 COMMON 专属 worktree 实现并交付控制任务审查。

创建接口没有自定义 cwd 参数，托管 worktree 位置不能满足用户指定目录。因此任务 UI 归属主项目，但所有命令/编辑必须显式指向预建 worktree；三个任务均已回报绑定核验，不得在主检出默认 cwd 编辑。

初始阶段仅只读盘点与离线开发。2026-09-19 第二轮控制已启动：当前桌面分配与审查记录见[控制推进记录](control-progress.md)。启动/重启、目录选择、配置切换、Prompt 发送与 smoke 均由控制任务安排独占。此记录不是实时锁，也没有配置定时巡检。

集成分支中的平台卡可能仍是最近一次已合入快照。“是否派发/绑定”以上表为准；平台卡改动由负责人提交后审查集成，COMMON 不代填 ADOPTED/VERIFIED。三个任务不自行 push 或合入主分支。

DoubaoWork 可只读复用旧 `.agents/doubaowork-macos-probe` 原型，保留未提交内容；历史本地项目/CDP 证据不等于正式 Web 闭环。

## v2 派发与串行切换记录（2026-09-20）

三条 v2 worktree 原计划均从控制 HEAD `bd9dbe6c91c98468b12628a68507f0b732d653ab` 创建。实际核验后，WorkBuddy v2 仅补充离线交接文档、QwenWork v2 没有新增代码提交；两者继续运行只会重复校验，已冻结为审计材料。DoubaoWork v2 提交 `3588c16`，控制侧以 `e2c1d9e` 接收，具体变更为 Web metrics 采集、Doubao parser 与 4 个覆盖测试。

后续改为串行：每次只保留一个活动平台 worktree；平台完成并合入控制分支后，以新的控制 HEAD 创建下一平台 worktree。旧 v2 WorkBuddy/Qwen 分支不得直接合入 `e2c1d9e`，如需继续必须重新从 `e2c1d9e` 派发。
