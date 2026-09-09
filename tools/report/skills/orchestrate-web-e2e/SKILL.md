---
name: orchestrate-web-e2e
description: 编排桌面 Harness Web E2E 的执行结果交接、Codex Desktop 评分项目注册和可恢复并发评分任务；用于把已完成的 execution 包闭环为 submission，不负责单题做题或评分判断。
---

# 编排 Web E2E 桌面评测

本 Skill 是执行与评分之间的控制平面。`execute-web-e2e` 负责被评 Harness 做题，`score-web-e2e` 负责一个 Codex Desktop 任务内的一题评分；本 Skill 只负责确定性地交接工作空间、注册项目、创建和等待评分任务。

## 1. 生成独立评分工作空间

输入必须是执行完成后的 Harness 根目录。`execution-receipt.json` 必须存在、`integrity.valid=true`，且每题 execution workspace 的当前 SHA 必须仍等于回执 `final_sha256`。评分不能直接在 `execution/tasks/<task_id>` 中进行，也不能只复制若干网页文件。

使用执行包自带的标准库脚本，严格按 `manifest.tasks` 把每个 `execution/tasks/<task_id>/` 复制为独立的 `score/tasks/<task_id>/`，再合并管理员提供的 scoring ZIP；不得复制 `.execute-web-e2e` 等执行控制目录。若新执行回执声明 `wildclawbench.web-e2e-runtime-directory-policy/v1`，复制时过滤 `.cache`、`.vite` 和 `node_modules`，但不修改 execution 原件；未声明策略的旧回执仍严格拒绝这些目录：

```bash
python3 <harness-root>/tools/prepare_scoring_workspace.py \
  --package-root <harness-root> \
  --scoring-archive <absolute-scoring-zip>
```

该步骤会在复制前、复制后和发布评分目录前重复校验哈希，把过滤后的候选 `workspace/`、`PROMPT.md` 和可选 `execution_record.json` 带入评分目录，并生成 `private-scoring/candidate_artifact.json` 冻结记录；该记录同时绑定 `execution-receipt.json` 的文件 SHA、运行时目录策略、模型选择模式、可选请求模型和实际回读模型。评分 contract 与可选 execution record 中的模型身份也会由该回读结果补全。score workspace 必须不含上述可忽略运行时目录，scoring ZIP 只能增加 `private-scoring/` 和 `.web-e2e-scoring-ready`。它不得覆盖、恢复、清理或接受漂移后的执行产物。

随后初始化可恢复的评分状态：

```bash
node <skill-dir>/scripts/scoring-control.mjs init \
  --package-root <harness-root> \
  --task-id <task_id> \
  --score-slots 3 \
  --score-port-base 4173 \
  --score-timeout-seconds 7200 \
  --max-retries 1
```

省略 `--task-id` 时使用 manifest 中的全部题目。新批次默认 `score_slots=3`，最多 8 路；显式传 `--score-slots 1` 可回退串行。每题固定使用 `score_port_base + task_index` 的独占端口。旧 revision 3 状态恢复时继续保持原 `score_slots=1` 和旧 Prompt，不自动升级。评分槽位、端口基数、deadline（默认 7200 秒）和失败终态重试数（默认 1 次）在同一批次初始化后均不可变。状态和逐题评分 Prompt 保存到 `score/.orchestrate-web-e2e/`，不写入候选 `workspace/`。

## 2. 用 Playwright 注册 Codex Desktop 项目

Playwright 只操作 Codex Desktop 的“打开文件夹/添加项目”界面，不输入评分 Prompt，不评判页面，也不使用 Computer Use 操作 Codex 自己。

Codex Desktop 必须在控制任务启动前由用户以仅监听本机的 CDP 端口启动。控制任务不得退出或重启承载自己的 Codex Desktop 进程。Driver 依赖由调用本 Skill 的控制 Harness 检查；缺失或 `npm ls --depth=0` 失败时，控制 Harness 在 Driver 目录自动执行 `npm ci`，不要求用户手工安装。安装失败时停止并报告原始错误，不能改用未锁定版本或把依赖装进候选目录。随后执行只读探测：

```bash
cd <skill-dir>/drivers/codex-desktop
npm ci

bash <skill-dir>/scripts/run-codex-project-registrar.sh \
  --probe \
  --endpoint http://127.0.0.1:9230
```

每题注册前先调用 Codex Desktop 内置 `list_projects`。若规范化绝对路径已经存在，直接复用其 `projectId`；否则一次只注册一个目录：

```bash
bash <skill-dir>/scripts/run-codex-project-registrar.sh \
  --endpoint http://127.0.0.1:9230 \
  --project <harness-root>/score/tasks/<task_id> \
  --output <harness-root>/score/.orchestrate-web-e2e/registration/<task_id>.json
```

默认路径必须通过可见 UI 和原生文件夹选择器完成。若目标 Desktop 版本的文件夹选择器在自动化会话中无法弹出，注册器应失败关闭；只有测试人员明确接受该版本私有接口风险时，才可增加 `--renderer-bridge`。该模式通过 Desktop 预加载 bridge 把已规范化的绝对目录交给内置项目管理器，仍须由 `list_projects` 精确回读，不能作为未记录的静默降级。升级 Desktop 后必须重新验证该模式。

macOS 原生文件夹选择器由随 Driver 分发的 Accessibility helper 处理，仍不属于 Computer Use。注册后再次调用 `list_projects`，必须按规范化绝对路径唯一匹配，不能按重复的目录名猜测。然后记录项目：

```bash
node <skill-dir>/scripts/scoring-control.mjs record-project \
  --package-root <harness-root> \
  --task-id <task_id> \
  --project-id <project_id> \
  --project-path <absolute-score-task-path> \
  --host-id <host_id> \
  --desktop-version <registrar-output-version> \
  --registration-method <registrar-output-ui-method>
```

创建评分任务前必须运行前置检查。`--desktop-version` 使用本次 registrar `--probe` 的实际结果；`--score-skill-dir` 必须指向 Desktop 独立安装的评分 Skill，而不是仓库副本或题目目录。私有 bridge 只有在测试人员已明确接受当前 Desktop 版本风险时才允许：

```bash
node <skill-dir>/scripts/scoring-control.mjs preflight \
  --package-root <harness-root> \
  --task-id <task_id> \
  --desktop-version <registrar-probe-version> \
  --score-skill-dir <installed-score-web-e2e-dir> \
  --allow-renderer-bridge
```

该门禁会核对 execution 与 score 两份候选 SHA、执行回执文件 SHA、运行时目录策略和禁止目录、项目注册时与当前 Desktop 版本、注册方式、`project-registry.json`、批次要求的评分 Skill 名称/版本、Skill 支持的 `metric_profile` 和当前题 contract。execution 只按新回执声明容忍可忽略目录，score 副本仍严格无运行时目录；任一项不一致时不得创建任务。可见 UI 注册不传 `--allow-renderer-bridge`。

## 3. 使用 Desktop 内置任务接口评分

禁止通过 Computer Use 点击 Codex 自身，也不要从外部启动裸 `codex app-server` thread。循环处理 `status` 或 `resume` 返回的 `recommended_actions`；`recommended_action` 只是数组第一项的串行兼容视图。状态文件只能由一个控制任务串行修改，评分任务本身可以并发运行：

1. 读取该题生成的 `scoring_prompt_file`。
2. 确认当前题的 `preflight.status=PASSED` 后，调用 Desktop 内置 `create_thread`，目标为已记录的 `projectId`，环境固定为 `{type: "local"}`。除非用户显式指定，不覆盖模型与推理强度。
3. 把返回的 `threadId`、`hostId` 记录到状态：

   ```bash
   node <skill-dir>/scripts/scoring-control.mjs record-thread \
     --package-root <harness-root> \
     --task-id <task_id> \
     --thread-id <thread_id> \
     --host-id <host_id>
   ```

4. 把全部活动评分任务组成一次 `wait_threads` 调用；需要诊断时再用 `read_thread`。每个目标都从对应 `recommended_actions` 项读取 `thread_id`、`host_id`、`after_cursor` 和 `next_wait_sequence`，返回后立即逐题串行持久化 poll 的 cursor 与状态：

   ```bash
   node <skill-dir>/scripts/scoring-control.mjs record-wait \
     --package-root <harness-root> \
     --task-id <task_id> \
     --wait-sequence <next_wait_sequence> \
     --wait-cursor <poll.cursor> \
     --wait-status <RUNNING|POLL_TIMEOUT|NEEDS_ATTENTION|COMPLETED|FAILED|CANCELLED|INTERRUPTED>
   ```

   `POLL_TIMEOUT` 只表示这次 `wait_threads` 没等到变化，不是评分超时；控制面只有到达该 attempt 的独立 `deadline_at` 后才执行 `mark-timeout`。某题失败后继续等待已经活动的其他题，但暂停补充新题，先按动作处理失败题。超时后原 `threadId` 状态仍不明时必须继续查询，禁止立即创建第二个任务。只有原任务已记录 `COMPLETED`、`FAILED`、`CANCELLED` 或 `INTERRUPTED` 终态，才可执行 `prepare-retry --retry-reason <说明>`，重新通过该题 preflight 后创建下一 attempt。

   `prepare-retry` 不删除失败现场。它先复核候选与评分初始输入，并要求受管评分服务和截图接收器已经进入可信终态；存在无 `runtime-state.json` 的运行时副本、仍为 `RUNNING` 的服务/接收器或身份不匹配的状态文件时一律禁止归档。门禁通过后，把旧 `private-scoring/` 原子迁入 `score/.orchestrate-web-e2e/attempts/<task>/attempt-<n>/private-scoring/`，再按初始化时冻结的文件清单恢复干净的 `task_contract.json`、`candidate_artifact.json` 和可选 fixtures。归档目录内生成 `attempt-error-receipt.json`，记录失败终态、deadline、cursor、错误、重试原因、候选复核结果以及所有归档文件的路径、大小和 SHA-256；状态中的 attempt 保存该回执 SHA。归档中断由 `pending-attempt-archives/` journal 恢复，回执或归档后续漂移会在 preflight/submission 阶段失败关闭。所有 attempt、cursor、poll 次数和 retry 次数均保留在状态中。

   一个评分任务必须实际使用 Codex Desktop 内置 Browser，并由 `$score-web-e2e` 生成 `private-scoring/task_score.json`。评分任务只能写 `private-scoring/`；候选 `workspace/` 是只读输入。站点端口冲突时优先改启动参数或环境变量；只有受管启动日志已证明冲突且端口无法外部覆盖时，评分 Skill 才能通过 `managed_runtime.mjs port-override` 修改运行时副本中的唯一数字端口并落审计。execution/score 候选原件仍不可修改，其他源码调整仍禁止。
5. 完成后让控制脚本校验身份、哈希、执行状态和证据路径：

   ```bash
   node <skill-dir>/scripts/scoring-control.mjs mark-complete \
     --package-root <harness-root> \
     --task-id <task_id>
   ```

   `mark-complete` 只接受已经通过 `record-wait` 保存 `COMPLETED` 终态、且未超过 deadline 的 attempt；它会再次核对 execution 与 score 两份候选 SHA、要求受管站点和截图接收器进入可信终态、确认 `runtime-workspace` 已清理，并要求 `task_score.identity.model` 与执行回执的实际模型一致。门禁通过后才释放该题槽位并补入下一题；完成顺序可以与 manifest 不同。状态不明时先查询已有 `threadId`，不能重复创建评分任务。

最后一题通过 `mark-complete` 后，控制脚本会自动调用 preflight 已绑定的 `score-web-e2e/scripts/build_submission.mjs`，以临时文件和 SHA-256 状态原子发布根目录 `submission.json`。重复调用不会重复生成；进程在发布中断后可通过 `build-submission` 收口，已完成文件丢失或漂移时失败关闭。该步骤会执行最后一次双副本哈希复检并验证端口冲突审计；不得让单题评分任务访问 Harness 根目录或其他题目，管理任务也不得修改候选 workspace。

控制任务重启后执行：

```bash
node <skill-dir>/scripts/scoring-control.mjs resume \
  --package-root <harness-root>
```

严格执行返回的 `recommended_actions`；只有串行兼容控制器才读取 `recommended_action`。`WAIT_EXISTING_THREAD` 必须带已保存的 `after_cursor` 查询原 `threadId`；`BUILD_SUBMISSION` 或 `RETRY_SUBMISSION` 执行 `build-submission`；不得因为控制任务或 Desktop 重启而重新 `init`、覆盖 attempt 或直接创建新任务。Desktop 自身重启需要用户或独立外部 watchdog 重新拉起应用，控制任务不能在终止自身宿主后继续执行。
