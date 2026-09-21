# E2E 串行修改与交付

2026-09-21：原“派发 worktree → 平台交接 → 控制分支回收”流程退役。当前规则与状态见 [General E2E 开发接续入口](../../general-e2e/README.md)。

1. 检查控制 worktree `.agents/e2e-harness-contract` / `feat/e2e-harness-contract` 的状态，直接逐项修改；保留无关改动。
2. 完成一项后核对差异，运行受影响检查，更新唯一进度入口及必要证据，单独提交中文 Conventional Commit。离线 PASS 不提升真机状态。
3. 旧平台 worktree 仅作审计，不从它们继续开发或重复合入代码；不需要按任务再建分支、填写派发或接收清单。
4. 本地控制分支形成阶段性交付后，合入主工作分支与 push 是另行安排的发布动作；当前不执行。届时检查双方差异、依赖和受影响验证，保留提交历史与未完成项。

原流程、旧分支冲突和 reconciliation 记录保留在 Git：`git show e29a7c8:docs/design/e2e/collaboration/integration-workflow.md`。运行期 UI/attempt 锁、候选冻结与精确 cleanup 仍属于技术要求，不随开发串行化删除。
