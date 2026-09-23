# E2E 串行修改与交付

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../端到端自动化评测Harness接入契约.md)。

2026-09-21：原“派发 worktree → 平台交接 → 控制分支回收”流程退役。当前规则与状态见 [General E2E 开发接续入口](../../端到端自动化评测Harness接入契约.md#integration-progress)。

1. 检查当前项目工作区 / `feature/astroncode-eval` 的状态，直接逐项修改；保留无关改动。
2. 完成一项后核对差异，运行受影响检查，更新唯一进度入口及必要证据，单独提交中文 Conventional Commit。离线 PASS 不提升真机状态。
3. 旧平台 worktree 仅作审计，不从它们继续开发或重复合入代码；不需要按任务再建分支、填写派发或接收清单。
4. 控制分支 `b759d87` 已快进合入工作区，后续无需平台/控制分支回收。旧控制 worktree 保留审计，不继续迭代；当前不 push。

原流程、旧分支冲突和 reconciliation 记录保留在 Git：`git show e29a7c8:docs/design/e2e/archive/collaboration/integration-workflow.md`。运行期 UI/attempt 锁、候选冻结与精确 cleanup 仍属于技术要求，不随开发串行化删除。
