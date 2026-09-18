# Web 站点端到端自动化评测指导手册

本文面向评测管理员和执行人员，说明如何通过 Prompt 调用 Web E2E Skill。用户不需要进入 Skill 目录运行执行或评分脚本；依赖检查、解压、执行、评分、状态恢复和回传打包均由控制 Harness 完成。

## 术语定义

| 术语 | 定义 |
| --- | --- |
| 控制 Harness | 用来接收用户 Prompt、调用 Web E2E Skill 并统筹执行、评分、回传和报告的 Harness。推荐使用 Codex Desktop。 |
| 被评测 Harness | 实际完成题目的桌面 Agent 客户端，例如 AstronStudio、WorkBuddy、QwenWork。 |
| 评分 Harness | 为被评测 Harness 的候选网站打分的 Agent。当前使用 Codex Desktop，并依赖其桌面内置 Browser 操作网站和保存证据。 |
| 管理员 | 选择用例和被评测 Harness、准备评测包、收集各机器回传包并生成报告的人员。 |
| 执行人员 | 接收管理员分发的题目包和评分包，在本机完成一个 `Harness（模型）` 单元的执行、评分和回传。 |
| 批次 | 一次带时间戳的评测集合。批次固定用例范围、源码版本和指标 Profile。 |
| 题目包 | 文件名以 `__execution.zip` 结尾，包含公开 Prompt 和被评测 Harness 可见的初始工作空间，不包含标准答案或评分标准。 |
| 评分包 | 文件名以 `__scoring.zip` 结尾，只包含评分契约和私有评分材料，必须等做题完成后再合入评分工作空间。 |
| 回传包 | 完成评分后生成的完整 Harness ZIP，以及同级的 SHA-256 回执。管理员可离线接收并导入。 |

## Web E2E Skill

| Skill | 使用者 | 功能 |
| --- | --- | --- |
| `prepare-web-e2e-workspaces` | 管理员 | 从 WildClawBench 用例生成题目包、评分包、报告配置和 5 个可分发 Skill ZIP。它是仓库内的准备 Skill，不计入批次分发的 5 个 ZIP。 |
| `run-web-e2e` | 管理员或执行人员 | 推荐的全局入口。只组合 Prompt 中明确要求的准备、执行、评分、打包回传、收集和报告阶段。 |
| `execute-web-e2e` | 执行人员 | 操作被评测 Harness 做题。WorkBuddy、AstronStudio 和 QwenWork 的默认后台并发均为 3，最大均为 8，UI 操作保持单路。 |
| `orchestrate-web-e2e` | 执行人员或评分控制人员 | 校验执行结果、准备只读评分副本、注册 Codex Desktop 项目并调度多个评分任务。 |
| `score-web-e2e` | Codex Desktop 单题评分任务 | 使用桌面内置 Browser 对一个用例评分并生成标准评分 JSON。通常由 `orchestrate-web-e2e` 自动调用，也支持人工单题调用。 |
| `report-web-e2e` | 管理员 | 汇总一个或多个 Harness 回传包，生成 JSON、Markdown 和 Excel 报告。 |

批次向执行和评分机器分发的 5 个 Skill 是 `run-web-e2e`、`execute-web-e2e`、`orchestrate-web-e2e`、`score-web-e2e` 和 `report-web-e2e`。Skill 包使用 `<skill-name>-skill-v<version>.zip` 命名，不带批次号；同一版本同时适用于自建与开源评测集。管理员准备机器还需要仓库内的 `prepare-web-e2e-workspaces`。

管理员可以在 macOS 或 Windows 上生成评测包。执行人员应安装同一批次随包提供的 Skill ZIP，并以 `batch_manifest.json`、`skills-manifest.json` 中的版本和 SHA-256 为准。不要混用不同批次的题目包、评分包或 Skill 包。

## 使用方法

### 做题+打分场景

适用场景：管理员已经准备好某个 Harness 的题目包和评分包，执行人员只需在自己的机器上完成做题、打分和打包回传。

#### 1. 准备被评测 Harness

在本轮被评测 Harness（WorkBuddy、AstronStudio 或 QwenWork）中完成以下设置：

1. 选择本轮评测模型，例如 GLM5.2 对应的客户端模型选项。
2. 设置该模型的推理强度。
3. 权限选择“**允许完全访问**”或“**完全访问**”。
4. 确认没有需要保留的运行中任务。

如果 Prompt 没有明确指定模型，执行 Skill 会保持并回读客户端当前模型，不会修改推理强度。评测期间不要人工切换模型。

#### QwenWork Token 采集开关（由 Skill 自动管理）

用户不需要手工设置 `QODERCN_EXPOSE_TOKEN_USAGE`，也不要把它写入系统全局环境、题目 Prompt 或评分 Agent 配置。Driver 会仅向新 QwenWork 客户端子进程注入 Token 采集开关，不会修改控制 Harness 的全局环境。

全新单题默认在发送 Prompt 前安全重启 QwenWork；全新批次默认只在第一题前重启一次，后续题目复用同一个已带开关的客户端进程。重启前 Driver 会核对主程序完整路径、9250 调试端点和状态库；只要发现活动任务就停止并进入人工处理，不会为了采集 Token 强制打断会话。普通调用不需要额外写环境变量或重启参数：

```powershell
& 'C:\Skills\execute-web-e2e\scripts\run-qwenwork.cmd' `
  'D:\评测包\<batch_id>__qwenwork\execution\tasks\<task_id>'
```

```powershell
& 'C:\Skills\execute-web-e2e\scripts\run-qwenwork-batch.cmd' `
  'D:\评测包\<batch_id>__qwenwork' `
  --run-id '<run-id>' --task-id '<task-id>' --run-slots 1 --permission-mode full-access
```

采集器会核对客户端和原生记录身份。无法可靠归属的用量保持为未知，不会补零或写入其他用例。

WorkBuddy、AstronStudio 和 QwenWork 的默认后台执行并发均为 3，最大均为 8，UI 操作保持单路。首次在新机器上使用、升级 Harness/Skill 或切换模型后，建议先以并发 1 运行 1–3 个用例，确认模型、权限、产物和回执正常后再使用默认并发。

#### 2. 自动准备桌面客户端调试模式

`run-web-e2e` 在进入执行或评分阶段前会自动检查 Codex Desktop 和本轮选择的 AstronStudio、WorkBuddy 或 QwenWork。有效 CDP 端点会原样复用；缺少调试模式时只关闭并重启需要的客户端，无需人工退出、重新打开。Windows 会动态解析 Codex MSIX 和所选 Harness 的当前用户安装路径，macOS 会解析标准系统或用户 Applications 目录。Windows 还会核对监听者和待停止进程的完整可执行路径；macOS 在重启已运行的 WorkBuddy/QwenWork 前会只读核对状态库，无法证明没有活动任务时停止并提示人工处理。

默认 Codex Desktop 使用 `127.0.0.1:9230`，AstronStudio 使用 `127.0.0.1:9240`，WorkBuddy 使用 `127.0.0.1:9229`，QwenWork 使用 `127.0.0.1:9250`，且都只监听本机。若 Codex Desktop 本身承载当前控制任务，Skill 会在持久化状态后使用一次性托管任务重启；当前回合可能中断，客户端恢复后必须继续原任务，不要重新初始化。

#### 3. 安装 Skill

可以通过 Codex 的 Skill 管理功能手动安装，也可以在 Codex 控制任务中通过 Prompt 自动安装。两种方式都应使用管理员随同本批次分发的 `packages/skills-manifest.json` 和版本化 Skill ZIP，不要从不同批次拼装。

手动安装并启用以下 5 个 Skill：

- `run-web-e2e`
- `execute-web-e2e`
- `orchestrate-web-e2e`
- `score-web-e2e`
- `report-web-e2e`

需要自动安装时，在 Codex Desktop 中新建一个控制任务，输入下面的 Prompt。将 `Skill 包目录` 替换为本批次 `packages` 目录的绝对路径；macOS 示例为 `/Users/tester/WebE2E/<batch_id>/packages`，Windows 示例为 `D:\WebE2E\<batch_id>\packages`。

```text
请只安装下面目录中的 Web E2E Skill，不要执行评测、启动 Harness 或修改任何题目 workspace。

Skill 包目录：/absolute/path/<batch_id>/packages

安装要求：
1. 读取 Skill 包目录中的 skills-manifest.json，以其中的 skills 列表为唯一安装清单；安装 run-web-e2e、execute-web-e2e、orchestrate-web-e2e、score-web-e2e 和 report-web-e2e。
2. 安装前逐个校验 ZIP 的文件名、SHA-256、唯一顶层目录、解压内容的 content SHA-256，以及 skill-metadata.json 中的 name/version；ZIP 包含绝对路径、.. 或符号链接时停止。
3. 安装到当前用户的 Codex 用户级 Skill 目录：macOS 使用 $HOME/.agents/skills，Windows 使用 %USERPROFILE%\.agents\skills。不要安装到仓库、评测批次、execution、score 或候选 workspace 中。
4. 已安装版本和 content SHA-256 完全一致时跳过。需要升级时，先把旧目录备份到 Skill 根目录之外，再通过临时目录解压、校验并原子替换；任一步失败都恢复旧版本，不覆盖无关 Skill。
5. 安装后使用 run-web-e2e/scripts/check_web_e2e_skills.py 对同一 skills-manifest.json 重新检查，必须 all_current=true；否则停止并报告，不开始评测。
6. 最后列出每个 Skill 的 installed、skipped 或 failed 状态，以及实际安装路径、版本和 content SHA-256。若 Codex 没有立即发现新 Skill，提示我重启 Codex 后新建控制任务，不要在当前任务中继续执行评测。
```

这个 Prompt 不依赖 Web E2E Skill 已经安装；Codex 可以先把本地 ZIP 安装到用户级目录。Codex 通常会自动发现新安装的 Skill；如果安装结果未出现在 Skill 列表中，重启 Codex 后再开始评测。

每个版本在本机安装一次即可。控制 Harness 会根据题目包 `manifest.json.required_skills`，校验已安装 Skill 的名称、版本和内容 SHA-256；完全一致时跳过安装，只安装缺失或版本不一致的包。版本相同但内容 SHA 不同会停止并报错，不能把不同内容当作同一版本。用户不需要手工安装执行或评分自动化依赖；控制 Harness 会自行检查并补齐。依赖安装失败时流程会停止并返回错误，不会把依赖装进候选工作空间。

#### 4. 输入一个 Prompt

在 Codex Desktop 中新建控制任务，输入：

```text
请使用 $run-web-e2e 完成下面 Web E2E 评测用例的执行、评分、打包回传。

题目：/absolute/path/<batch_id>__workbuddy__execution.zip
评分标准：/absolute/path/<batch_id>__workbuddy__scoring.zip
```

这个 Prompt 已足以完成以下动作：

1. 校验两个 ZIP 属于同一批次、同一 Harness 和相同用例范围。
2. 解压题目包，建立独立 worker 工作目录。
3. 自动检查和安装执行、评分所需的锁定依赖。
4. 使用题目包声明的被评测 Harness，以客户端当前模型和推理强度执行全部题目，权限使用 `full-access`。
5. 三个 Harness 的默认值均为 3 路执行并发、最大 8。任一题明确结束并通过回执校验后动态补入下一题。
6. 校验执行回执后合入评分包。
7. 默认创建 3 个并发 Codex Desktop 评分任务，每题使用独立项目、任务、Browser 和端口。
8. 生成 `submission.json`、完整回传 ZIP 和外部 SHA-256 回执。

默认 Codex Desktop CDP 地址为 `http://127.0.0.1:9230`。需要使用其他端口、改成串行或显式切换被评测模型时，再在 Prompt 中增加对应要求。

例如显式指定模型：

```text
执行时显式选择 WorkBuddy 中显示的模型 xopglm52，并在发送每题 Prompt 前回读确认；不要修改推理强度。
```

AstronStudio 使用示例：

```text
请使用 $run-web-e2e 完成下面 AstronStudio Web E2E 评测用例的执行、评分、打包回传。

题目：/absolute/path/<batch_id>__astronstudio__execution.zip
评分标准：/absolute/path/<batch_id>__astronstudio__scoring.zip

保持并回读 AstronStudio 当前模型，不修改推理强度；权限使用 full-access；使用默认执行并发 3。
```

WorkBuddy 使用示例：

```text
请使用 $run-web-e2e 完成下面 WorkBuddy Web E2E 评测用例的执行、评分、打包回传。

题目：/absolute/path/<batch_id>__workbuddy__execution.zip
评分标准：/absolute/path/<batch_id>__workbuddy__scoring.zip

保持并回读 WorkBuddy 当前模型，不修改推理强度；权限使用 full-access；使用默认执行并发 3。
```

QwenWork 使用示例：

```text
请使用 $run-web-e2e 完成下面 QwenWork Web E2E 评测用例的执行、评分、打包回传。

题目：/absolute/path/<batch_id>__qwenwork__execution.zip
评分标准：/absolute/path/<batch_id>__qwenwork__scoring.zip

保持并回读 QwenWork 当前模型，不修改任务模式或其他推理设置；权限使用 full-access；使用默认执行并发 3。Token 采集开关由 execute-web-e2e 自动管理，不要手工设置环境变量。
```

例如临时使用串行：

```text
QwenWork 执行并发和 Codex Desktop 评分并发都设为 1。
```

#### 5. 获取回传包

成功后，控制 Harness 会返回以下两个文件的绝对路径：

```text
<batch_id>__<harness>__return.zip
<batch_id>__<harness>__return-receipt.json
```

把两个文件一起离线发送给管理员。不要只发送 `submission.json`、`score/` 或单题目录。

#### 6. 中断后恢复

控制任务中断或 ChatGPT 重启后，不要重新开始同一批次。在新的控制任务中输入：

```text
请使用 $run-web-e2e 恢复下面批次，沿用磁盘上已有状态继续，不要重新初始化、重复创建任务或重发题目 Prompt。

题目：/absolute/path/<batch_id>__<harness>__execution.zip
评分标准：/absolute/path/<batch_id>__<harness>__scoring.zip
```

若状态是 `NEEDS_ATTENTION`，按控制 Harness 返回的具体原因处理。不要通过删除状态文件、编辑回执或修改候选网站来强行继续。

### 全流程场景

适用场景：同一台机器同时承担管理员、执行人员和评分人员角色，从获取仓库开始，完成准备工作空间、做题、评分、离线收集和出报告。

#### 1. 一次性准备

1. 在 Codex 用户级 Skill 中安装 `run-web-e2e`。这样即使仓库尚未下载，也能识别下面的 Prompt。
2. 按“做题+打分场景”设置 WorkBuddy。
3. 启动 Codex Desktop 并新建控制任务。`run-web-e2e` 会自动检查 CDP 调试模式，必要时按流程重启客户端。

#### 2. 输入全流程 Prompt

```text
请使用 $run-web-e2e 完成一次 Web 站点端到端评测的准备、执行、评分、打包回传、收集和报告。

如果本机还没有仓库，请从下面地址下载到指定目录；已经存在时只校验并复用，不要覆盖本地修改。
仓库：https://code.iflytek.com/CYXH_Agent/astroncode-eval.git
本地目录：/Users/tester/Project/WildClawBench

用例：
- 07_Website_Generation_task_ab241_menu_switch_gui_framework
- 07_Website_Generation_task_ab378_square_circle_intersection
- 07_Website_Generation_task_ab699_css_formatter_tool
- 07_Website_Generation_task_ab1468_mall_register_login_page
- 07_Website_Generation_task_ab1775_pi_derivation_demo

被评测 Harness：WorkBuddy
指标 Profile：auto
输出目录：/Users/tester/WebE2E
报告模型：xopglm52
报告推理强度：客户端默认值

保持并回读 WorkBuddy 当前模型，不修改推理强度，权限使用 full-access。
执行和评分均使用默认并发 3；Codex Desktop CDP 使用 http://127.0.0.1:9230。
准备完成后从 execution ZIP 解压独立 worker 根，不要直接使用管理员 staging 根做题或评分。
最终生成并校验回传 ZIP、外部回执、报告 JSON、领导版 Markdown 和三 Sheet Excel。
```

如果本次包含资源指标，Prompt 还应明确要求：执行 Driver 在终态采集 `execution_record.json`，评分与回传只透传资源字段，报告阶段检查三个 Harness 的资源覆盖率。报告总量只接受 `observed`/`inferred`/`legacy`；`masked`、`unverified`、`partial` 和 `unavailable` 必须显示为空值、已知小计及覆盖率，不能补成 0。核心字段包括输入/输出/总 Token、缓存读取 Token、执行流程耗时、智能体耗时、模型请求数和工具调用数；没有可靠原生来源的缓存写入 Token、推理输出 Token 和完整 HTTP 尝试次数保持为空。

控制 Harness 会在仓库自身环境和 Skill Driver 目录准备必要依赖，不会在候选网站目录安装依赖。完整流程结束后会返回：

- 带时间戳的批次目录；
- WorkBuddy 回传 ZIP 和回执；
- 报告 JSON、Markdown 和 Excel；
- 各阶段最终状态以及需要人工处理的异常。

### 多电脑场景

多电脑不需要指定固定的 `admin` 或 `worker` 参数。Prompt 明确提到哪些阶段，就只执行哪些阶段。

管理员准备包：

```text
请使用 $run-web-e2e 完成下面批次的准备阶段。

仓库：/absolute/path/WildClawBench
用例：@/absolute/path/task_ids.txt
被评测 Harness：WorkBuddy
指标 Profile：auto
输出目录：/absolute/path/WebE2E
使用自动生成的时间戳批次 ID，不要执行题目或评分。
```

执行人员使用“做题+打分场景”的双 ZIP Prompt，完成执行、评分和打包回传。

管理员收到回传文件后输入：

```text
请使用 $run-web-e2e 完成下面批次的收集和报告阶段。

批次目录：/absolute/path/WebE2E/<batch_id>
回传 ZIP：
- /absolute/path/returns/<batch_id>__workbuddy__return.zip
对应回执：
- /absolute/path/returns/<batch_id>__workbuddy__return-receipt.json

校验所有回传包后生成 JSON、Markdown 和 Excel 报告；缺少任何 Harness 时停止，不要生成不完整报告。
```

同一 `Harness（模型）` 单元不要拆到多台机器。管理员与执行人员之间只需离线传递 ZIP 和对应回执，不要求机器在线互联。

## 各个 Skill 用法详解

### 管理员准备能力：`prepare-web-e2e-workspaces`

功能：从 WildClawBench 自建或开源 Web 用例生成隔离的题目包、评分包、报告配置和 5 个可分发 Skill ZIP。

推荐通过 `run-web-e2e` 组合调用。需要只准备、不执行时，也可以直接输入：

```text
请使用 $prepare-web-e2e-workspaces 生成 Web 站点端到端评测包。

仓库：/absolute/path/WildClawBench
用例：
- <task_id_1>
- <task_id_2>
被评测 Harness：workbuddy
指标 Profile：auto
报告模型映射：workbuddy=xopglm52
报告推理强度映射：workbuddy=客户端默认值
输出目录：/absolute/path/WebE2E

使用自动生成的时间戳批次 ID，只准备工作空间，不执行或评分。
```

主要产物是每个 Harness 的 `__execution.zip`、`__scoring.zip`，以及批次级报告配置和 5 个版本化 Skill ZIP。execution/scoring 包保留批次号；公共 Skill 包按 `<skill-name>-skill-v<version>.zip` 命名，可以跨自建/开源批次复用。题目包不会包含 Ground Truth、Rubric、checker、`eval/` 或 `gt/`。

### 1. `run-web-e2e`

功能：动态组合多个阶段并保存可恢复状态，是日常使用的首选入口。

适用场景：

- 一条 Prompt 完成做题、评分和回传；
- 单机完成全部阶段；
- 管理员和执行人员在不同机器上分阶段运行；
- 控制任务中断后恢复原批次。

Prompt 必须明确写出要执行的阶段和输入路径。没有明确选择的阶段不会自动运行。

```text
请使用 $run-web-e2e 恢复并完成这个批次尚未结束的执行、评分和打包回传阶段：

题目：/absolute/path/<batch>__<harness>__execution.zip
评分标准：/absolute/path/<batch>__<harness>__scoring.zip

读取已有磁盘状态继续，不要重新初始化。
```

### 2. `execute-web-e2e`

功能：只操作被评测 Harness 做题，不评分、不生成报告。

```text
请使用 $execute-web-e2e 执行下面 WorkBuddy 题目包中的全部用例：

/absolute/path/<batch_id>__workbuddy

保持并回读 WorkBuddy 当前模型，不修改推理强度；权限使用 full-access；使用默认并发 3。完成后验证 execution-receipt.json 的 integrity.valid=true。
```

需要显式覆盖模型时，补充 WorkBuddy 下拉框中的精确显示名。首次换机、升级客户端或 Skill、切换模型后，建议先以并发 1 执行 1–3 个用例，确认回执和产物正常后再使用默认并发。

WorkBuddy 默认 `run_slots=3`、最大 8，可显式设为 1 回退串行；所有项目创建、目录选择、模型/权限回读和 Prompt 发送仍保持 UI 单路。

AstronStudio 使用下面的并发 Prompt：

```text
请使用 $execute-web-e2e 执行下面 AstronStudio 题目包中的全部用例：

/absolute/path/<batch_id>__astronstudio

保持并回读 AstronStudio 当前模型，不修改推理强度；权限使用 full-access；使用默认并发 3。完成后验证 execution-receipt.json 的 integrity.valid=true。
```

AstronStudio 默认 `run_slots=3`、最大 8，可显式设为 1 串行执行。

QwenWork 使用同样的并发 Prompt，只需把 Harness 名称和目录改为 QwenWork：

```text
请使用 $execute-web-e2e 执行下面 QwenWork 题目包中的全部用例：

/absolute/path/<batch_id>__qwenwork

保持并回读 QwenWork 当前模型，不修改任务模式或其他推理设置；权限使用 full-access；使用默认并发 3。Token 采集开关和首题前安全重启由 execute-web-e2e 自动管理。完成后验证 execution-receipt.json 的 integrity.valid=true。
```

QwenWork 默认 `run_slots=3`、最大 8，可显式设为 1 串行执行。所有项目创建、目录选择、模型/权限回读和 Prompt 发送仍保持 UI 单路。

### 3. `orchestrate-web-e2e`

功能：将已完成的执行包转换为只读评分工作空间，注册 Codex Desktop 项目，创建并等待评分任务，最终生成 `submission.json`。

```text
请使用 $orchestrate-web-e2e 完成下面执行结果的评分编排：

Harness 根目录：/absolute/path/<batch_id>__workbuddy
评分标准：/absolute/path/<batch_id>__workbuddy__scoring.zip
Codex Desktop CDP：http://127.0.0.1:9230

使用默认评分并发 3。每题创建独立 Codex Desktop 项目和任务，并调用 $score-web-e2e；评分完成后生成 submission.json。不得修改候选 workspace。
```

执行人员不需要逐题新建 Codex 项目或复制评分 Prompt。此 Skill 会为每题注册独立项目并创建评分会话，也不会用 Computer Use 点击 Codex 自己。

### 4. `score-web-e2e`

功能：在一个 Codex Desktop 任务中独立评分一个用例。正常全流程会由 `orchestrate-web-e2e` 自动创建和调用，无需执行人员逐题输入 Prompt。

人工复核单题时，把 `score/tasks/<task_id>/` 作为 Codex Desktop 项目，然后输入：

```text
请使用 $score-web-e2e 评分当前目录中的唯一 Web E2E 用例。

严格按 private-scoring/task_contract.json 操作网站并保存证据，只访问当前项目，不访问父目录或其他题目。候选 workspace 只读；评分完成后生成 private-scoring/task_score.json。
```

如果浏览器不可用、站点无法安全启动或证据不足，Skill 会记录 `evaluation_error`，不会把评分基础设施问题伪装成候选零分。

### 5. `report-web-e2e`

功能：汇总一个或多个已校验回传包，生成报告数据 JSON、领导版 Markdown 和三 Sheet Excel。

```text
请使用 $report-web-e2e 汇总下面 Web E2E 回传包：

回传包：
- /absolute/path/<batch_id>__workbuddy__return.zip
- /absolute/path/<batch_id>__astronstudio__return.zip
报告配置：/absolute/path/<batch_id>__report-config.yaml
输出目录：/absolute/path/report

校验批次、源码版本、Profile、Harness 和完整用例范围一致后，生成并检查 JSON、Markdown 和 Excel。
```

一个报告批次不能混用不同指标 Profile。缺失用量字段显示为未知，不会当作零；执行或评分异常会按正式评分契约进入报告。

## 模型、权限和并发规则

- Prompt 未指定被评测模型：保持并回读客户端当前模型。
- Prompt 显式指定模型：使用客户端 UI 中的精确显示名，选择后回读一致才开始执行。
- 推理强度：始终由用户提前在被评测 Harness 中设置，执行自动化不修改。
- WorkBuddy、AstronStudio、QwenWork 权限：生产评测使用 `full-access`，发送题目 Prompt 前会回读确认。
- WorkBuddy、AstronStudio 和 QwenWork 的默认执行并发均为 3、最大 8；UI 操作始终只有一路。新机器、新模型或客户端升级后可先显式设为 1 小批量运行。
- Codex Desktop 评分并发：新批次默认 3，最大 8；每题使用独立项目、任务、Browser 和端口。
- 同一批次执行期间不要人工切换模型、权限或关闭正在运行的客户端。

## 候选产物保护

被评测 Harness 结束后，候选网站即被冻结。执行、评分、编排和报告 Agent 都不能修改 `execution/tasks/*/workspace/` 或 `score/tasks/*/workspace/`。

被评测 Harness 在做题过程中自行生成 `node_modules`、`.cache` 或 `.vite` 是正常的，不会单独导致 `execution-receipt.json` 的 `integrity.valid=false`。这些目录保留在 execution 原件中并记录到回执，准备评分副本和生成回传 ZIP 时会自动过滤；用户不需要也不允许手工删除。`.git` 仍属于禁止目录，会使完整性校验失败。

如果站点依赖安装、构建或启动需要写文件，评分 Skill 只会操作 `private-scoring/runtime-workspace/` 副本。只有已经由日志证明的端口冲突，才允许在该运行时副本中受控替换端口；候选原件始终不能修改。

发现候选不合规或哈希漂移时，应保留现场并重新执行该 Harness 单元，不能编辑回执或重算哈希继续评分。

`integrity.valid=false` 表示执行包未通过进入评分阶段的完整性门禁，不等于该题按 0 分计分。流程会停止并保留错误证据；只有生成有效评分结果后才会进入成绩汇总。

## 用户检查清单

开始前：

- [ ] 已安装本场景所需 Skill。
- [ ] 被评测 Harness 的模型、推理强度和权限已经设置。
- [ ] 允许 `run-web-e2e` 自动检查并按需重启 Codex Desktop 和本轮选择的 AstronStudio、WorkBuddy 或 QwenWork 调试模式。
- [ ] 题目包和评分包来自同一批次、同一 Harness。
- [ ] 当前没有需要保留的运行中任务。
- [ ] 已安装该批次随包提供的 Skill，版本和内容 SHA-256 校验通过。

完成后：

- [ ] 控制 Harness 报告执行和评分阶段均已完成。
- [ ] `execution-receipt.json` 完整性有效。
- [ ] 根目录已生成 `submission.json`。
- [ ] 收到了 return ZIP 和外部回执两个文件。
- [ ] 没有通过人工编辑候选网站或状态文件处理错误。

## 常见问题

### 提示自动化依赖安装失败

正常情况下控制 Harness 会自动安装锁定依赖。安装失败时把原始错误交给管理员检查网络或目录权限；不要手工改依赖版本，也不要在题目工作空间安装。

### WorkBuddy 当前模型与预期不一致

停止本批次，确认客户端配置。已经执行的产物不能通过编辑 JSON 更换模型；切换模型后应新建带时间戳的批次重新执行。

### AstronStudio 预检未就绪

确认客户端已登录且桌面已解锁。`run-web-e2e` 会自动检查 `127.0.0.1:9240`，无有效 CDP target 时按需重启 AstronStudio。macOS 默认应用路径为 `/Applications/AStudio.app`；Windows 默认从当前用户安装信息和 `%LOCALAPPDATA%\Programs` 查找 `AStudio.exe`，找不到时在 Prompt 中提供实际主程序路径。停在历史会话时 workspace picker 可以暂时不可见；只要预检整体 `ready=true`，Driver 会新建任务后再选择并回读项目绝对路径。

### Codex Desktop CDP 连接失败

先重新运行 `run-web-e2e` 的桌面 CDP 前置准备；它会复用健康实例，或自动关闭并以调试参数重启 Codex Desktop。若端口被无关进程占用、应用未安装或重启后仍无真实 target，流程会进入 `NEEDS_ATTENTION` 并保留现场。

### Codex Desktop 反复重启且无法停止

若 Codex Desktop 每次打开后又被退出、手工退出也会再次启动，先停止评测。该现象通常是旧版自动化通过 `launchctl submit` 注册了会被 launchd 自动拉起的临时任务，不是 Codex Desktop 自身反复崩溃，也与 “Trust this folder” 提示无关。

在 macOS 终端执行以下止损命令；任务不存在时命令可能返回非零，可继续执行下一条：

```bash
launchctl remove com.wildclawbench.general-e2e.codex-refresh
launchctl remove com.wildclawbench.general-e2e.codex-debug
launchctl bootout gui/$(id -u)/com.wildclawbench.desktop-debug-restart.codex
```

不需要重启电脑。确认 Codex Desktop 已停止反复拉起后，再使用当前 `run-web-e2e` 随包提供的 `scripts/restart_macos_desktop_debug.sh`。新版入口使用固定单实例 Label 和 `KeepAlive=false` 的一次性 LaunchAgent，拒绝与遗留任务或另一轮重启并发；每轮状态与日志保存在 `~/Library/Application Support/WildClawBench/desktop-debug-restart/<run-id>/`，只有 `status.json` 为 `PASSED` 才恢复原评测状态。不要自行改回 `launchctl submit`。

### 控制任务中断或 Desktop 重启

重新打开 ChatGPT 后使用恢复 Prompt。Skill 会查询原有任务和磁盘状态；不要删除状态目录或要求重新创建状态不明的任务。

### 评分任务没有 Browser

确认评分任务由 Codex Desktop 内置任务接口创建，且项目目录是单个 `score/tasks/<task_id>/`。不要使用裸 CLI 或独立 App Server 会话代替 Desktop 评分任务。

### 站点无法启动或 Browser 无法取证

该情况应记录为 `evaluation_error`，不是候选功能全部为零。保留错误和现场，由管理员决定是否重试基础设施。

### 流程进入 `NEEDS_ATTENTION`

让控制 Harness说明具体阻塞原因，并只处理该原因。未知授权、身份不一致、候选漂移、原任务终态不明或依赖安装失败都不能跳过门禁。
