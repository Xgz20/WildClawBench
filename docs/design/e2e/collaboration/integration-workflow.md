# 控制分支派发与回收合并流程

维护方：COMMON。适用于本轮之后新增或继续接入的 Harness 任务。控制分支是开发集成入口，主工作分支只接收已经完成控制侧验收的阶段性基线。

## 分支角色

| 角色 | 分支 / 位置 | 责任 |
| --- | --- | --- |
| 控制集成 | `feat/e2e-harness-contract` / `.agents/e2e-harness-contract` | 固定派发基线、接收平台提交、运行组合回归、登记接收映射 |
| 平台任务 | `feat/<描述>` / `.agents/<worktree>` | 只实现本 Harness 范围，提交代码、测试和交接记录 |
| 主工作分支 | `feature/astroncode-eval` | 只接收控制分支已经形成的阶段性基线，不直接接收平台分支 |

平台任务、控制集成和主工作分支不是同一个工作树。任何任务都必须显式记录实际 worktree，不能因为任务 UI 位于主项目就把主检出当作编辑目录。

## 一轮任务的生命周期

### 1. 从控制分支派发

控制会话先冻结当前 `control_base_sha`，再从该 SHA 创建每个并行任务的 worktree 和 `feat/<描述>` 分支。派发记录至少包含：任务 ID、Codex task ID、完整 base SHA、分支、worktree、证据根和修改边界。

新的平台分支必须以控制分支当前 HEAD 为祖先。不得从旧公共基线、另一个平台分支或主工作分支的未接收提交创建下一轮任务。

### 2. 平台独立开发

平台任务只修改任务卡声明的专属路径；公共文件通过控制会话协调。每个提交使用中文 Conventional Commits，提交前检查：

- worktree clean，未提交和未跟踪文件有明确处理；
- 代码、fixture、测试和文档范围与任务卡一致；
- 离线验证、真机证据和生产声明分开记录；
- 不在平台分支直接 merge 主工作分支，不 push 代替控制侧接收。

### 3. 平台交接

任务完成或暂时阻塞时必须交付 `source_base_sha`、`source_head_sha`、提交范围、变更文件清单、测试命令与结果、未完成项和证据路径。控制会话以提交和文件为准，不以聊天中的“完成”替代交接。

### 4. 控制分支接收

如果平台分支从当前 `control_base_sha` 创建且没有跨边界修改，控制会话在控制 worktree 中使用：

```bash
git merge --no-ff --no-commit <platform-branch>
```

然后审查暂存区的文件清单、差异和测试，再生成控制侧 merge commit。这样平台分支的完整提交范围都会进入审查，不依赖人工挑选单个提交。

如果平台分支不是当前控制分支的祖先，禁止直接盲合。必须先冻结双方 HEAD，执行 `git log`、`git diff --name-status`、`git range-diff` 和 `git cherry`，建立“平台源提交 → 控制接收提交”的映射；发现旧基线、重复提交或无关证据时，先做一次受控 reconciliation，再接收代码。

### 5. 接收验证

控制侧接收至少验证：

1. 平台分支 worktree clean，源 HEAD 可复现；
2. 变更文件都属于任务边界，公共文件有协调记录；
3. `git diff --cached --check` 和适配器专属测试通过；
4. `git cherry <control-head> <platform-head>` 中没有未解释的 `+` 提交；
5. 控制分支组合回归通过，失败原因和环境问题单独登记；
6. 任务卡记录源 SHA、控制集成 SHA、测试和未完成生产门禁。

只读预检或离线测试通过，不等于真机发送、正式 collect、cleanup、评分或生产准入通过。

### 6. 生成下一轮基线

本轮所有并行任务完成接收或明确标记阻塞后，控制分支 HEAD 形成新的 `control_base_sha`。下一项任务只能从这个 SHA 派发新的 worktree；不继续在已经回收的旧平台 worktree 上叠加下一项需求。

主工作分支的提升是独立动作：在控制分支完成组合验证后，由控制会话将控制分支一次性合并到主工作分支。主工作分支不得反向成为平台任务的开发源。

## 当前迁移状态

本流程从控制基线 `b07495007f46e977ca6c183cdf416cfa1c87c031` 开始生效，流程文档提交 `1d61be3` 后，下一轮派发基线为 `1d61be3`。现有 WorkBuddy、QwenWork、DoubaoWork worktree 都以旧公共基线 `ddba8d645da18af75d04fad4a7a47ec1aaa1c161` 为共同祖先；它们的历史接收不能证明已完整同步。后续若需继续使用这些分支，必须先完成 reconciliation；新任务直接从 `1d61be3` 或其后的控制 HEAD 创建。
