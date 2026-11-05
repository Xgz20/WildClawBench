# AgentCube 沙箱端到端评测

执行入口为 `eval/run_e2e.py`，实现位于 `src/e2e/`。当前驱动覆盖 Windows AStudio，任务来源支持已登记 General 数据集和仓库 Web 任务。执行结果交给现有 General/Web 评分 Skill。流水线入口消费逐题就绪记录，评分状态独立保存。

## 1. 执行顺序

1. 本机 Python 解析数据集范围、配置单元和多 run，冻结题目、公开素材、私有评分材料及兼容 Skill。
2. 本机调用 AgentCube API，每个用例的每次 run 创建独立 Windows 沙箱。
3. 本机通过沙箱 Linux PicoD 执行 wgui CLI，等待 `vm health` 返回 `wgui.v2`，把公开文件上传到 Windows 工作区。
4. 本机构造 RunRequestV2，注入 Prompt、模型、推理强度和 `timeout_sec`，启动可恢复的远端 `task run` job。
5. 本机持续观察原 job，取得终态报告，再核对受管 AStudio 进程静默和原生轨迹稳定性。控制器超时返回后，产品仍可能继续写文件，终态报告本身不能证明进程已经停止。
6. 本机主动执行 `task collect`，下载 Windows Workspace、产品诊断、原生 rollout 和 ATIF，并验证 collect manifest 中的文件大小与 SHA。
7. 本机按 Prompt、cwd、原生 session/turn、模型和推理强度绑定本题，归一化完整工具调用与返回，封存原件，生成并逐成员验证 ZIP 备份。
8. 备份通过后发布 `execution-ready.json` 并进入评分队列。沙箱销毁确认前继续占用执行并发槽。
9. Codex 控制聊天领取已就绪题，为本题生成独立评分工作空间，接续冻结的现有 General/Web 评分编排器。执行和评分可并行。
10. 单题 submission 验证后释放评分槽，按完整 unit/run 范围合成结果索引，报告阶段继续使用对应场景 Skill。

ATIF 的 `converted` 单独保留。当前验收观察到 ATIF 可能只有用户与助手消息，工具轨迹以绑定后的原生 rollout 为来源。资源统计保留报告及原生累计值和覆盖状态。Windows 与控制器时钟分别保存。

## 2. 认证与运行

使用仓库 Python 环境，需要已有的 `requests`、`PyYAML` 等项目依赖。认证 token 由环境变量 `AGENTCUBE_AUTH_TOKEN` 注入。非敏感配置可写为以下 JSON。

```json
{
  "app_id": "AstronEval",
  "user_id": "xgzhu6",
  "trust_env": false,
  "active_ttl": 10800,
  "expire_ttl": 14400
}
```

内网端点默认直连。需要继承系统代理时显式设置 `trust_env=true`。

以下命令在 evaluator checkout 根运行。`--workspace-root` 使用评测数据目录。调试和验收可使用本机 debug-workspace，生产分发数据使用项目约定目录。

```bash
.venv/bin/python eval/run_e2e.py run \
  --workspace-root /absolute/evaluation-root \
  --batch-id astudio-general-001 \
  --scenario general --dataset general-custom70-v3 \
  --task-id 02_Office_task_005_xiaohongshu_psychology_note_pack \
  --harness astronstudio --model spark-x2.6 --reasoning-effort high \
  --agentcube-config /absolute/agentcube-identity.json \
  --concurrency 3 --runs 1 --timeout-override 2400 --jsonl
```

加 `--dry-run` 可准备冻结批次并查看任务数。已准备批次执行使用 `resume` 和同一 batch-id。恢复保持冻结参数。

```bash
.venv/bin/python eval/run_e2e.py resume \
  --workspace-root /absolute/evaluation-root --batch-id astudio-general-001 \
  --agentcube-config /absolute/agentcube-identity.json --jsonl

.venv/bin/python eval/run_e2e.py status \
  --workspace-root /absolute/evaluation-root --batch-id astudio-general-001
```

创建或任务派发的结果不确定时，状态为 `NEEDS_ATTENTION`，本地保留远端 job 和 session 身份。`resume` 沿原身份观察。终态业务错误保留诊断和备份，评分状态体现实际缺口。

### 参数

| 参数 | 行为 |
| --- | --- |
| `--scenario general/web/all` | 选择场景，General 和 all 需要显式数据集 |
| `--dataset` | General 已登记数据集 ID |
| `--task` / `--task-id` / `--category` | 选择单题文件、题目 ID 或分类，三类入口互斥，后两者可重复 |
| `--tag` / `--exclude-tag` / `--modality` | 筛选分类或场景范围，modality 支持 pure-text 和 multimodal，显式单题/ID 保持其指定范围 |
| `--harness` | 当前支持 astronstudio，驱动注册点为 backend.DRIVERS |
| `--model` | wgui 内置模型 ID，执行后核验原生 turn_context |
| `--reasoning-effort none/high/max` | 转换为 wgui 的 None/High/Max，并核验实际值 |
| `--concurrency` / `--parallel` | 批次执行并发，默认 3，未确认释放的沙箱仍占槽 |
| `--runs` | 每题独立执行次数，默认 1 |
| `--timeout-override` | 正整数秒，默认 10800，覆盖本次调用所有 unit 的 wgui timeout_sec |
| `--scoring-mode streaming/batch` | 默认 streaming，batch 等执行范围进入终态后准入评分 |
| `--scoring-concurrency` | 默认 3，支持 1–8，独立于执行并发 |
| `--template` | AgentCube 模板，默认 winarena-pc-20261104-a |
| `--plan` | JSON 多配置单元计划，可与并发、runs、timeout 等全局覆盖参数组合 |

超时优先级为 CLI `--timeout-override`、unit.timeout_override、计划顶层 timeout_override、默认 10800。它用于被测客户端执行预算，评分规则原有超时独立保存。预检要求平台 `expire_ttl >= timeout_override + 2400`，留出启动、采集和回收时间。超时覆盖到所有配置单元后逐项核验。

General 的非空 Env、Skills、Warmup 等要求需要相应沙箱驱动能力。当前未覆盖的运行时要求在创建沙箱前返回明确预检错误。

## 3. 多模型、多 Harness 与多 run

```json
{
  "schema_version": "wildclawbench.sandbox-batch-plan/v1",
  "batch_id": "astudio-model-comparison-001",
  "selection": {
    "scenario": "web",
    "task_ids": ["07_Website_Generation_task_002_focus_pomodoro_clock"]
  },
  "execution_concurrency": 3,
  "scoring_concurrency": 3,
  "scoring_mode": "streaming",
  "timeout_override": 3600,
  "runs": 2,
  "units": [
    {"harness": "astronstudio", "model": "spark-x2.6", "reasoning_effort": "high"},
    {"harness": "astronstudio", "model": "spark-x2.6", "reasoning_effort": "max"}
  ]
}
```

```bash
.venv/bin/python eval/run_e2e.py run \
  --workspace-root /absolute/evaluation-root \
  --plan /absolute/plan.json --agentcube-config /absolute/agentcube-identity.json
```

整个批次共用执行并发预算，各 unit 轮转补位，支持 unit.max_concurrency。unit 身份包含场景/Profile、Harness、模型、推理强度、模板和配置摘要。其他 Harness 可通过驱动扩展接入，当前选择未交付驱动会返回 `SANDBOX_DRIVER_UNAVAILABLE`。

同一 workspace 的不同 batch-id 独立保存，可以并行准备和执行。相同 batch-id 的新 run 返回冲突，恢复通过 `resume` 读取原冻结计划。两个进程同时准备或执行同一批次时由内核文件锁互斥。

## 4. 工作目录和备份

```text
<workspace-root>/
  workspace.json
  control/resources.sqlite                  # 跨批次 Web 评分端口登记
  batches/<batch-id>/
    batch.json                              # 冻结完整范围、units、runs、参数和来源
    selection.json                          # 筛选条件及入选任务
    inputs/<dataset-or-profile>/tasks/<task-id>/
      execution/                            # 允许上传的 Prompt 和公开 Workspace
      private-scoring/                      # 私有评分契约和 GT
    inputs/compatibility/                    # 冻结现有场景 Skill、发行包和数据集
    control/state.sqlite                    # 事务状态、远端 job、评分领取和事件
    control/events.jsonl                    # 可按游标消费的执行事件
    units/<unit-id>/runs/run-0001/
      tasks/<task-id>/
        executions/<execution-attempt-id>/
          staging/                          # 下载、核验过程数据
          original/                         # 封存原件，保留原始字节并移除写权限
          backups/execution-original.zip    # 独立备份
          backups/backup-receipt.json        # 成员、身份及摘要回执
          execution-ready.json              # 封存和备份成功后的逐题交接记录
        restores/generation-*/              # 经验证的新恢复副本
        restores/current.json               # 当前读取副本，绑定原备份 SHA
        scoring/score-<claim-id>/
          source.json                       # 父批次、原执行、备份与领取身份
          execution-source/                 # 从备份恢复的本题证据
          unit/                             # 现有场景标准 execution/scoring 根
          packages/                         # General 本题标准包
          orchestrations/                   # General 现有编排器状态与独立 attempt
      submission/submission.json            # 该 unit/run 的完整标准结果
      submission/selected-results.json      # 包括执行失败、未评分的完整范围索引
    selected-results.json                   # 全批次选择和来源锁
    batch-summary.json
```

Web 编排状态位于单题标准 unit 内的 `score/.orchestrate-web-e2e/`。General 使用 `orchestrations/`。单题评分候选独立复制，现有评分 Skill 管理依赖、build 和运行服务目录。

原件文件清单包含空目录。先封存，再建立 ZIP，重新读取每个 ZIP 成员验证大小和 SHA，回执成功发布后才入队。远端归档使用 `strict_timestamps=False` 兼容早于 1980 年的文件时间戳，文件内容按原字节校验。已派发任务收集或备份失败时保留原沙箱，状态为 NEEDS_ATTENTION，便于继续采集。失败收集也会抓取已变化的原生 rollout，并标记其实际覆盖和终态核验缺口。

已派发任务的失败收集先按 executable、PID、创建时间与进程树归属停止受管 AStudio，通过 5 秒静止核验后再抓取原生轨迹和 Workspace。恢复使用独立的 `failure-quiesced-task-collect` job 与目录，保留此前活跃期间的失败快照；清理核验失败时继续保留沙箱。失败材料收全后封存、释放，业务状态仍为 FAILED，不发布成功就绪记录。

### 恢复

```bash
.venv/bin/python eval/run_e2e.py restore \
  --workspace-root /absolute/evaluation-root --batch-id astudio-general-001 \
  --execution-key '<unit-id>/run-0001/<task-id>'
```

恢复校验原 ZIP，生成新的只读 generation 并切换 current.json。消费前再次验证恢复副本及原备份绑定。原污染数据和历史评分上下文保留。执行控制器或本题活动评分仍持锁时，恢复返回冲突。

此入口恢复执行证据源。已建立的评分 attempt 继续使用其冻结候选。评分 attempt 的运行时污染按对应场景 Skill 的恢复契约处理。

### 分发

```bash
.venv/bin/python eval/run_e2e.py export \
  --workspace-root /absolute/evaluation-root --batch-id astudio-general-001 \
  --execution-key '<unit-id>/run-0001/<task-id>' \
  --purpose results --output /absolute/share/results.zip

.venv/bin/python eval/run_e2e.py export \
  --workspace-root /absolute/evaluation-root --batch-id astudio-general-001 \
  --purpose scoring --output /absolute/share/scoring.zip

.venv/bin/python eval/run_e2e.py import \
  --workspace-root /absolute/recipient-root \
  --archive /absolute/share/scoring.zip --receipt /absolute/share/scoring.zip.json
```

选择参数还支持 `--unit-id` 和 `--run-index`。results 包保存已封存原始结果和诊断。scoring 包另含私有契约、GT、本题标准评分输入和冻结 Skill。导入验证外层完整性和内层执行备份，生成本地绝对路径映射。同一原包重复导入会复核已导入文件后返回 already_imported。接收方从 import-receipt.json.scoring_contexts 取得 context_root 和 installed_skills，按冻结场景 Skill 初始化本机评分编排。

## 5. 执行和评分并行

`execute-sandbox-e2e` Skill 包装公开 Python CLI。`orchestrate-e2e-pipeline` Skill 使用同一批次的持久化队列，既可接续用户已启动的脚本，也可跟随执行 Skill 启动的进程。

```bash
.venv/bin/python eval/run_e2e.py pipeline \
  --workspace-root /absolute/evaluation-root --batch-id astudio-general-001 \
  next-actions --owner <control-chat-id> --after-cursor 0 --wait-seconds 20
```

按 recommended_actions 执行 prepare-context、init-orchestration 和 poll，后续持续携带 execution-key、claim-id 和 owner。现有下层编排器每题配置一槽，父队列统一控制评分并发。原生评分聊天、Browser 预检、规则 Worker 和验分遵循冻结场景 Skill。

```bash
.venv/bin/python eval/run_e2e.py pipeline \
  --workspace-root /absolute/evaluation-root --batch-id astudio-general-001 \
  record-submission --owner <control-chat-id> \
  --execution-key '<unit-id>/run-0001/<task-id>' --claim-id <claim-id>

.venv/bin/python eval/run_e2e.py pipeline \
  --workspace-root /absolute/evaluation-root --batch-id astudio-general-001 compose
```

compose 要求执行资源已释放、评分领取已收口，按冻结题序合成各 unit/run。General unscored 保留基础设施失败及超时。Web 标准 submission 依赖完整评分回执，缺失情况保留在完整 selected-results 索引。报告阶段沿用原 report Skill 的配置、回传包和发布契约。

Web 单题审计 submission 可以包含 `evaluation_error`。父队列在验证后保留该文件与摘要，评分状态记为 FAILED，完整范围索引保留 unscored 和评分错误；美观度基础设施错误也采用这一准入规则。旧 Web finalizer 的异常总分占位 0 不作为有效能力分数。原生线程终态与下层审计收口仍须先完成。

owner 迁移使用 takeover，并提供 previous-owner 和 reason。已有原生线程继续沿原身份接续，迁移回执会标出需要核对的旧线程。

新执行进程每 5 秒更新 owner 心跳，租约为 120 秒。评分控制会话通过 next-actions 和本题控制动作续约。status 的 controllers 字段给出 fresh、stale、released 或 unknown。活动评分 claim 在租约过期后继续占槽，接管使用显式 takeover。空闲过期 owner 被接续后，旧 owner 的后续领取会被拒绝。旧批次缺少心跳字段时显示 unknown。

## 6. 验证范围

截至 2026-11-04，最新 BVT POC 已验证正确答案、产物与原生轨迹下载、manifest SHA、独立备份及平台释放。正式入口已完成一题 General 的执行、原沙箱恢复收集、备份分发和标准评分交接，规则评分 Worker 已接续。语义评分和完整报告仍需按原生评分 Skill 完成验收。

第一轮 Web 产品驱动返回 product_error，已作为失败原件保留。第二轮 Web 在本次自定义的 2400 秒预算处返回 host_timeout。收集文件的时间戳早于 1980 年，导致旧实现 ZIP 归档失败，旧失败收口逻辑随后释放了沙箱，工作区未下载。终态报告与此前下载的 212 条原生事件作为部分证据封存，包含 51 次工具调用及 51 次返回，未观察到原生完成事件。分发包保留原失败档案和独立补充档案。

上述 ZIP 时间戳问题、失败收集保全门禁已修复并增加回归。Web 单题标准包、执行记录、轨迹、资源指标及现有编排器初始化已通过合成执行夹具验证。真实 Web 成功态、原生语义评分及完整报告仍待验收。十任务并发槽位、断点恢复和污染检测已有合成测试，真实十路容量验收另行留证。

本指南引用的正式入口为 `eval/run_e2e.py`，协议与备份实现分别见 `src/e2e/backend.py`、`src/e2e/artifacts.py`，现有场景适配见 `src/e2e/handoff.py`。设计文件保留在 `docs/design/e2e-sandbox/` 的 v1、v2，BVT、接口指南及 POC 运行记录按本地参考资料管理。

2026-11-05 的 3600 秒 Web 验收已完成执行、采集、备份、恢复、分发和标准评分交接，本机及接收方编排器均到达 REGISTER_PROJECT。窗口报告起终时间差约 35 分 08 秒，原生轨迹为 352 个事件、69 次工具调用。评分候选为 34 个文件，原始 Workspace 连同依赖完整封存。

生产盘点结论为受控试运行阶段。评分报告闭环、真实并发、多 run、异常恢复与版本发行仍需完成验收。当前实际驱动覆盖 AStudio，实机联调组合为 spark-x2.6/high。本轮沙箱回归 52 项、远端与旧本地收集 Node 回归 31 项通过。

本机附加元数据按原归档或原文件目录识别并独立保存，来源已声明文件保留。下载、还原和评分输入在写入时建立只读保护，分发包再次核验逐成员摘要。分发中间目录清理失败时保留该目录并写入 cleanup 回执，已发布包与正式回执继续可用。

2026-11-05 后续五题实测已验证三路独立沙箱执行、三路 General 原生评分及执行评分重叠，三路评分共同活动 128.384 秒。结果为 4 题执行完成、1 题 3600 秒超时；3 题有效评分、1 题 Web 评分异常、超时题未评分。Web 异常涉及公开 Browser 缺少测试时钟、无法确认页面隐藏，以及一次未恢复预设的检查；未将其记为能力零分。五份备份校验、整批执行包跨目录导入均通过，沙箱全部释放，沙箱 Python 回归 57 项通过。三路 Web Browser、多 run、完整 Web 有效评分与报告仍待验收。完整记录见 `/Users/gzx/debug-workspace/e2e-sandbox-evaluate/reports/五题执行3并发评分3并发实测记录-20261105.md`。
