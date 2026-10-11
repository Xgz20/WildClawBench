---
name: orchestrate-web-e2e
description: 编排桌面 Harness Web E2E 的执行结果交接、Codex Desktop 评分项目注册和可恢复并发评分任务；用于把已完成的 execution 包闭环为 submission，不负责单题做题或评分判断。
---

# 编排 Web E2E 桌面评测

本 Skill 是执行与评分之间的控制平面。`execute-web-e2e` 负责被评 Harness 做题，`score-web-e2e` 负责一个 Codex Desktop 任务内的一题评分；本 Skill 只负责确定性地交接工作空间、注册项目、创建和等待评分任务。

`0.3.27` 在创建评分线程并打开 Browser 后，要求控制任务使用公开 `navigate_to_codex_page` 显示该线程，直到其自身暖启动返回 READY 或明确失败再切换。隐藏线程的 `open_in_codex=queued` 不保证 webview 已挂载。仅 Browser 暖启动按单槽准备，正式评分仍为三槽并发；已有冻结 Prompt、候选、deadline 和重试预算不变。

`0.3.26` 的新评分状态支持 `init --score-skill-dir ABS`：在首次 Prompt 生成前冻结评分 Skill 的绝对路径、版本和元数据 SHA，并写入单题指令。评分前检须使用同一冻结 Skill；旧状态不补路径、不改写 Prompt，切换来源必须新建编排。

`0.3.25` 对新评分状态冻结默认裁判 `gpt-6.1-sol/high`，并在 `CREATE_THREAD` 动作中返回 `model` 与 `thinking`。已有状态保留原裁判和 Prompt；旧状态未冻结裁判时显示 `judge=null`，不能据此推断实际评分模型。

`0.3.24` 的项目注册器先悬停唯一关联的侧栏项目标题，显露添加入口，再进行普通点击；裁切的隐藏按钮区域不再强制点击。标题或入口歧义继续拒绝，冻结批次、候选与评分材料不变。

## 1. 生成独立评分工作空间

输入必须是整批执行成功后的 Harness 根目录。`execution-receipt.json` 必须存在、`integrity.valid=true`，每题必须同时为 `automation_phase=SUCCEEDED`、`execution_status=completed`，且 execution workspace 的当前 SHA 必须仍等于回执 `final_sha256`。安全超时或明确失败的完整终态回执只能用于审计与恢复，禁止进入评分。评分不能直接在 `execution/tasks/<task_id>` 中进行，也不能只复制若干网页文件。

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
  --score-skill-dir /absolute/installed/score-web-e2e \
  --score-port-base 4173 \
  --score-timeout-seconds 7200 \
  --max-retries 1
```

省略 `--task-id` 时使用 manifest 中的全部题目。新评分状态默认 `judge.model=gpt-6.1-sol`、`judge.reasoning_effort=high`，可用 `--judge-model` 和 `--judge-reasoning-effort` 显式覆盖；初始化后不可变，修改需新评分编排，恢复不会套用新的默认值。新批次默认 `score_slots=3`，最多 8 路；显式传 `--score-slots 1` 可回退串行。每题固定使用 `score_port_base + task_index` 的独占端口。旧 revision 3 状态恢复时继续保持原 `score_slots=1` 和旧 Prompt，不自动升级。评分槽位、端口基数、deadline（默认 7200 秒）和失败终态重试数（默认 1 次）在同一批次初始化后均不可变。状态和逐题评分 Prompt 保存到 `score/.orchestrate-web-e2e/`，不写入候选 `workspace/`。

macOS 的 Codex Desktop Browser 路由必须单独验收。`score_slots=3` 是本协议的生产默认值，执行与评分都必须按三路并发控制；它不代表当前 Desktop 会话一定已经提供三个 `iab` 实例。评分线程创建后，控制任务必须核对每个线程的 Browser 路由与 `metadata.codexSessionId`；少于三路时停止评分、保留 `evaluation_error`，并在新的控制会话中重新建立 Browser 路由。不得把路由缺失静默降级为串行，也不得把 `browsers=[]` 或 `Browser unavailable` 转成题目能力分数。

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

Windows 使用同一 CDP 契约和原生入口：

```bat
<skill-dir>\scripts\run-codex-project-registrar.cmd --probe --endpoint http://127.0.0.1:9230
```

多窗口探针应选择无路由查询参数的主窗口，不能因预热 Page 窗口的 ChatGPT 标题而优先选中它。候选同等或 URL 不唯一时失败关闭；可在确认主窗口后传 `--page-url <完整URL>` 精确指定。

每题注册前先调用 Codex Desktop 内置 `list_projects`。若规范化绝对路径已经存在，直接复用其 `projectId`；否则一次只注册一个目录：

```bash
bash <skill-dir>/scripts/run-codex-project-registrar.sh \
  --endpoint http://127.0.0.1:9230 \
  --project <harness-root>/score/tasks/<task_id> \
  --output <harness-root>/score/.orchestrate-web-e2e/registration/<task_id>.json
```

Windows 将上述入口替换为 `run-codex-project-registrar.cmd`；若无法从带目标 CDP 端口的进程唯一发现主程序，显式增加 `--app-path <ChatGPT.exe或Codex.exe>`。

默认路径必须通过可见 UI 和原生文件夹选择器完成。若目标 Desktop 版本的文件夹选择器在自动化会话中无法弹出，注册器应失败关闭；只有测试人员明确接受该版本私有接口风险时，才可增加 `--renderer-bridge`。该模式通过 Desktop 预加载 bridge 把已规范化的绝对目录交给内置项目管理器，仍须由 `list_projects` 精确回读，不能作为未记录的静默降级。升级 Desktop 后必须重新验证该模式。

macOS 原生文件夹选择器由随 Driver 分发的 Accessibility helper 处理；Windows 由随 Driver 分发的 PowerShell UI Automation helper 处理，并且只接受与已解析 Desktop 主程序路径完全一致的进程。两者都不属于 Computer Use。Windows 已完成真机探针、文件夹选择、绝对路径唯一回读、并发评分和 submission 恢复验收，属于生产已验证。注册后再次调用 `list_projects`，仍必须按规范化绝对路径唯一匹配，不能按重复的目录名猜测。然后记录项目：

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
   题目隔离限制不禁止读取已独立安装的 `score-web-e2e` Skill、参考文档、受管脚本及其运行依赖；生成的 Prompt 必须明确这项只读授权。不得访问其他项目、父目录或其他用例，所有本题写入仍限定在 `private-scoring/`，候选 `workspace/` 保持只读。
2. 确认当前题的 `preflight.status=PASSED` 后，调用 Desktop 内置 `create_thread`，目标为已记录的 `projectId`，环境固定为 `{type: "local"}`。新状态必须同时传入当前 `CREATE_THREAD` 动作的 `model` 与 `thinking`；不能沿用控制会话默认值。兼容恢复的旧状态未冻结裁判时，动作不返回这两个字段，继续原历史行为；用户指定新裁判时需新评分编排。
3. `create_thread` 返回后，控制任务必须马上调用 Desktop 内置 `open_in_codex`，目标为 `{type: "browser", url: "about:blank"}`，并传入刚返回的 `threadId`；随后调用公开 `navigate_to_codex_page`，同样只传刚返回的 `threadId`，显示该评分会话。返回 `queued` 只表示请求已入队，隐藏线程须实际显示后才能挂载 Browser webview。控制任务通过本题原始暖启动记录观察 READY 或明确失败，在此之前保持该评分会话显示，不进行其他项目注册或切换页面；记录导航工具真实结果，不把 `navigated=true` 视为健康证明。Browser 暖启动准备串行，已通过就绪检查的评分继续在后台并发，不降低冻结的 `score_slots`。0.3.23 新生成的 Prompt 要求在安装依赖、构建、启动站点及评分之前先完成 Browser 就绪检查；既有冻结 Prompt 不改写。

   就绪窗口为 180 秒，发现检查最多 3 次，窗口计时前先读取评分 Skill 和 helper 文档。在发现前仅一次调用公开 `mcp__cua_repl.js_reset`，记录实际起止时间及 `attempt_count=1`，复位属于180秒总窗口。随后首次 CUA js 调用遵循工具要求，只调用 `cua.getState()`（可以赋给变量）；返回后立即记录外部观察时间 `finished_at_upper_bound`，精确 `finished_at` 未知时保持 null。helper 只对首调用接受这一实际外部界限并标记时间精度，不用工具耗时反推精确结束时间。第一次为空时，评分线程可自己调用一次 `open_in_codex`（`about:blank`，省略 `threadId`）；后续空清单分别退避 2 秒和 5 秒再发现，全部检查仍受总窗口约束。发现唯一属于本线程的 `iab` 后，或三次发现仍为空但窗口尚未耗尽时，仅一次用公开 `cua.createBrowserTab("iab", "about:blank", {visible:false})` 实际初始化，再核验本线程 `metadata.codexSessionId`、创建的唯一 tab 和实际 AX 页面。空清单不证明创建不可用；外国会话、重复 iab、创建失败或窗口耗尽必须停止。禁止父会话 Browser、Chrome、headless、替代运行时及私有管道。

   评分线程将原始观察保存到本题 `private-scoring/evidence/browser-readiness-input.json`，字段为 `task_id`、实际 `thread_id`、`started_at`、可选 `reset`（`attempt_count/started_at/finished_at`）、`discoveries`（每次 `started_at/finished_at/state`，首调用可为 `finished_at=null/finished_at_upper_bound`）、`creation`（`attempt_count=1/success/tab_id/started_at/finished_at`）、`verification`（`finished_at/state`）及 `readback`（`finished_at/url/ax_state`，可使用创建返回的实际 AX 状态）。时间使用实际 ISO 时间；未发生的创建或复查省略，不能补造。生成的 Prompt 明确允许读取和运行本次独立安装的编排 helper：

   ```bash
   node <installed-orchestrate-web-e2e-dir>/scripts/browser-readiness.mjs \
     --task-root . --thread-id <actual-thread-id> \
     --input private-scoring/evidence/browser-readiness-input.json
   ```

   helper 原子写入 `browser-readiness.json`，返回 `RETRY_DISCOVERY`、`CHECKING`、`READY` 或 `BLOCKED`；它只核验记录，不操作 Browser。只有 `READY` 才按 `score-web-e2e` 启动受管站点，并让同一 Browser 打开本题固定评分端口的实际入口。`BLOCKED`、校验错误或实际工具失败按评分 Skill 生成 `evaluation_error` 并结束当前 attempt。180 秒是外层有界预热，不修改 Codex 内置 5 秒信息等待，不增加评分 attempt 或恢复预算，也不要求修改 Desktop 安装文件。最终健康证明仍须在 60 秒内使用，不能用过期记录启动站点。
4. 把返回的 `threadId`、`hostId` 记录到状态：

   ```bash
   node <skill-dir>/scripts/scoring-control.mjs record-thread \
     --package-root <harness-root> \
     --task-id <task_id> \
     --thread-id <thread_id> \
     --host-id <host_id>
   ```

5. 把全部活动评分任务组成一次 `wait_threads` 调用；需要诊断时再用 `read_thread`。每个目标都从对应 `recommended_actions` 项读取 `thread_id`、`host_id`、`after_cursor` 和 `next_wait_sequence`，返回后立即逐题串行持久化 poll 的 cursor 与状态：

   ```bash
   node <skill-dir>/scripts/scoring-control.mjs record-wait \
     --package-root <harness-root> \
     --task-id <task_id> \
     --wait-sequence <next_wait_sequence> \
     --wait-cursor <poll.cursor> \
     --wait-status <RUNNING|POLL_TIMEOUT|NEEDS_ATTENTION|COMPLETED|FAILED|CANCELLED|INTERRUPTED> \
     [--finished-at <Desktop 返回的终态完成时间>]
   ```

   `POLL_TIMEOUT` 只表示这次 `wait_threads` 没等到变化，不是评分超时；控制面只有到达该 attempt 的独立 `deadline_at` 后才执行 `mark-timeout`。Desktop 返回已结束的评分线程时，应把其 `completedAt` 转成 `--finished-at` 一并记录；控制面用这个原生终态时间判断 deadline，不能把控制器晚到的轮询时间当成评分完成时间。某题失败后继续等待已经活动的其他题，但暂停补充新题，先按动作处理失败题。超时后原 `threadId` 状态仍不明时必须继续查询，禁止立即创建第二个任务。只有原任务已记录 `COMPLETED`、`FAILED`、`CANCELLED` 或 `INTERRUPTED` 终态，才可执行 `prepare-retry --retry-reason <说明>`，重新通过该题 preflight 后创建下一 attempt。

   推荐将 `wait_threads` 返回的当前题完整 poll 原样保存为 JSON，然后使用原生终态入口；`completedAt` 按 Unix 秒自动转换，无需手工换算 UTC。该入口校验 thread/host、终态与时间，复制原始观察到控制目录并记录 SHA-256，后续恢复会复核；不得与手工 cursor/status/time 参数混用：

   ```bash
   node <skill-dir>/scripts/scoring-control.mjs record-wait \
     --package-root <harness-root> --task-id <task_id> \
     --wait-sequence <next_wait_sequence> --terminal-observation <absolute-poll.json>
   ```

   当 `wait_threads` 明确无法解析 host，但 `read_thread` 可访问同一线程时，0.3.16 允许将该工具原样返回的 JSON 通过同一 `--terminal-observation` 入口留存。必须是 Codex 同 thread/host、`page.order=newest_first`、`limit=1`、单个最新终态 turn，且线程为 idle；完成时间仍取原生 `completedAt`。该回执使用真实 turn ID 作终态投递键，不能把它当作 wait_threads 分页 cursor；仍活动、旧页、未知终态或身份不匹配均拒绝。不得手工拼装 Desktop poll、补完成时间或绕过哈希门禁。

   已到 deadline 但仍活动的原评分线程可以记为 `TIMED_OUT`，同时继续等待其真实终态；该标记不会停止线程，也不释放槽位。不得因观察超时再派发同题。

   `prepare-retry` 不删除失败现场。它先复核候选与评分初始输入，并要求受管评分服务和截图接收器已经进入可信终态；存在无 `runtime-state.json` 的运行时副本、仍为 `RUNNING` 的服务/接收器或身份不匹配的状态文件时一律禁止归档。门禁通过后，把旧 `private-scoring/` 原子迁入 `score/.orchestrate-web-e2e/attempts/<task>/attempt-<n>/private-scoring/`，再按初始化时冻结的文件清单恢复干净的 `task_contract.json`、`candidate_artifact.json` 和可选 fixtures。归档目录内生成 `attempt-error-receipt.json`，记录失败终态、deadline、cursor、错误、重试原因、候选复核结果以及所有归档文件的路径、大小和 SHA-256；状态中的 attempt 保存该回执 SHA。归档中断由 `pending-attempt-archives/` journal 恢复，回执或归档后续漂移会在 preflight/submission 阶段失败关闭。所有 attempt、cursor、poll 次数和 retry 次数均保留在状态中。

   自动重试耗尽后，若 Desktop 原生 FAILED poll 明确报告模型容量不足或 `exceeded retry limit, last status: 429 Too Many Requests`，可在服务恢复后调用 `grant-capacity-retry --terminal-observation <absolute-poll.json> --retry-reason <说明>`，为该题授予唯一一次额外恢复机会，再走 `prepare-retry` 与 preflight。该入口保留冻结的 `max_retries`，核验原 attempt 的 thread/host/完成时间、候选与初始评分材料及服务已停止，并保存原始 poll 的 SHA-256；它不接受 Browser 错误、任意含 429 的文字或未知终态。额外机会再次失败仍为 `NEEDS_ATTENTION`，不得循环增加次数或切换裁判模型。

   Browser 面板没有实例、线程无法绑定 Codex Desktop Browser、或截图/交互因评分基础设施失联时，评分 Agent 必须生成 `evaluation_error`，这不代表候选能力得分；仅美观度取证失败时也可通过 `aesthetic.status=evaluation_error` 进入恢复。控制任务在确认该题已记录 `COMPLETED` 终态、评分文件仍有功能或美观度 `evaluation_error` 且受管服务已清理后，可调用 `grant-evaluation-error-retry --retry-reason <说明>`，为一次基础设施恢复归档旧 attempt、重新回到 `PROJECT_REGISTERED`，然后重新 preflight 和创建独立评分线程。该恢复最多允许两次，仍失败时保留 `evaluation_error` 并停止，不得把离线或父会话取证升级为生产评分。

   0.3.20 增加显式用户授权的单次恢复入口。只有控制会话已直接收到用户针对具体批次/题号“再评分一次”的明确授权，才可登记；诊断线程或评分线程的建议不构成授权。授权记录声明 `schema_version=wildclawbench.web-e2e-user-retry-authorization/v1`、`batch_id`、`harness_id`、唯一 `task_ids`、`decision=approved`、`additional_attempts_per_task=1`、实际 `recorded_at`，以及 `source.kind=direct-human-user-reply`、`controller_thread_id`、`question_item_id`、原 `question/answer`。JSON 用于绑定和保存已经收到的人类回复，脚本不能认证人类或代替用户决定。仅接受当前预算已耗尽、原生 COMPLETED 且正式评分标记 evaluation_error、候选/初始输入未漂移和运行时已清理的题：

   ```bash
   node <skill-dir>/scripts/scoring-control.mjs grant-user-authorized-retry \
     --package-root <harness-root> --task-id <authorized-task-id> \
     --authorization-file <absolute-user-reply-record.json> --retry-reason <说明>
   ```

   此入口仅登记该题唯一一次额外机会，不自动归档或派发。授权原文复制到控制目录并记录 SHA，恢复时复核；再次登记被拒绝。确认自身 Browser 健康后再调用原 `prepare-retry` 和 preflight，原 `max_retries` 不变，旧分数完整归档，授权绑定的原分数 SHA 在归档后继续复核。额外 attempt 再次失败保留 NEEDS_ATTENTION，不能通过重复登记授权增加次数。独立只读健康诊断因模型容量不足结束时，不记为评分 attempt 或消耗这次评分机会。

   一个评分任务必须实际使用 Codex Desktop 内置 Browser，并由 `$score-web-e2e` 生成 `private-scoring/task_score.json`。评分任务只能写 `private-scoring/`；候选 `workspace/` 是只读输入。站点端口冲突时优先改启动参数或环境变量；只有受管启动日志已证明冲突且端口无法外部覆盖时，评分 Skill 才能通过 `managed_runtime.mjs port-override` 修改运行时副本中的唯一数字端口并落审计。execution/score 候选原件仍不可修改，其他源码调整仍禁止。
5. 完成后让控制脚本校验身份、哈希、执行状态和证据路径：

   ```bash
   node <skill-dir>/scripts/scoring-control.mjs mark-complete \
     --package-root <harness-root> \
     --task-id <task_id>
   ```

   `mark-complete` 只接受已经通过 `record-wait` 保存 `COMPLETED` 终态、且未超过 deadline 的 attempt；它会再次核对 execution 与 score 两份候选 SHA、要求受管站点和截图接收器进入可信终态、确认 `runtime-workspace` 已清理，并要求 `task_score.identity.model` 与执行回执的实际模型一致。0.3.18 保存评分结果状态与文件 SHA：功能或美观度为 `evaluation_error` 时，整批返回 `NEEDS_ATTENTION/SCORING_INFRASTRUCTURE_ERROR`，暂停新题注册/创建建议，`record-thread` 也拒绝补位；已活动任务仍继续等待、校验和收口。普通候选失分不会触发此保护。确认基础设施恢复后，仅按原有预算归档重试，旧结果随 attempt 保留；状态不明时不能重复创建。

最后一题通过 `mark-complete` 后，控制脚本会自动调用 preflight 已绑定的 `score-web-e2e/scripts/build_submission.mjs`，以临时文件和 SHA-256 状态原子发布根目录 `submission.json`。重复调用不会重复生成；进程在发布中断后可通过 `build-submission` 收口，已完成文件丢失或漂移时失败关闭。该步骤会执行最后一次双副本哈希复检并验证端口冲突审计；不得让单题评分任务访问 Harness 根目录或其他题目，管理任务也不得修改候选 workspace。

包含 `evaluation_error` 的 submission 仍可导出用于审计，但整批保持 `NEEDS_ATTENTION`，不返回 `DONE`，不代表生产验收通过。旧状态缺少评分结果字段时，只读 `status` 在内存中核验并分类已有分数，不重写状态、冻结 Prompt、评分文件或预算；新就绪流程仅用于新生成的 Prompt。

控制任务重启后执行：

```bash
node <skill-dir>/scripts/scoring-control.mjs resume \
  --package-root <harness-root>
```

严格执行返回的 `recommended_actions`；只有串行兼容控制器才读取 `recommended_action`。`WAIT_EXISTING_THREAD` 必须带已保存的 `after_cursor` 查询原 `threadId`；`BUILD_SUBMISSION` 或 `RETRY_SUBMISSION` 执行 `build-submission`；不得因为控制任务或 Desktop 重启而重新 `init`、覆盖 attempt 或直接创建新任务。Desktop 自身重启需要用户或独立外部 watchdog 重新拉起应用，控制任务不能在终止自身宿主后继续执行。


## Desktop 重启后的同线程接续

0.3.21 起，用户重启 Desktop 并要求继续尚未完成的评分时，可将 `wait_threads` 原样返回的 INTERRUPTED poll 保存后调用 `record-thread-interruption --terminal-observation <file>`。仅接受当前 SCORING、未记最终终态且原 deadline 未过的同 thread/host；中断 turn 单独留存于 thread-interruptions 并绑定 SHA，原 attempt、评分槽、retry_count、deadline 保持。控制器在消息派发前查询原线程；仍活动时只等待，明确中断后向原线程发送一次继续指令，不创建新线程。新 turn 最终完成时仍走 record-wait/mark-complete，所有历史中断证据持续复核。普通 FAILED/CANCELLED、迟到结果或已收口题不能通过此入口续评。宿主重启后的旧 Browser 健康证明需要另存原件并重核，本题服务和接收器按受管状态恢复。

0.3.22 起，客户端升级可以通过显式 `record-desktop-upgrade --desktop-probe <registrar-probe.json> --project-observation <list-projects.json> --upgrade-reason <说明>` 记录恢复。probe 必须包含真实身份已验证的 Desktop 版本，原生 list_projects 必须按已登记的 projectId/host/规范化绝对路径逐一唯一回读。大清单可保留原件并提供带原始 SHA、尺寸和来源的精确目录子集，项目身份字段不能改写。原项目登记版本作为快照留存，观察文件复制留 SHA；当前 registry 及未完成项目更新为回读版本，待评分题必须重新前检，已完成评分及其旧登记保持。该入口不修改候选、模型、Prompt、旧分数或预算；普通 record-project/preflight 继续拒绝未经记录的版本混用。升级后的 Browser/服务兼容性仍需真实验证，显式升级记录本身不证明生产通过。
