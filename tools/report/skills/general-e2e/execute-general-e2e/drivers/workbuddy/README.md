# WorkBuddy macOS General 离线预检

在真实新时段开始前，从脱仓后的 `general-e2e` Skill 根目录运行：

```bash
node execute-general-e2e/drivers/workbuddy/preflight.mjs --skill-root /absolute/general-e2e
```

预检只读取包内文件，确认 `task-process-cleanup` 共享组件、WorkBuddy 的四个原生
source gate 字段和 CB-B 的 state/trace/resource/cleanup 输入仍可装配。输出 `PASS`
只代表离线包完整，不代表客户端已启动、slot 已取得、历史 canary 已处理或真机
collect/cleanup 已通过。

正式 collect 还必须保存本题的 `conversationId`、`requestId`、原生 `cwd`、终态来源、
原始 trace、resource metrics，以及 cleanup 前后精确 Workspace 进程快照；缺任一项应
保持 `REVIEW/未验证`，不能用状态字段或候选 Workspace 反推。

