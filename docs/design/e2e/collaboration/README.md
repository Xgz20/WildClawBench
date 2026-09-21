# E2E 历史协作档案

2026-09-21 起，本目录退出日常开发流程。当前唯一入口为 [General E2E 开发接续入口](../../general-e2e/README.md)，包含串行顺序、全部平台/Harness 状态、代码基线、证据和新会话 Prompt。

当前直接在 `.agents/e2e-harness-contract` / `feat/e2e-harness-contract` 迭代；优先 macOS 四个 Harness 的 General，再支持 Windows。无需任务派发、独立平台 worktree、桌面时段申请或逐交接接收。

旧文件保留原路径，供提交映射、失败现场和证据追溯使用；其中“当前”“下一项”“必须申请”等表述仅属于历史安排，不作为新会话指令。无需例行更新 task card、handoff、dispatch 或 SLOT。

历史入口：[基线与发行](baseline.md)、[派发记录](dispatch.md)、[原控制记录](control-progress.md)、[任务卡](tasks/)、[交接](handoffs/README.md)。旧内容未保留在当前文件时，可用 `git show e29a7c8:docs/design/e2e/collaboration/<文件名>` 查询本次整理前快照。
