# MAC-WORKBUDDY-GENERAL-003：SLOT05 发送前草稿隔离失败

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 创建时间 | `MAC-WORKBUDDY-GENERAL-003` / 2026-09-19（SLOT05 发送前门禁） |
| 来源任务 / 唯一负责人 | `MAC-WORKBUDDY-GENERAL` / `01a0b8d2-0ea9-7012-ac4f-c2bd69dc8b7b` |
| 目标任务 | COMMON 控制任务 `01a0b79a-09d7-7271-810a-7796036b8f35` |
| 基线 / 实现 SHA / 必需依赖 | 冻结源码 `0eddf84e34f2cd8f738f819eebdd963acda3ae77`（含 `5bea7621e4c90222d3f2e0000ab1ca6093af6e0b`）；当前工作树另已采用 COMMON-004 / execute 0.8.1 |
| 集成分支 / 集成状态与 SHA | `feature/astroncode-eval` / 当前独立文档待接收；不 push；后续发行应采用 COMMON-004 的固定 SYNC |
| 修改范围 | SLOT05 私有门禁证据、P2 证据索引、WorkBuddy 任务卡；没有创建 attempt，没有修改代码、共享 Schema 或旧 journal |
| 关联任务与验收 ID | Mac P2/CV02/CV03/CV04/CV07/CV11/CV12；旧 attempt `3e554524-6599-4182-aecc-3257977867c0` |

本交接新增于 `MAC-WORKBUDDY-GENERAL-002` 之后。它不是成功 canary，也不更正旧 attempt；只记录一次受控 SLOT05 的发送前保护失败和停止决策。

## 冻结发行与只读门禁

为避免 COMMON-004 的 execute 0.8.1 中途替换活动批次，SLOT05 先冻结源码 `0eddf84e34f2cd8f738f819eebdd963acda3ae77` 和 execute Skill `0.8.0`。release `workbuddy-macos-p2-0eddf84` 的 suite SHA-256 为 `05107dfc13116e68e6afbe5a27d3ed600463d4f4d943d93f060acaf33f5a5cb5`，dataset bundle SHA-256 为 `181f718f4309cb85bd009e8eccba6b2581a9e9d1a41df17a4908dcf828e263f0`。独立 prepare Skill 生成 batch `workbuddy-macos-canary-20260919-02`，单题 execution/scoring 双包及 batch verify 均 PASS；Prompt SHA-256 为 `deb5f6554a69c93afe1e6ad1f1fb6d678adedfc8860dda0875afaa6d4281e621`。

`pre-canary-probe-01.json` 于 `2026-09-19T13:43:42.656Z` 返回 `PASS`：WorkBuddy 5.5.3/x86_64、PID 33343、CDP `127.0.0.1:9229`、唯一 WorkBuddy page target、原生 session index 仅一个历史 `Completed`。编辑器只读核验返回 Workspace/conversation 为空、模型 `xopglm52`、权限 `default-sandbox`；正文长度 31，正文和 HTML SHA 分别为 `48c34111a769d3367a62c87f1b06a90e1e34bdcd5c8f9137c37dd26679844141`、`14263d5c4a28339da5db126c07e6ba2f6e88e31b97079ed33ce86f67197c53a6`，均与私有备份一致。附件 input、选中文件和可见附件元素均为 0，发送控件为 1 但 disabled。

## 失败动作与边界

按已授权的“临时移出 → canary → 精确恢复”路径，只执行一次真实清空尝试：编辑器成功聚焦后发送 CDP Meta+A/Backspace key events，等待 500ms；正文仍为同一 31 字符和同一 SHA。`retry_count=0`。没有点击“新建任务”、没有填入 canary Prompt、没有调用发送动作、没有创建新 attempt、没有生成新 journal，也没有修改旧草稿。

失败证据为来源机器 debug 根的 `slot05/pre-canary-draft-clear-failure-01.json`。失败后的正文和 HTML 哈希仍与备份一致，Workspace/conversation 仍为空；因此现场已按原内容恢复，不需要再执行恢复动作。按控制要求应标记 `SLOT05_RELEASED`，不得再重试同一清空路径或把未创建的 attempt 当成发送失败。

离线 `5bea762` fixture 与 VM DOM guard 仍通过，但本轮没有进入 `Input.insertText`，所以不能声称真实 WorkBuddy 编辑器事件路径已验证。WorkBuddy collector、trace-index v2、真实 cleanup、conversation/request/cwd 绑定、终态和评分均未运行。

## 接收方动作

| 接收任务 | 要求级别 | 下一动作/真实入口与配置 | 通过条件/验收 ID | 失败或缺依赖时 |
| --- | --- | --- | --- | --- |
| COMMON 控制任务 | REQUIRED_BEFORE_EXECUTION | 核验 `pre-canary-draft-check-01.json` 与 `pre-canary-draft-clear-failure-01.json`，标记 `SLOT05_RELEASED`；不得再操作当前 WorkBuddy | 旧草稿哈希一致、无 attachments、attempt/click/send/native session 均为 0 | 保持现场并报告，不清空、不重试、不发送 |
| COMMON | REQUIRED_BEFORE_NEXT_RELEASE | 后续发行采用 COMMON-004/最新固定 SYNC 的 execute 0.8.1；不要把冻结 0.8.0 的未执行 batch 当作新发行 | release source/Skill/ZIP SHA 与 prepare identity 全部重建并登记 | 不复用 SLOT05 的 batch/unit/journal；继续离线验证 |
| COMMON | REQUIRED_BEFORE_CLAIM | WorkBuddy 专属 collector、trace-index v2、真实 cleanup hook 独立审查 | 真机原生来源和候选收口证据完整 | 不声明正式 collect、评分或生产准入 |

## 接续与风险

旧 SLOT03 attempt 继续保持 `reservation=1 / click=0 / send=0`，永不重发、重置或替换。SLOT05 没有 attempt，不能把“清空失败”计为模型失败或任务执行。任何后续真机验证都必须由控制任务重新授权 slot，先设计并验证不破坏用户草稿的隔离/恢复机制，再创建全新 attempt；不能依赖当前 WorkBuddy 进程、PID、CDP 或 UI 状态继续操作。
