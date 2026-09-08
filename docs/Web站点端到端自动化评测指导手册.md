# Web 站点端到端自动化评测指导手册

本文面向评测管理员、Harness 执行人员和评分人员，说明如何使用 Codex 中的 Web E2E Skills 完成“准备题目 → Harness 自动做题 → Codex Desktop 自动评分 → 汇总报告”。如果只是第一次跑通流程，直接按第 1 节操作；后续章节用于理解参数、恢复中断和排查失败。

当前已经实现的自动化范围是：

- 全局组合：`run-web-e2e` 只启用 Prompt 明确提到的准备、执行、评分、打包回传、收集和报告阶段；`admin`、`worker`、`full-local` 只是可选预设；
- 被评 Harness：WorkBuddy，采用 Electron CDP/Playwright 串行操作 UI、后台并发执行；
- 评分 Harness：Codex Desktop，每题建立独立项目和独立任务，使用桌面内置 Browser；
- 执行并发：新队列默认 `ui_slots=1`、`run_slots=3`，可显式设为 1，最多 8；
- 评分并发：新批次默认 `score_slots=3`，可显式设置为 1 串行，最多 8；
- AstronStudio、QwenWork、DoubaoWork 尚未完成专用 Driver，不能把 WorkBuddy 的验证结论直接套用到这些客户端。

基础串行链路已在批次 `web-e2e-20260907-124800` 完成 5 个 L1 真实用例的 WorkBuddy 执行、Codex Desktop 评分和 submission 闭环。WorkBuddy 5.5.3/Driver 1.6.1 在未指定模型时连续五题读回 `current/xopglm52`，四次自动切题后队列进入 `COMPLETED`；Codex Desktop 26.901.51231 为五题分别创建项目、任务和 Browser 证据，评分为 55、65、67、77、91，编排状态最终为 `COMPLETED`。该批次评分使用 `score-web-e2e 4.3.0`。随后批次 `web-e2e-20260907-192642` 用一个 L1 完成 `score-web-e2e 4.4.0` 真实 Desktop 截图接收 smoke，6 张 Browser 截图均由标准一次性接收器保存并通过终态、签名和 SHA-256 门禁，submission 正常生成。同日又使用旧五题批次的只读隔离副本完成 `start-static --root square-circle-intersection` 真实 Desktop smoke，并验证 Desktop 整个进程退出、重新打开后仍能依据磁盘状态跟踪原评分任务和自动生成 submission；这些重复评分只用于运行时验证，不计入正式成绩。评分控制面现已实现并实测默认 3 槽调度：同一 Codex Desktop 的三个独立评分任务同时使用内置 Browser，分别绑定 4173、4174、4175，真实乱序完成并只生成一次 submission；候选、端口、截图和运行时均未交叉。WorkBuddy Driver/Worker 1.7.0 已实现默认 3、最多 8 个后台任务的控制面，自动化回归为 50/50，并使用三个 L1 完成真实 `run_slots=3` smoke：三题在约 21 秒内全部投递，拥有不同 conversation ID 和共同后台运行窗口，最终乱序完成，三题 Prompt 都只发送一次，执行回执有效。首次换机器、升级 WorkBuddy/Codex Desktop/Skill、切换模型或启用并发后，仍应先做小批次 smoke；需要严格对比串并行稳定性时，继续使用同一候选做重复运行抽查。

全局组合链路已在真实批次 `web-e2e-20260908-123216` 完成 5 个开源 ArtifactsBench L1 用例。WorkBuddy 使用 `xopglm52`、`full-access` 和默认三槽执行，首批三题投递后，ab378 完成约 4.5 秒后补入 ab1468，ab241 完成约 4.4 秒后补入 ab1775，5/5 执行成功且回执完整。Codex Desktop 26.901.51231 使用 `score-web-e2e 4.4.0` 完成五个独立 Browser 评分，得分为 61、79、57、77、88，平均 72.40；第四题在槽位释放后补入，第五题在控制任务交接恢复后补入。最终 submission、完整 Harness 回传 ZIP、外部 SHA-256 回执、安全导入、JSON、Markdown 和三 Sheet Excel 均通过。第五题的恢复补位证明状态可接管，不等同于控制任务不中断时的即时补位时延。

文中的 `<...>` 都需要替换为实际路径或 ID。示例以 macOS、WorkBuddy 和三个 L1 用例为例；第 7.1 节另列出已经完成的五题真实基线和 4.4.0 单题 smoke。

## 1. 最快跑通一次完整评测

### 1.0 推荐：让 `run-web-e2e` 按 Prompt 组合全流程

完成 1.1 的客户端准备后，在同一台机器调试时可直接复制下面的 Prompt。无需额外指定 `admin` 或 `worker`；明确列出的阶段就是本次运行计划，未列出的阶段不会执行。

```text
请使用 $run-web-e2e 完成下面 Web E2E 批次的准备、执行、评分、打包回传、收集和报告。

用例：
- 07_Website_Generation_task_ab241_menu_switch_gui_framework
- 07_Website_Generation_task_ab378_square_circle_intersection
- 07_Website_Generation_task_ab699_css_formatter_tool
- 07_Website_Generation_task_ab1468_mall_register_login_page
- 07_Website_Generation_task_ab1775_pi_derivation_demo

Harness：workbuddy
指标 Profile：auto
输出目录：/Users/tester/WebE2E
报告模型映射：workbuddy=xopglm52
报告推理强度映射：workbuddy=客户端默认值
WorkBuddy 权限：full-access
WorkBuddy 执行并发：默认 3
Codex Desktop 评分并发：默认 3
Codex Desktop CDP：http://127.0.0.1:9230

执行阶段显式选择 xopglm52，并回读实际模型；不要操作推理强度。
执行完成后必须验证 execution-receipt.json，再合入同批 scoring ZIP。
每题使用独立 Codex Desktop 项目、任务、Browser 和端口；不得修改 execution 或 score 候选 workspace。
评分完成后生成 submission，导出完整 Harness 回传 ZIP 和外部回执，再按离线导入流程收集。
最后生成并校验 JSON、Markdown 和 Excel 三种报告。
中断后读取磁盘状态继续，不要重新初始化或重复创建状态不明的任务。
```

如果测试人员已经在 WorkBuddy 中配置好模型，删掉“显式选择 xopglm52”一句，改为“省略模型参数，保持并回读当前模型”。跨机器时管理员只写“准备”，worker 只写“执行、评分、打包回传”，管理员收到 ZIP 后再写“收集、报告”；这些都是同一个 Skill 的合法动态组合。

### 1.1 跑批前只做一次的准备

执行机器需要：

1. 安装并启用 `execute-web-e2e` Skill。
2. 打开 WorkBuddy，在客户端中把默认模型设为 `xopglm52`，选择本轮要测的推理强度，并开启“允许完全访问”。
3. 确认当前没有需要保留的运行中任务。
4. 在执行 Skill 的 WorkBuddy Driver 目录运行一次 `npm ci`。

评分机器需要：

1. 安装并启用 `orchestrate-web-e2e` 和 `score-web-e2e`。
2. 使用带桌面 Browser 的 Codex Desktop。
3. 确认没有需要保留的运行中 Codex 任务，完全退出 ChatGPT/Codex Desktop，再在 macOS 终端启动仅本机可访问的 CDP 端口：

   ```bash
   open -na "ChatGPT" --args \
     --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9230
   ```

   评分控制任务必须在这次启动后新建；控制任务运行期间不得退出或重启承载它的 Desktop。
4. 在 `orchestrate-web-e2e/drivers/codex-desktop` 目录运行一次 `npm ci`。

同一台电脑可以同时承担执行和评分；多电脑时按第 8 节传递文件。

### 1.2 生成评测包

在 WildClawBench 工程中打开一个 Codex 任务，复制下面的内容，把输出目录替换成实际路径：

```text
请使用 $prepare-web-e2e-workspaces 生成一个 Web 站点端到端评测批次。

用例：
- 07_Website_Generation_task_ab078_svg_smartphone_speech_bubbles
- 07_Website_Generation_task_ab097_svg_download_animation
- 07_Website_Generation_task_ab378_square_circle_intersection

Harness：workbuddy
指标 Profile：auto
报告模型映射：workbuddy=xopglm52
报告推理强度映射：workbuddy=客户端默认值
输出目录：/Users/tester/WebE2E

使用自动生成的时间戳 batch_id，不要执行题目或评分。
```

成功后会得到类似目录：

```text
/Users/tester/WebE2E/web-e2e-20260907-120000/
├── packages/
│   ├── web-e2e-20260907-120000__workbuddy__execution.zip
│   ├── web-e2e-20260907-120000__workbuddy__scoring.zip
│   ├── web-e2e-20260907-120000__run-web-e2e-skill.zip
│   ├── web-e2e-20260907-120000__execute-web-e2e-skill.zip
│   ├── web-e2e-20260907-120000__score-web-e2e-skill.zip
│   ├── web-e2e-20260907-120000__orchestrate-web-e2e-skill.zip
│   ├── web-e2e-20260907-120000__report-web-e2e-skill.zip
│   └── skills-manifest.json
└── web-e2e-20260907-120000__report-config.yaml
```

解压 execution ZIP，得到 Harness 根目录：

```text
/Users/tester/WebE2E/web-e2e-20260907-120000__workbuddy/
```

### 1.3 让 WorkBuddy 自动并发做完三题

在执行机器的 Codex 控制任务中复制：

```text
请使用 $execute-web-e2e 执行下面 WorkBuddy 包中 manifest.json 的全部用例：

/Users/tester/WebE2E/web-e2e-20260907-120000__workbuddy

要求：
- run-id 使用 workbuddy-20260907-120000；
- 按 manifest 顺序执行全部题目；
- 后台并发使用默认 3 路；WorkBuddy 前台 UI 仍必须单路操作；
- 不指定模型，保持并回读 WorkBuddy 当前模型；
- 不操作推理强度，保持 WorkBuddy 当前设置；
- 权限模式使用 full-access；
- 第一题前自动重启 WorkBuddy；
- 单题失败或状态不明时停止，不跳过失败继续；
- 完成后检查 execution-receipt.json 的 integrity.valid 必须为 true。
```

这里故意不写模型参数。Driver 会读取 WorkBuddy 当前显示的模型，不会打开模型下拉框，也不会改变推理强度。如果希望覆盖客户端当前模型，把第三条改为：

```text
- 显式指定模型 xopglm52，选择后必须回读一致；
```

全部完成后，Harness 根目录应存在：

```text
execution-receipt.json
```

至少检查：

- `integrity.valid` 为 `true`；
- 顶层 `model.id` 非空；
- 每题 `model_selection.actual_model` 相同；
- 未指定模型时，每题 `model_selection.mode` 为 `current`、`requested_model` 为 `null`；
- 每题 `execution_status` 已进入终态。

### 1.4 自动准备并完成 Codex Desktop 评分

先把同批次 scoring ZIP 放到 Harness 根目录或其同级目录。然后在评分机器的 Codex 控制任务中复制：

```text
请使用 $orchestrate-web-e2e 闭环下面 WorkBuddy 执行包的评分：

Harness 根目录：
/Users/tester/WebE2E/web-e2e-20260907-120000__workbuddy

scoring ZIP：
/Users/tester/WebE2E/web-e2e-20260907-120000__workbuddy__scoring.zip

Codex Desktop CDP：
http://127.0.0.1:9230

要求：
1. 先校验 execution-receipt.json 并生成独立 score 工作空间；
2. 初始化全部题目的评分状态，使用默认 score_slots=3，并为每题分配独立端口；若本机尚未做过并发 smoke，则显式使用 --score-slots 1；
3. 每题注册 score/tasks/<task_id> 为独立 Codex Desktop 项目，并按绝对路径回读 projectId；
4. 每题创建独立 Desktop 评分任务，必须使用 $score-web-e2e 和桌面内置 Browser；
5. 一次 wait_threads 同时等待全部活动评分任务；每题返回后立即分别保存 cursor 和状态，任一题记录 COMPLETED 且通过 mark-complete 后立即补入下一题；
6. 不覆盖评分模型或推理强度，沿用评分 Codex Desktop 的默认设置；
7. 控制任务重启时从磁盘状态 resume 并查询原 threadId，禁止重复创建状态不明的评分任务；
8. 最后一题通过 mark-complete 后确认 submission.json 已自动生成；失败时按 recommended_actions 收口；
9. execution 和 score 中的候选 workspace 均不得修改。
```

默认先使用可见 UI 注册项目。如果这台评分机当前版本的原生文件夹选择器无法工作，只有在该 Desktop 版本已经完成过 renderer bridge 验证、测试人员明确接受其版本敏感风险后，才在请求中补充：

```text
本机已接受当前 Codex Desktop 版本的 renderer bridge 风险；允许显式使用 renderer-bridge，并在 preflight 中携带 allow-renderer-bridge。不得静默降级。
```

成功后确认 Harness 根目录存在 `submission.json`，然后用系统 ZIP 工具压缩整个 Harness 根目录。不要只压缩 `score/` 或单独发送 `submission.json`。

### 1.5 生成汇总报告

在安装了 `report-web-e2e` 的 Codex 任务中复制：

```text
请使用 $report-web-e2e 汇总 Web 站点端到端评测结果。

回传包：
- /Users/tester/WebE2E/returns/web-e2e-20260907-120000__workbuddy.zip

报告配置：
/Users/tester/WebE2E/web-e2e-20260907-120000/web-e2e-20260907-120000__report-config.yaml

输出目录：
/Users/tester/WebE2E/reports/web-e2e-20260907-120000

请生成并校验 Markdown、JSON 和 Excel 三种报告产物。
```

最终应得到：

```text
Web站点端到端评测领导版.md
web_e2e_report_data.json
Web站点端到端评测报告.xlsx
```

## 2. 六个阶段和对应 Skill

| 阶段 | Skill | 输入 | 主要输出 |
| --- | --- | --- | --- |
| 准备 | `prepare-web-e2e-workspaces` | 用例 ID、Harness、输出目录、报告配置 | execution/scoring ZIP、五个 Skill ZIP、Skill manifest、报告配置 |
| 执行 | `execute-web-e2e` | 解压后的 execution Harness 根目录 | 候选产物、自动化状态、`execution_record.json`、`execution-receipt.json` |
| 评分 | `orchestrate-web-e2e` + `score-web-e2e` | 已完成执行包、scoring ZIP、Codex Desktop | 独立评分项目与任务、浏览器证据、`task_score.json`、`submission.json` |
| 打包回传 | `run-web-e2e` | 有效 `submission.json` 和完整 Harness 根目录 | return ZIP、外部 `return-receipt.json` |
| 收集 | `run-web-e2e` | return ZIP 和对应外部回执 | 校验后的 `returns/<harness>/`、导入回执 |
| 报告 | `report-web-e2e` | 一个或多个完整回传包、报告配置 | Markdown、JSON、Excel |

`execute-web-e2e` 负责被评 Harness 做题，不参与评分；`score-web-e2e` 每次只评一题；`orchestrate-web-e2e` 负责交接、注册项目和调度评分任务，不自行判断得分。

## 3. 模型和推理强度规则

### 3.1 模型优先级

WorkBuddy Driver 只有两个模型模式：

| 调用方式 | 行为 | 回执记录 |
| --- | --- | --- |
| 显式传入 `--model <UI 精确显示名>` | 选择目标模型并回读；不一致则停止 | `mode=explicit`、请求模型、实际模型 |
| 省略 `--model` | 保持当前模型，只回读；不展开模型下拉框 | `mode=current`、`requested_model=null`、实际模型 |

省略模型不再等于“均衡”。它表示测试人员已经在 Harness 中配置好模型，自动化不得覆盖。

无论哪种模式：

- 发送 Prompt 前都必须取得非空实际模型；
- 同一队列所有题的实际模型必须一致；
- 执行过程中不要人工切换模型；
- 实际模型会写入执行记录、执行回执、评分冻结记录、单题评分和 submission；
- 已完成批次的模型身份不能通过编辑 JSON 更换，切换模型必须新建时间戳批次并重新执行。

### 3.2 推理强度

执行自动化不选择、不回读、不校验被评 Harness 的推理强度。原因是不同客户端的设置入口和模型联动差异较大，Playwright 控制容易产生静默误配。

生产跑批前由测试人员手工设置推理强度；准备阶段的 `--reasoning-effort` 或 `--reasoning-effort-map` 只写入报告配置，是用户声明值，不是 UI 自动取证结果。

### 3.3 建议的生产配置顺序

1. 打开被评 Harness，配置模型。
2. 配置该模型对应的推理强度。
3. 配置权限模式。
4. 关闭无关会话或确认没有运行中任务。
5. 再让控制 Agent 调用 `execute-web-e2e`。

如果要确保本轮使用指定模型，在执行请求中显式给出模型；如果某个 Harness 的模型/推理强度组合只能由人工稳定配置，则省略模型参数，让 Driver 保持当前设置并记录实际模型。

## 4. 准备评测包

### 4.1 命令行等价示例

在仓库根目录运行：

```bash
.venv/bin/python .agents/skills/prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py \
  --task-id 07_Website_Generation_task_ab078_svg_smartphone_speech_bubbles \
  --task-id 07_Website_Generation_task_ab097_svg_download_animation \
  --task-id 07_Website_Generation_task_ab378_square_circle_intersection \
  --harness workbuddy \
  --metric-profile auto \
  --model-map workbuddy=xopglm52 \
  --reasoning-effort-map workbuddy=客户端默认值 \
  --output-dir /Users/tester/WebE2E
```

`--model-map` 在这里用于生成报告配置，不会要求 WorkBuddy Driver 自动切换模型。执行阶段是否切换，只由调用 `execute-web-e2e` 时有没有显式提供模型决定。

### 4.2 不得进入 execution 包的内容

执行工作空间只能包含公开 Prompt 和初始候选 Workspace，不能包含：

- Ground Truth；
- Expected Behavior；
- Rubric、checker 或评分脚本；
- 题目 `eval/`、`gt/`；
- 其他题目的 Prompt；
- 真实账号、Cookie、API Key、私钥或生产数据。

执行时选择 `execution/tasks/<task_id>/`，不要选择其中的 `workspace/`，也不要选择整个 Harness 根目录。

## 5. WorkBuddy 自动执行

### 5.1 一次性安装依赖与只读探测

```bash
cd <execute-web-e2e-skill-dir>/drivers/workbuddy
npm ci

bash <execute-web-e2e-skill-dir>/scripts/run-workbuddy.sh --probe
```

`--probe` 不会新建任务。若 WorkBuddy 当前停在历史会话页，可能返回 `workspace-picker-not-visible`；先切到未发送的新任务页再探测。

### 5.2 直接运行批次

沿用客户端当前模型：

```bash
bash <execute-web-e2e-skill-dir>/scripts/run-workbuddy-batch.sh \
  /Users/tester/WebE2E/web-e2e-20260907-120000__workbuddy \
  --run-id workbuddy-20260907-120000 \
  --task-id 07_Website_Generation_task_ab078_svg_smartphone_speech_bubbles \
  --task-id 07_Website_Generation_task_ab097_svg_download_animation \
  --task-id 07_Website_Generation_task_ab378_square_circle_intersection \
  --run-slots 3 \
  --permission-mode full-access \
  --restart-app-first
```

显式覆盖模型只需增加：

```bash
--model xopglm52
```

模型参数使用客户端下拉框中的精确显示名。同一个 `run-id` 恢复时，任务顺序、模型模式、显式模型值、权限模式和并发数都不能改变。新队列省略 `--run-slots` 时默认 3；显式 `--run-slots 1` 可回退串行，最大为 8。没有并发字段的旧队列恢复时仍为 1，不会自动升级。

### 5.3 如何判断一题完成并补入下一题

Worker 不用固定等待时间猜测完成。新题发送 Prompt 并捕获稳定 conversation ID 后退出前台观察，WorkBuddy 在后台继续执行；Worker 使用唯一 UI Driver 轮流打开活动 conversation 做一次性观察。它优先读取 WorkBuddy 本地 session 状态，并用 DOM 明确终态和实质最终回复补充判断。只有以下内容一致时才释放该题槽位并补入下一题：

- WorkBuddy 会话已经明确结束；
- `automation_state.json` 已进入可信终态；
- `execution_record.json` 状态和模型一致；
- 候选 Workspace 已记录终态哈希；
- 超时题还必须有停止确认和 Workspace 静默证据。

网站没有生成成功仍可能是 Harness 的正常完成结果，后续由评分阶段判定；自动化不能因为产物质量低而替模型继续修改。

### 5.4 中断恢复

控制 Agent 或 Worker 中断后，使用原来的 `run-id`、任务顺序和参数，并增加 `--resume`：

```bash
bash <execute-web-e2e-skill-dir>/scripts/run-workbuddy-batch.sh \
  /Users/tester/WebE2E/web-e2e-20260907-120000__workbuddy \
  --run-id workbuddy-20260907-120000 \
  --task-id 07_Website_Generation_task_ab078_svg_smartphone_speech_bubbles \
  --task-id 07_Website_Generation_task_ab097_svg_download_animation \
  --task-id 07_Website_Generation_task_ab378_square_circle_intersection \
  --run-slots 3 \
  --permission-mode full-access \
  --resume
```

如果 WorkBuddy 客户端也崩溃，增加 `--restart-app-on-resume`。Worker 只重启客户端一次，再串行恢复所有活动 conversation。只有已捕获稳定 conversation ID 时才会恢复原会话；无法唯一确认时停在 `NEEDS_ATTENTION`，不会创建新任务或重复发送 Prompt。

发送前自动化失败、候选 Workspace 完全没有变化时，修复原因后可以在恢复命令中增加 `--retry-pre-send-failure`。旧 attempt 会被归档，发送后失败不能用该参数重试。

### 5.5 失败处理

- `NEEDS_ATTENTION`：状态不明、未知授权或无法安全恢复，需要人工检查；它不是完成。
- `INFRA_FAILED`：发送前控制失败或已确认的基础设施错误，默认停止队列。
- `TIMEOUT`：只有 WorkBuddy 已停止且 Workspace 静默时才是安全终态。
- 默认不要使用 `--continue-on-terminal-failure`；只有明确需要验证失败隔离或接受失败题继续时才使用。

### 5.6 执行并发边界

WorkBuddy 新队列默认记录 `ui_slots=1`、`run_slots=3`。`run_slots` 可显式设置为 1 到 8；省略时新队列使用 3，恢复已有队列时沿用首次冻结值，没有该字段的旧队列按 1 恢复。并发期间始终只有一个 Driver 操作 WorkBuddy：串行新建项目、设置模型/权限、发送 Prompt、切换会话和处理授权；不能启动多个 Playwright 进程同时点击客户端。

Prompt 发送并捕获稳定 conversation ID 后，任务留在 WorkBuddy 后台运行，Driver 退出本次观察。Worker 轮流恢复各活动 conversation；任一题可信终态后释放槽位并立即补入下一题。出现未知授权或默认失败时暂停补题，但继续收口已经投递的其他活动题。当前 WorkBuddy 5.5.3/Driver 1.7.0 节点已通过 3 个 L1 真实并发 smoke；WorkBuddy/Skill 升级、换机或切换模型后仍要重跑，未通过时显式使用 `--run-slots 1`。

## 6. Codex Desktop 自动评分

### 6.1 先冻结并复制执行产物

评分前先备份整个 Harness 根目录，然后执行：

```bash
python3 <harness-root>/tools/prepare_scoring_workspace.py \
  --package-root <harness-root> \
  --scoring-archive <absolute-scoring-zip>
```

该步骤会：

- 验证 `execution-receipt.json`；
- 三次检查候选哈希；
- 将 execution 候选复制到独立的 score 单题目录；
- 绑定实际回读模型和执行回执 SHA；
- 生成 `private-scoring/candidate_artifact.json`。

评分不能直接在 `execution/tasks/` 中进行。

### 6.2 注册项目和创建评分任务

Codex Desktop 必须在控制任务开始前开放本机 CDP。先探测：

```bash
bash <orchestrate-web-e2e-skill-dir>/scripts/run-codex-project-registrar.sh \
  --probe \
  --endpoint http://127.0.0.1:9230
```

项目注册成功必须同时满足：

- 评分目录通过 UI 或已显式允许的 renderer bridge 注册；
- Desktop 内置 `list_projects` 按规范化绝对路径唯一回读；
- 注册前后的 Desktop 版本一致；
- `preflight` 校验候选哈希、执行回执、评分 Skill 版本和指标 Profile。

随后由控制 Agent 调用 Desktop 内置 `create_thread` 和 `wait_threads`。不要用 Computer Use 点击 Codex 自己，也不要从外部启动裸 `codex app-server` 会话代替 Desktop 任务。

初始化评分状态时可设置 `--score-slots`、`--score-port-base`、`--score-timeout-seconds` 和 `--max-retries`。新批次默认 3 槽、基础端口 4173、deadline 7200 秒、失败终态最多重试 1 次；最多支持 8 槽，显式 `--score-slots 1` 可回退串行。每题端口固定为基础端口加任务序号，这些参数在批次初始化后不可修改；旧 revision 3 状态恢复后仍是 1 槽。每次 `wait_threads` 前从 `status`/`resume` 的 `recommended_actions` 读取所有活动题各自的 `after_cursor` 与 `next_wait_sequence`，一次等待多个目标，返回后由唯一控制任务逐题串行执行 `record-wait`。单次轮询未等到事件应记录为 `POLL_TIMEOUT`；它不等于评分 deadline 超时。

控制任务重启后先执行：

```bash
node <orchestrate-web-e2e-skill-dir>/scripts/scoring-control.mjs resume \
  --package-root <harness-root>
```

返回 `WAIT_EXISTING_THREAD` 时必须查询其中记录的原 `thread_id`，并把保存的 cursor 作为 `afterCursor`；并发批次要把全部等待动作放进同一次 `wait_threads`。只有原任务终态已经确认且仍有 retry 配额时，才可 `prepare-retry`。任一题失败后继续跟踪已活动题，但暂停补入新题，直至失败题收口。如果失败 attempt 已产生 `score_input.json`、`task_score.json`、Browser 证据、日志或运行时副本，控制脚本会把完整旧 `private-scoring/` 移入 `score/.orchestrate-web-e2e/attempts/`，生成带终态、cursor、deadline、错误原因、文件清单和 SHA-256 的 `attempt-error-receipt.json`，再恢复初始化时冻结的评分输入；不能人工删除旧文件后重试。Desktop 重启需要用户或外部 watchdog 重新拉起应用，恢复后仍执行同一流程。

### 6.3 单题评分边界

每个评分任务只能访问：

```text
score/tasks/<task_id>/
```

评分 Agent 必须使用桌面内置 Browser 逐项操作和取证，并生成：

```text
private-scoring/task_score.json
private-scoring/evidence/
```

候选 `workspace/` 是只读输入。安装依赖、构建、缓存和启动服务只能发生在 `private-scoring/runtime-workspace/` 运行时副本中。

端口冲突时优先通过启动参数或环境变量换端口。只有日志明确证明端口占用、项目又无法外部覆盖端口时，才允许对运行时副本中的唯一端口数字做受控替换；execution 和 score 的候选原件始终不能修改。

静态入口在 `workspace/dist/` 或 `workspace/build/` 时，可分别使用 `managed_runtime.mjs start-static --root dist` 或 `--root build`。`--root` 始终相对 `workspace/` 解析，不能传绝对路径、`..`、符号链接或不存在的目录。

Browser 截图必须使用 `score-web-e2e 4.4.0` 内置的一次性接收器落盘，不能在单题目录临时编写接收脚本，也不能通过剪贴板或手工 Base64 分片传输。评分 Agent 对每张图执行：

```bash
node <score-web-e2e-skill-dir>/scripts/screenshot_receiver.mjs \
  start --task-root . --filename desktop-main.jpg
```

命令会后台启动并返回仅本机可用的一次性 `upload_url`。评分 Agent 在 Desktop Browser 的持久 JavaScript 会话中把 `tab.getScreenshot({ emit: false })` 返回的二进制直接 `POST` 到该 URL；只有 HTTP 201 且 `status --task-root .` 返回 `COMPLETED` 才算取证成功。文件扩展名、`Content-Type` 与 PNG/JPEG 签名必须一致。接收器默认 5 分钟超时、20 MiB 上限，上传一张合法图片后自动退出；异常时使用 `stop --task-root .` 精确停止记录的 PID。

### 6.4 评分异常不是候选零分

以下情况应记录 `evaluation_error`，不能伪造 Criterion 零分或成功证据：

- 浏览器不可用；
- 站点无法安全启动；
- 缺少候选入口文件；
- 评分工具无法完成 Rubric 要求的操作；
- 证据不足以判断。

一题只有先保存评分任务 `COMPLETED` 终态，再通过 `mark-complete` 的身份、哈希、状态、证据、服务终态和 `runtime-workspace` 清理门禁后，才释放该题槽位并补入下一题；多题可乱序完成。最后一题通过后，控制脚本会使用 preflight 绑定的评分 Skill 原子生成 `submission.json`；重复调用不会重复生成，已完成文件丢失或 SHA 漂移会失败关闭。

## 7. 回传和报告

### 7.1 已验证基线

2026-09-08 的真实批次 `web-e2e-20260908-123216` 是当前全局组合验收基线。5 个开源 ArtifactsBench L1 用例使用 WorkBuddy `xopglm52` 和默认三槽执行，5/5 `SUCCEEDED`，第四、五题分别在前序题终态后约 4.5 秒和 4.4 秒补位；执行总墙钟约 22 分钟，长尾为 ab1775。Codex Desktop 26.901.51231 使用 `score-web-e2e 4.4.0`、独立端口 4173–4177 完成五题，得分为 ab241 61、ab378 79、ab699 57、ab1468 77、ab1775 88，平均 72.40。评分第五题因控制任务交接约延迟 13 分钟才恢复补位，但沿用磁盘状态且没有重复创建任务。最终 `submission.json` SHA-256 为 `a027c40e2e98a20f4798c22d820c7dd5004807140b282774a0f29288f995c74e`；return ZIP 为 27,902,048 bytes，SHA-256 为 `41d1561d6b00e57bfde70465f55c82b675e9b8aff36bcf13837e79b3ca1a961e`。安全导入后生成的 JSON、Markdown 和 Excel 一致记录 5/5 completed、平均 72.40，Excel 三张 Sheet 均通过渲染和公式错误扫描。

2026-09-07 的真实批次 `web-e2e-20260907-124800__workbuddy` 使用 WorkBuddy 5.5.3、Driver 1.6.1、`current/xopglm52` 和 `score-web-e2e 4.3.0`，完成 5 个 L1 用例的执行、5 个独立 Codex Desktop 项目/任务、Browser 评分和 submission。得分依次为：ab241 55、ab378 65、ab699 67、ab1468 77、ab1775 91；编排最终为 `COMPLETED`。

回传 ZIP：

```text
/Users/gzx/debug-workspace/web-e2e/web-e2e-20260907-124800__workbuddy__submission.zip
size: 32848336 bytes
sha256: cc30f4d350f67ad3700857c63d704d035985ef810679367808c507187b14c495
unzip -t: No errors detected
```

评分前完整备份 SHA-256 为 `b413c7a095b58b09b14a80af005172a20b14443f84d503f2506f8bda8f38065f`。该五题基线不能证明 `score-web-e2e 4.4.0`，但后续单题批次 `web-e2e-20260907-192642` 已补齐新版真实 Desktop smoke：WorkBuddy 5.5.3/Driver 1.6.1 保持 `current/xopglm52` 完成 L1 用例 `07_Website_Generation_task_ab378_square_circle_intersection`，Codex Desktop 任务 `01a07ba6-b2a2-7ec3-a842-045a4798105f` 使用内置 Browser 完成 10 项评分，得分 79。6 张 JPEG/JFIF 截图均通过 4.4.0 内置 `screenshot_receiver.mjs` 一次性上传，最后接收器状态为 `COMPLETED`，截图签名、字节数和 SHA-256 复核通过；服务已精确停止、运行时副本已清理、候选 SHA 始终为 `ba090603aed15d39a83096997caf316d7dca5d608ceda55d485ccd0a770bdf53`，`submission.json` SHA-256 为 `742b5c4ca8cbf7d3eda3a6b60fddf0212add973ee3709b3390b64265e791d760`。

该单题产物的入口直接位于 `workspace/index.html`，所以它只验证截图接收器，不能单独证明 `start-static --root <子目录>`。随后从五题基线中选择入口天然位于 `workspace/square-circle-intersection/index.html` 的同一 ab378 候选，建立只含该题的隔离包 `web-e2e-20260907-124800__workbuddy__score440-root-smoke`，并由 Codex Desktop 任务 `01a07bc2-fb0d-7ed0-9841-12e0cf6ad09d` 使用 `score-web-e2e 4.4.0` 完成真实 Browser smoke。运行状态记录 `service.static_root=workspace/square-circle-intersection`、`service.http_status=200` 和 `service.status=STOPPED`，精确 PID/进程组校验通过，`runtime-workspace` 已清理；4 张 JPEG/JFIF 截图通过一次性接收器落盘，接收器终态为 `COMPLETED`。原批次 workspace、隔离 execution workspace 和隔离 score workspace 内容一致，候选 SHA 始终为 `b417f2a8eba8021f2ebad5d20fdd14bfdfaa85d0f348dc3344647834a86c0b69`。`mark-complete` 与 `build_submission.mjs` 均通过，隔离包 `submission.json` SHA-256 为 `f330b0fa92c7d42c912146e141a7220955483480b5f7cc747f9c535a17c5e046`。

同一历史评分任务随后用于 Desktop 重启恢复 smoke。重启前编排状态为 `SCORING/WAIT_EXISTING_THREAD`；Desktop 整个进程退出并重新打开后，`resume` 仍返回原任务 `01a07bc2-fb0d-7ed0-9841-12e0cf6ad09d`，没有创建替代任务。实际 `wait_threads` 完成终态和 cursor 被持久化后，`mark-complete` 自动生成 submission；重复执行 `build-submission` 的 SHA 均为 `28bb1b59cd22784142269fc303205132c1a9c79f264b9becff639399d5c9b892`，且无 pending 文件残留。来源、隔离 execution 和隔离 score 三份候选 workspace 两两一致。

另一个独立 Codex 控制任务接管也已完成实测。原控制任务只把隔离包 `web-e2e-20260907-124800__workbuddy__r5c-independent-controller-smoke-20260907-212718` 准备到 `SCORING/WAIT_EXISTING_THREAD`；独立任务 `01a07c0e-a166-7f51-8513-51076fbf63e3` 随后只读取磁盘状态，查询同一历史评分任务，保存真实 cursor `a49ffe10-3900-4c0b-bdf8-b59cafdfa222:1` 和 `COMPLETED` 终态，再由 `mark-complete` 自动生成 submission。最终状态为 `COMPLETED`，无 pending 文件，submission SHA-256 为 `8a3586342fd18e056be6a73f9f26b4007879914ce113250dcc1830aac1ccbe9a`；来源 execution、隔离 execution 和隔离 score 三份候选 workspace SHA 都是 `b417f2a8eba8021f2ebad5d20fdd14bfdfaa85d0f348dc3344647834a86c0b69`。该任务没有新建替代评分任务、重新评分或修改候选产物，证明控制面恢复不依赖原控制会话上下文。

该隔离 smoke 沿用旧批次身份，只验证评分运行时，不是新的 WorkBuddy 模型执行结果；其重复评分 69/100 不得合并到正式报告。

2026-09-08 又从同一五题执行包建立三题只读隔离包 `web-e2e-20260907-124800__workbuddy__r7-score3-smoke-20260908-084054`，选择 ab241、ab378、ab699 三个 L1 历史产物，并在 `execution-receipt.json` 中明确记录 `isolation.formal_result=false`。Codex Desktop 26.901.51231 同时创建三个独立评分任务，使用 `score-web-e2e 4.4.0` 和内置 Browser；三个受管站点在 4173、4174、4175 上有约 7 分 30 秒的共同监听区间，完成顺序为 ab378、ab241、ab699，单任务耗时约 9 分 22 秒、9 分 45 秒、10 分 39 秒，总墙钟时间约 10 分 36 秒。三个评分分别为 68、63、68，只用于并发运行时验证，不得并入正式成绩。

三题的 `task_score.json`、Browser 截图、观察记录、站点 PID/PGID、截图接收器和 task identity 均保存在各自目录；全部截图 SHA-256 不同，submission 中的证据引用都只能解析到本题 `private-scoring/evidence/`。三个站点均为 HTTP 200 后精确停止，截图接收器均为 `COMPLETED`，没有残留 `runtime-workspace`，4173–4175 无监听残留。来源 execution、隔离 execution、隔离 score 三份候选逐文件一致；`mark-complete` 的双副本 SHA 门禁全部通过。最后一题完成后只进行一次 submission 构建，文件 SHA-256 为 `f2e15d629d85a855611fb85f5b84360d101d1754d30690cf459e62eaae65a341`。该 smoke 证明当前评分机的三路 Browser、端口、截图、服务进程和结果隔离可用；候选没有统一的 Cookie/localStorage 场景，因此共享 Browser profile 下的显式存储 sentinel 仍应作为后续增强测试，而不是本轮已证明结论。

### 7.2 生成 submission 与报告

全部评分完成后，由不参与单题评分的管理任务运行：

```bash
node <score-web-e2e-skill-dir>/scripts/build_submission.mjs \
  --package-root <harness-root> \
  --output <harness-root>/submission.json
```

该命令会再次检查：

- execution 和 score 两份候选哈希；
- 模型身份和模型选择模式；
- 每题评分结果与证据；
- 受管服务已停止；
- 截图接收器已进入可信终态，最近一次成功截图的大小、SHA-256 和签名一致；
- 运行时副本已清理；
- 禁止目录和敏感文件。

随后压缩完整 Harness 根目录并回传。报告阶段使用批次报告配置补充模型友好名称、Harness 名称和用户声明的推理强度。

## 8. 多电脑分工

最小分配单元是 `Harness（模型）`。同一 Harness、同一模型的一批题不要拆到多台机器，否则客户端默认配置、版本和会话状态难以保证一致。

常见组合：

| 机器 | 分工 |
| --- | --- |
| 机器 A | WorkBuddy（模型 A）执行 |
| 机器 B | AstronStudio（模型 A）执行；其 Driver 完成后再启用自动化 |
| 机器 C | Codex Desktop 按本机 `score_slots` 评分一个或多个已完成 Harness 包 |
| 管理机器 | 准备批次、收集 submission、生成报告 |

跨机器只传递完整文件包：

1. 管理员向执行机器发送对应 Harness 的 execution ZIP，并确保执行 Skill 已安装。
2. 执行完成后备份整个 Harness 根目录。
3. 将完整 Harness 根目录和同批 scoring ZIP 交给评分机器。
4. 评分完成后回传包含 `submission.json` 的完整 Harness ZIP。
5. 管理员将全部回传 ZIP 与同一份报告配置交给 `report-web-e2e`。

## 9. 候选产物不可修改

被评 Harness 结束后，候选产物即冻结。以下主体都不能再修改它：

- 执行控制 Agent；
- 评分 Agent；
- 评分编排 Agent；
- 报告 Agent；
- 人工操作人员。

禁止为了“让评分跑起来”而在候选目录中：

- 改源码或端口；
- 创建 `package.json`；
- 安装依赖；
- 执行会写缓存的构建；
- 删除 `.git`、`node_modules` 或其他不合规内容；
- 重算哈希并接受漂移后的新值；
- 从评分副本覆盖回 execution 原件。

发现候选不合规时保留现场并重新执行该评测单元，不能清理后继续评分。

## 10. 常见问题

### 未传模型，为什么回执里的 requested model 是空的

这是预期行为。`mode=current` 表示自动化沿用用户预配置，`requested_model=null`，但 `actual_model` 和顶层模型必须非空。

### 显式指定模型后无法找到选项

确认传入的是 WorkBuddy 下拉框中的精确显示名。不要使用报告中的友好名称、CLI 路由前缀或猜测的模型 ID 代替 UI 文本。

### 同一队列的实际模型不一致

停止评测，确认是否有人在队列执行期间修改了 WorkBuddy 默认模型。不要编辑回执修复；新建时间戳批次后重新执行。

### 推理强度为什么没有出现在执行回执

它由用户在 Harness 中预配置，当前不做 UI 自动回读。报告配置中的值是用户声明信息，不代表自动化已经验证。

### WorkBuddy 未开放 9229 调试端口

第一题使用 `--restart-app-first`，让 Driver 有界重启并验证 CDP；如果仍失败，检查客户端路径、版本和本机权限。不要在有运行中任务时强制重启。

### Codex Desktop 项目注册失败

先确认 `127.0.0.1:9230` 探测成功。默认使用可见 UI；renderer bridge 是版本敏感的私有兜底，只能显式启用，并且必须由 `list_projects` 按绝对路径回读。

### 评分任务没有 Browser

确认任务是通过当前 Codex Desktop 内置任务接口创建，项目路径是单题评分目录。不要用裸 CLI/App Server 任务冒充 Desktop 评分任务。

### 控制任务或 Codex Desktop 重启

不要重新初始化批次或创建新评分任务。运行 `scoring-control.mjs resume`，按照 `recommended_actions` 查询状态中已有的全部 `thread_id`；`recommended_action` 只用于串行兼容。`WAIT_EXISTING_THREAD` 必须携带保存的 `after_cursor`。Desktop 本身不会由当前控制任务在进程退出后继续拉起，需要人工重新打开或部署独立 watchdog。

### 失败评分已经留下部分文件

不要删除 `private-scoring/` 中的部分评分、截图、日志或运行时状态。确认原 Desktop 任务已经进入终态，并通过 `score-web-e2e` 的受管命令停止站点服务和截图接收器后，再执行 `prepare-retry --retry-reason <说明>`；控制脚本会先检查运行时均已静默，再原子归档失败 attempt、生成结构化错误回执并恢复干净的评分输入。下一 attempt 仍需重新执行 preflight。无状态文件的运行时副本、仍为 `RUNNING` 的运行时、归档 journal、错误回执或归档内容发生漂移时都应停机审计，不能跳过门禁。

### wait_threads 返回超时

这只表示本次轮询没有等到新事件，记录为 `POLL_TIMEOUT` 后继续使用同一 `thread_id` 和 cursor。只有评分 attempt 的 `deadline_at` 已到，才能执行 `mark-timeout`；原任务终态不明时仍禁止重试。

### 站点启动失败或 Browser 被拦截

记录真实错误并使用 `evaluation_error`。评分基础设施失败不等于候选功能全部为零。

### Browser 截图二进制无法稳定落盘

不要复制 Base64 文本，也不要在题目 `private-scoring/` 中临时创建接收器。确认评分机安装的是 `score-web-e2e 4.4.0` 或更高版本，按第 6.3 节为每张图单独启动 `screenshot_receiver.mjs`，并检查扩展名、`Content-Type` 和二进制签名是否一致。仍失败时停止接收器并记录 `evaluation_error`，不能伪造截图。

### 恢复时提示配置不一致

恢复必须使用原 `run-id`、原任务顺序、原模型模式和原权限模式。旧版以“均衡”为显式默认模型创建的未完成队列，恢复时应继续显式提供 `--model 均衡`；不要把它改成新的 `current` 模式。

## 11. 最终检查清单

### 管理员

- [ ] 批次 ID 包含时间戳且没有复用旧目录。
- [ ] execution 包不含 Ground Truth、Rubric、checker、`eval/` 或 `gt/`。
- [ ] 报告配置已填写每个 Harness（模型）单元的模型和推理强度声明。
- [ ] 每个回传包的 `batch_id`、`source_revision`、Profile 和任务范围一致。

### 执行人员

- [ ] 跑批前已设置 Harness 默认模型、推理强度和权限。
- [ ] 未指定模型时确认使用的是 `current` 模式；显式指定时使用 UI 精确显示名。
- [ ] 同一队列执行期间没有人工切换模型。
- [ ] 当前节点已通过 3 个 L1 执行并发 smoke；未通过时已显式使用 `--run-slots 1`。
- [ ] `execution-receipt.json.integrity.valid=true`。
- [ ] 候选 Workspace 中没有 `.git`、`.cache`、`.vite` 或 `node_modules`。
- [ ] 执行完成后已备份完整 Harness 根目录。

### 评分人员

- [ ] 评分目录由标准准备脚本从执行原件复制生成。
- [ ] 每题是独立 Codex Desktop 项目和独立任务。
- [ ] 每题实际使用桌面内置 Browser 操作和取证。
- [ ] 截图由标准一次性接收器保存，最后状态为 `COMPLETED`、`STOPPED`、`TIMED_OUT`、`FAILED` 或 `LOST`，没有存活接收进程。
- [ ] `task_score.json` 引用的每个截图文件都存在于当前题 `private-scoring/evidence/`，且不是空文件。
- [ ] 候选 Workspace 没有被评分或编排 Agent 修改。
- [ ] 每题通过 `mark-complete` 且运行时已清理后才释放槽位并补入下一题。
- [ ] 根目录已生成有效 `submission.json`。
- [ ] 回传 ZIP 包含完整 Harness 根目录。
