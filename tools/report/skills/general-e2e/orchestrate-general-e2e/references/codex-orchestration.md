# General E2E Codex 项目与任务编排

## 能力边界

本控制器把正式 execution record 与独立 scoring ZIP 交接为每题一个私有评分 attempt，并维护 Codex Desktop 项目、线程、wait cursor 和 deadline。它不执行 Harness，不亲自判分，不生成 `score.json` 或 submission。

本页只描述 `codex-agent-judge-v1` 分支。`report-config.json` 中的模型和推理强度必须是已选定的非空值；`unconfigured-*` 占位值会失败关闭。显式的 `api-judge-v1` 使用独立的 [API Judge 编排](api-orchestration.md)，两个分支不会静默互换。

## 初始化

输入需要包含：

- 已完成 collect 的 execution unit，且每个选择题只有一个可唯一发现的正式 execution record；存在多个 attempt 时用 `--execution-record TASK_ID=/absolute/path` 明确选择；
- 与 unit 身份和任务范围一致的 scoring ZIP；
- 同一批次的 `report-config.json`；
- 独立安装的 `score-general-e2e` Skill 目录。

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py init \
  --unit-root /absolute/path/to/execution-unit \
  --scoring-package /absolute/path/to/unit-scoring.zip \
  --report-config /absolute/path/to/report-config.json \
  --score-skill-dir /absolute/path/to/score-general-e2e \
  --output-root /absolute/path/to/private-orchestrations \
  --orchestration-id ORCHESTRATION_ID \
  --score-slots 3 \
  --score-timeout-seconds 7200
```

普通生产运行不要传验收标记。需要为批准的验收项单独留证时，显式增加例如 `--acceptance-id G4-03`。控制器会把 `{mode: acceptance, acceptance_id: G4-03}` 同时冻结到 orchestration state、queue digest、评分 Prompt 和每题 attempt manifest；四处不一致即失败关闭。该选项只适用于 `codex-agent-judge-v1`，不能用于 API Judge。重评分需要验收时必须在 `init-rescore` 再次显式传入，不能从源 attempt 隐式继承。

初始化采用临时目录和原子发布。每题调用 score Skill 的 `prepare` 子能力，生成不同的 `scoring_attempt_id`、attempt 根和评分 Prompt；状态冻结 unit/report/scoring package SHA、score Skill 绝对根目录、版本、入口路径与入口 SHA、runtime lock、裁判协议、模型、推理强度、可选验收标记、Prompt SHA、任务顺序和 deadline 策略。评分 Prompt 要求子任务只读取该冻结根，不使用项目、仓库或自动发现路径中的同名 Skill。语义评分默认 3 槽，可配置 1–8；改变槽位或验收标记必须新建 orchestration，不能恢复时漂移。

`automated` 任务先运行规则并在本地形成 `not-required` 语义组件和标准分，不创建 Codex 项目或评分会话；`hybrid` 先运行并冻结规则组件，再进入语义评分队列；`llm_judge` 直接进入语义评分队列。规则 Worker 不计入 `score_slots`，但当前控制器串行发起规则动作，避免把本地规则并发误报成语义评分并发。

## 注册 Codex Desktop 项目

先安装锁定 Driver 依赖并只读探测。Desktop 应优先在控制任务启动前以 loopback CDP 启动：

```bash
cd <skill-dir>/drivers/codex-desktop
npm ci

bash <skill-dir>/scripts/run-codex-project-registrar.sh \
  --probe \
  --endpoint http://127.0.0.1:9230
```

Windows 使用 `run-codex-project-registrar.cmd`。Driver 与 Web E2E 使用相同的 `wildclawbench.codex-project-registration/v1` 契约，但随 General Skill 独立分发；默认通过可见 UI 和原生文件夹选择器注册，不使用 Computer Use 操作 Codex 自己。只有测试人员明确接受当前 Desktop 版本私有接口风险时才可传 `--renderer-bridge`。

如果 macOS 当前控制任务就承载在需要补开 CDP 的 Codex Desktop 中，只能先持久化编排状态，再调用一次性托管入口：

```bash
/bin/bash <skill-dir>/scripts/restart_macos_desktop_debug.sh \
  --application codex \
  --port 9230
```

入口固定使用 `com.wildclawbench.desktop-debug-restart.codex` 单实例 Label、`RunAtLoad=true`、`KeepAlive=false`，状态和日志保存在 `~/Library/Application Support/WildClawBench/desktop-debug-restart/<run-id>/`。脚本发出正常退出后，只在目标进程属于已核对的 Codex bundle、窗口中出现精确的“退出 Codex？”/“Quit Codex?”标题且按钮为“退出”/“Quit”时自动确认；未知弹窗、辅助功能不可用或文案不匹配时不点击，继续使用 10 秒 TERM、5 秒 KILL 的有界兜底。当前回合中断后，新控制任务读取 `status.json` 并恢复原 orchestration；只有 `PASSED` 才继续项目注册。禁止使用 `launchctl submit` 或任何自动复活的临时任务；脚本检测到旧版 `com.wildclawbench.general-e2e.codex-debug`、`com.wildclawbench.general-e2e.codex-refresh` 或已有新 Label 时会失败关闭。

读取 `status` 的 `REGISTER_PROJECT.project_path`，先调用 Desktop 内置 `list_projects` 按规范化绝对路径唯一匹配。已经存在时直接复用并记录：

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py record-project \
  --orchestration-root /absolute/path/to/orchestration \
  --task-id TASK_ID \
  --project-id PROJECT_ID \
  --host-id HOST_ID \
  --project-path /absolute/path/from/recommended-action \
  --desktop-version DESKTOP_VERSION
```

不存在时先注册该目录：

```bash
bash <skill-dir>/scripts/run-codex-project-registrar.sh \
  --endpoint http://127.0.0.1:9230 \
  --project /absolute/path/from/recommended-action \
  --output /private/path/registration.json
```

再次调用 `list_projects` 确认绝对路径唯一匹配，再执行 `record-project`，并增加 `--registration-evidence /private/path/registration.json`。项目名相同或路径尾部相同不能代替完整路径匹配。

随后执行前置检查；Desktop 版本必须与项目登记时一致：

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py preflight \
  --orchestration-root /absolute/path/to/orchestration \
  --task-id TASK_ID \
  --desktop-version DESKTOP_VERSION
```

前置检查会重算队列、Prompt、项目证据、attempt manifest、候选原件和私有评分材料，并复核 score Skill 及 runtime lock 未漂移。

## 创建与等待评分任务

按 `status` 或 `resume` 返回的 `recommended_actions` 执行动作。最多同时出现冻结槽位数的语义任务；每个任务的状态更新仍单独、原子记录。`CREATE_THREAD` 时读取 `prompt_file`，调用 Desktop 内置 `create_thread`：

- target 使用动作中的 `project_id`，environment 固定 `{type: "local"}`；
- `model` 和 `thinking` 必须使用动作冻结值，不沿用控制会话默认值；
- 不创建 projectless、cloud 或 worktree 任务；
- 返回后立即保存 thread/host。

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py record-thread \
  --orchestration-root /absolute/path/to/orchestration \
  --task-id TASK_ID \
  --thread-id THREAD_ID \
  --host-id HOST_ID
```

`WAIT_EXISTING_THREAD` 使用动作中的 `thread_id`、`host_id`、`after_cursor` 和 `next_wait_sequence` 调用 `wait_threads`。每次返回后立即记录：

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py record-wait \
  --orchestration-root /absolute/path/to/orchestration \
  --task-id TASK_ID \
  --wait-sequence N \
  --wait-cursor CURSOR \
  --wait-status RUNNING
```

允许状态为 `RUNNING / POLL_TIMEOUT / NEEDS_ATTENTION / COMPLETED / FAILED / CANCELLED / INTERRUPTED`。`POLL_TIMEOUT` 只是本次等待没有变化；`NEEDS_ATTENTION` 应按 `INSPECT_THREAD` 读取原任务，必要时在同一线程继续，不得新建替代任务。

到达 deadline 时，状态先返回 `MARK_TIMEOUT`。执行 `mark-timeout` 后继续等待原 thread 的明确终态；即使原 thread 后来返回 `COMPLETED`，该 attempt 仍按超时失败保存，不自动新建重试：

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py mark-timeout \
  --orchestration-root /absolute/path/to/orchestration \
  --task-id TASK_ID
```

如果一次已发出的 `wait_threads` 跨过 deadline 后才返回，直接执行 `record-wait`；控制器会在同一次原子状态更新中先记录超时，再保存 cursor 和线程终态，不会把 deadline 后的 `COMPLETED` 误记为成功。

线程返回 `COMPLETED` 后，该槽进入 `SCORE_VERIFICATION_PENDING`，不会立即补位。执行 `status` 返回的 `VERIFY_SCORE`，确认评分会话已生成并校验 `score.json`，再记录结果：

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py record-score \
  --orchestration-root /absolute/path/to/orchestration \
  --task-id TASK_ID
```

`record-score` 调用冻结的 score Skill `verify-score`，复核标准 score、审计、语义查询日志和来源 SHA；有效能力分和合法的 `evaluation_error / total_score=null` 都可记录。只有评分产物通过校验后该槽才按冻结顺序动态补位。线程完成但缺少、篡改或未通过校验的 score 继续占用当前槽位。

## 恢复与失败关闭

控制任务重启后只运行：

```bash
python <skill-dir>/scripts/orchestrate_general_e2e.py resume \
  --orchestration-root /absolute/path/to/orchestration
```

严格继续返回的动作。不要重新 `init`，不要按最近任务猜测 thread，不要丢弃 cursor 或重置 deadline。状态使用原子替换写入，并假定只有一个控制任务串行修改；多个控制任务不得同时写同一 orchestration。

以下情况失败关闭：裁判配置未冻结、Codex 分支混入 API 动作、同题 execution record 不唯一、score Skill 或 runtime lock 漂移、Prompt/attempt/项目证据漂移、项目路径不一致、Desktop 版本改变、host 切换、wait sequence 跳号、deadline 未到提前超时，以及操作不属于当前活动槽位的任务。
