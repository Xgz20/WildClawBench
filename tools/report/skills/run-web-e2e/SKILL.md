---
name: run-web-e2e
description: 按用户明确要求动态组合 Web E2E 的准备、桌面 Harness 执行、Codex Desktop 评分、离线回传、收集和报告阶段；持久化可恢复状态，但不替代各单阶段 Skill。
---

# 编排 Web E2E 全流程

本 Skill 是跨阶段组合器。现有 `prepare-web-e2e-workspaces`、`execute-web-e2e`、`orchestrate-web-e2e`、`score-web-e2e` 和 `report-web-e2e` 仍可人工独立使用；本 Skill 只在用户要求跨阶段串联、离线交接或统一恢复时启用。

## 1. 只选择用户明确要求的阶段

把用户 Prompt 映射为以下显式阶段，再传给状态脚本。不要让 Python 猜测自然语言：

- `prepare`：调用 `prepare-web-e2e-workspaces`。
- `execute`：调用 `execute-web-e2e`。
- `score`：调用 `orchestrate-web-e2e`，并让每个独立 Codex Desktop 评分任务使用 `score-web-e2e`。
- `package`：生成完整 Harness 离线回传 ZIP 和外部回执。
- `collect`：在管理员机离线导入并校验回传包。
- `report`：调用 `report-web-e2e` 生成 JSON、Markdown 和 Excel。

没有明确阶段且磁盘上也没有运行状态时，只说明可选阶段和缺少的输入，不创建文件、不准备题目、不执行 Harness。用户说“继续”或“恢复”时，读取已有状态并沿用冻结的 `selected_stages`。用户显式提到的阶段优先于可选预设：

- `admin`：批次级 `prepare,collect,report`。
- `worker`：Harness 单元级 `execute,score,package`。
- `full-local`：分别初始化批次级 `prepare,collect,report` 和单元级 `execute,score,package`。

未选择的阶段始终是 `NOT_SELECTED`。前置产物缺失时报告阻塞，不能为了“跑通”而隐式增加阶段。

## 2. 初始化和恢复状态

批次状态位于 `<batch-root>/.run-web-e2e/batch-state.json`，只允许 `prepare,collect,report`。Harness 单元状态位于 `<harness-root>/.run-web-e2e/unit-state.json`，只允许 `execute,score,package`。

```bash
python3 <skill-dir>/scripts/run_web_e2e.py init \
  --scope unit \
  --root /absolute/<batch_id>/harnesses/workbuddy \
  --stage execute --stage score --stage package

python3 <skill-dir>/scripts/run_web_e2e.py resume \
  --scope unit \
  --root /absolute/<batch_id>/harnesses/workbuddy
```

首次选择会冻结。相同 `init` 幂等；需要扩大范围时必须显式 `add-stage`，不能用第二次 `init` 静默改计划：

```bash
python3 <skill-dir>/scripts/run_web_e2e.py add-stage \
  --scope unit --root /absolute/<harness-root> --stage package
```

单阶段开始、完成或失败后及时记录：

```bash
python3 <skill-dir>/scripts/run_web_e2e.py set-stage \
  --scope unit --root /absolute/<harness-root> \
  --stage execute --status RUNNING
```

`sync`/`resume` 只根据已存在且身份匹配的正式产物收口状态，不创建业务产物，也不把未选择阶段改成已选择。

## 3. 阶段动作

### 准备

严格按 `prepare-web-e2e-workspaces` 创建带时间戳的新批次。准备结果应包含五个独立 Skill ZIP 和 `packages/skills-manifest.json`。Skill ZIP 是按需离线安装材料，不表示各阶段绑定执行。

单机全流程也必须从生成的 `__execution.zip` 解压出独立 Harness 单元根，再在该根执行和合入 `__scoring.zip`。不要直接把管理员批次中的 `harnesses/<harness>/` staging 目录当作 worker execution 包；staging 可能预置非空评分模板，标准评分交接会正确拒绝覆盖。该规则只改变本机文件搬运位置，不改变 execution receipt、候选哈希或离线回传契约。

### 执行与评分

执行完全遵守 `execute-web-e2e`。WorkBuddy 新批次默认三槽、最大八槽，UI 操作仍为单槽；用户显式指定模型时才传 `--model`，否则保持客户端当前模型和推理强度。

执行回执有效后才按 `orchestrate-web-e2e` 复制到独立评分工作空间并启动评分。Codex Desktop 新批次默认三槽，每题独立项目、任务、Browser 和端口。评分任务使用 `score-web-e2e`，候选 `workspace/` 永远只读；端口冲突只允许修改 `private-scoring/runtime-workspace/` 中的评分运行时副本。

### 离线回传与收集

评分生成有效 `submission.json` 后打包：

```bash
python3 <skill-dir>/scripts/run_web_e2e.py export-return \
  --package-root /absolute/<batch_id>__workbuddy \
  --output-dir /absolute/offline-return
```

该命令生成 `<batch_id>__<harness>__return.zip` 和外部 `return-receipt.json`。回执绑定 ZIP SHA-256、批次、源码 revision、Profile、模型、Harness 和完整 task IDs。目标存在时拒绝覆盖。ZIP 不含 `.git`、依赖缓存、运行时缓存、密钥或 `.run-web-e2e` 控制状态。

管理员离线收到 ZIP 和回执后导入：

```bash
python3 <skill-dir>/scripts/run_web_e2e.py import-return \
  --batch-root /absolute/<batch-root> \
  --archive /absolute/<batch_id>__workbuddy__return.zip \
  --receipt /absolute/<batch_id>__workbuddy__return-receipt.json
```

导入先在隔离临时目录中校验 ZIP SHA、路径穿越、符号链接、唯一顶层 Harness 根、唯一 submission，以及批次/revision/Profile/Harness/task IDs；全部通过后才原子发布到 `<batch-root>/returns/<harness>/`。相同内容重复导入幂等，冲突内容拒绝覆盖。

### 报告

只有 `collect` 已完成或用户明确提供了一组已经校验的回传包时才进入 `report-web-e2e`。报告的 JSON、Markdown、Excel 三件套生成并验证后，再把 `report` 标记为 `COMPLETED`。

## 4. 不可变性和证据边界

- 同一 Harness（模型）单元不能拆到多台机器。
- execution 终态候选和复制后的 score 候选都不可修改。
- 不得把状态机单测、历史包、模拟 submission 或静态检查当作本轮真实 E2E 成绩。
- `NEEDS_ATTENTION`/`FAILED` 必须保留现场；恢复只处理原任务、原 attempt 和原磁盘状态。
- 每一阶段的具体门禁以对应单阶段 Skill 为准；本 Skill 不重新实现做题逻辑或评分判断。

离线文件格式和安全门禁见 [交接契约](references/handoff-contract.md)。
