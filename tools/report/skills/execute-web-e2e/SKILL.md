---
name: execute-web-e2e
description: 在桌面 Harness 中执行单个或批量 Web E2E 用例，持久化可恢复状态、终态证据和 execution_record；用于 WorkBuddy 等客户端的自动做题阶段，不负责评分或报告。
---

# 执行 Web E2E 用例

本 Skill 是桌面 Harness 执行自动化的唯一实现入口。当前已实现 WorkBuddy 单题 Driver 和串行队列 Worker；其他 Harness Driver 仍按 Roadmap 逐步接入。

## WorkBuddy 单题

先在 Driver 目录安装锁定依赖，依赖不能安装到候选工作空间：

```bash
cd .agents/skills/execute-web-e2e/drivers/workbuddy
npm ci
```

只读预检：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh --probe
```

`--probe` 不会点击“新建任务”。WorkBuddy 只有在新任务页挂载 workspace picker；若当前停在历史会话页，探针会以 `workspace-picker-not-visible` 返回未就绪。切换到未发送的新任务页后重跑，不能把该结果误判为插件或 CDP 不可用。

执行一个准备包中的任务：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh \
  /absolute/batch-root/execution/tasks/<task_id> \
  --model 均衡 \
  --permission-mode full-access \
  --restart-app
```

`--restart-app` 会退出并重新启动 WorkBuddy，仅在当前没有需要保留的运行任务时使用。WorkBuddy 已通过本地 CDP 端口启动时省略该参数。

中断后恢复：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy.sh \
  /absolute/batch-root/execution/tasks/<task_id> \
  --resume
```

恢复时必须沿用相同的 `automation_state.json`。Prompt 已进入发送临界区后，Driver 只检查已有 WorkBuddy conversation，不能盲目重发。状态不明时停在 `NEEDS_ATTENTION`。

## WorkBuddy 串行队列

用同一 `run-id` 按声明顺序执行多个任务：

```bash
bash .agents/skills/execute-web-e2e/scripts/run-workbuddy-batch.sh \
  /absolute/<batch_id>__workbuddy \
  --run-id <queue_id> \
  --task-id <task_id_1> \
  --task-id <task_id_2> \
  --permission-mode full-access \
  --model 均衡
```

`--permission-mode full-access` 是评测运行的显式授权：Driver 会在发送 Prompt 前回读权限状态，已开启时不重复点击；未开启时通过 WorkBuddy 自身的风险确认界面开启。WorkBuddy 5.5.3 将该设置作用于当前客户端的全部任务，而不是单个项目。省略该参数时默认 `current`，只记录当前权限，不修改客户端设置。

Worker 从 Harness 根目录的 `manifest.json` 按精确 task ID 解析工作空间，使用文件锁保证同一 execution 包只有一个 WorkBuddy UI 队列，并把状态写到 `execution/.execute-web-e2e/queues/<queue_id>/queue_state.json`。当前题只有在明确终态、自动化状态和 `execution_record.json` 一致后才会记录 `AUTO_ADVANCE` 并启动下一题。

队列停在 `NEEDS_ATTENTION` 后，先处理或扩充经过审查的安全规则，再使用完全相同的参数加 `--resume`。默认遇到 `INFRA_FAILED` 或 `TIMEOUT` 即停止；只有明确需要验证失败隔离时才使用 `--continue-on-terminal-failure`。

如果 Driver 在 Prompt 发送前因 UI 自动化错误进入 `INFRA_FAILED`，且候选 workspace 没有任何变化，可在修复根因后使用 `--resume --retry-pre-send-failure`。旧 attempt 会移入相邻的 `.attempts/<task_id>/<attempt_id>/` 留存审计；发送后失败、超时或已有产物变化时拒绝自动重试。

## 执行约束

- 选择的是单题根目录 `execution/tasks/<task_id>/`，不是其中的 `workspace/`。
- WorkBuddy 5.5.3 优先通过其输入框 workspace provider 写入并回读绝对路径；只有该能力不存在时才退回 macOS 原生文件夹选择器。不能只凭同名目录标签确认工作空间。
- Prompt 只从 `PROMPT.md` 读取；状态中只保存 SHA-256 和字节数，不复制正文。
- `automation_state.json` 和过程截图写到单题目录外；完成后的 transcript 证据才写回 `.web-e2e-evidence/`。
- 优先使用 WorkBuddy 本地 session 数据库中的 conversation 状态判定终态；DOM 负责补充运行中、授权弹窗和最终回复证据。不能用固定睡眠或 workspace 文件稳定代替明确终态。
- 未知授权、未知 session 状态、Prompt 发送临界区不明确都失败关闭。
- “允许完全访问”只决定 WorkBuddy 创建任务时的权限模式；若运行中仍出现授权面板，Driver 继续按下面的严格命令白名单处理，不会因为客户端已开启完全访问而自动批准未知操作。
- 只允许 Driver 对显式白名单且严格限定在候选 `workspace/` 内的普通操作自动选择一次性“允许”；当前唯一规则是清理该目录下的 `.DS_Store`。其他命令（包括同类命令的路径或参数变化）一律停在 `NEEDS_ATTENTION`。
- `SUCCEEDED`、`INFRA_FAILED`、`TIMEOUT` 分别映射为 `execution_record.json` 的 `completed`、`execution_error`、`timeout`；没有生成有效站点仍是正常完成，由评分阶段判低分。
- 第一版每台机器保持 `ui_slots: 1`、`run_slots: 1`，不要并发操作 WorkBuddy。

实现或审查其他 Driver 时，完整读取 [Driver 契约](references/driver-contract.md)。
