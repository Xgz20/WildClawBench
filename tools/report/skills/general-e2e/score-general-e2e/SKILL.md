---
name: score-general-e2e
description: 对一个冻结的 General E2E 任务运行自动规则与指定语义裁判，生成证据可追溯的标准评分；不负责批量调度、执行 Harness 或报告汇总。
---

# 评分 General E2E 单题

新轮次的 prepare 必须将该题完整 trace 包复制到评分 attempt 的 trace/，包括标准 transcript、trace-index、原始日志与绑定证据。attempt-manifest.trace_bundle 锁定 SHA，verify 每次核验；private/transcript.jsonl 必须与交接的标准轨迹一致。新 CLI 缺少 trace-index 时拒绝，只有旧冻结证据显式 --legacy-transcript-only 或经审核的失败产物契约可按旧口径处理。

语义证据目录包含 raw_trace 与 trace_index，按 catalog/file 分页核验原始会话。不要仅以桌面投影缺少某条工具事件断言没有调用。后补轨迹不得冒充旧裁判已经读取；重评分创建新 attempt，复制并复核完整 trace 包。

完成后归档不需要保留 runtime。`verify-score --archived` 仍校验冻结候选、评分、原件和回执 SHA，并按当前规则复核审核证据内容；历史策略标识保持原回执值。正常评分继续强制 runtime 与当前策略版本。

在独立评分工作空间中完成单题规则分、语义分、合分和评分审计。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name score-general-e2e --json
```

当前 `0.10.0/operational` 已提供不依赖 Docker 的私有评分目录、本地受管规则 Worker、`codex-agent-judge-v1` 证据查询，以及 `api-judge-v1` 的 Anthropic Messages、OpenAI Chat Completions、OpenAI Responses 三种 transport、重试与独立审计；两类语义结果均经过结构化校验、中文理由门禁、合分审计和 `verify-score`。自动规则组件会为每个检查点记录中文分值解释，并绑定冻结规则源码、候选清单、轨迹与 Worker 原始返回键值。终态评分可复用冻结候选创建独立重评分 attempt；题目 `timeout_seconds` 与控制线程 deadline 不进入能力评分 Rubric。G4-03 已完成固定 `gpt-6-astra/high` 的三题真实 Codex 语义评分并纳入五题闭环；该生产状态不表示 Windows 或其他 Harness 已验收。

评分 Prompt 必须冻结并显式给出本 Skill 根、入口、版本和入口 SHA；不得从项目或仓库中的同名 Skill 猜测入口。普通生产运行的 manifest 不含 validation 标记；显式验收运行仍要求 Prompt 的 acceptance ID 与 `attempt-manifest.json` 完全相同。两种模式都不得省略证据查询、反例检查、合分或 `verify-score`。

## 责任边界

`0.10.0` 支持两类显式证据政策。`references/reviewed-evidence-policy.json`按冻结契约SHA审核输出型任务所需证据，允许非必需工具轨迹缺口，仍核验原生会话、Prompt、原始trajectory、最终回复及候选。`references/reviewed-failure-evidence-policy.json`只为已审核的输出契约准入有原生失败证明的`candidate_error`；证明绑定原记录、状态、候选、Prompt和文件SHA，不写死某次运行ID。采集器不决定分数，缺产物仍由原规则和Judge判断。保护确认阻断、未知发送和基础设施错误不进入这个原生失败评分准入分支。

原有自动规则准入仍保留：纯 automated 规则的 `grade(**kwargs)` 仅以常量键 `workspace_path` 读取输入、无动态/转交参数、无轨迹或回复引用时，可接受带绑定原始证据的 partial 工具轨迹。候选及原始/标准轨迹SHA必须有效，回执不改成complete。除此推断分支外，hybrid/llm_judge只有命中上述审核政策且通过独立证据核验时才准入。读取缺失轨迹的规则、未知参数形式和缺身份/候选仍拒绝。

`0.8.4` 对冻结 Prompt 明确映射 `/tmp_workspace → ./workspace`、且候选仅在嵌套 `workspace/results/` 产出文件的任务，按已核验的 Prompt SHA 将该目录作为规则 Worker 的逻辑 `/tmp_workspace`。候选原件不改动；attempt manifest、规则审计和语义请求均记录实际路径。若根目录与嵌套目录同时有结果，直接拒绝路径歧义。语义裁判须按 [Codex 语义评分协议](references/codex-agent-judge.md)引用原始路径并评价内容，不因已证明的映射多出一层目录而扣交付位置分。

`0.10.0` 仅对第 58 题已冻结且 SHA 精确匹配的旧规则应用经审核的缺失 `recipient_id` 修正。Worker 请求使用修正源码，原 contract 保持不可变；独立修正记录、规则审计、检查点证据和标准评分均绑定原始与实际执行源码 SHA，`verify-score` 逐项复核。其他任务或源码 SHA 不匹配时不应用修正。

- 输入：单题评分工作空间、冻结候选/轨迹和裁判配置。
- 输出：自动规则分、语义分、证据引用、评分审计和标准 `score.json`。
- 保持任务原规则、rubric、权重和分值锚点；缺证据时保留未判定或评测错误。
- 语义判断必须引用可定位证据，长轨迹可分页回查，不能只用截断摘要替代原文；每个 Rubric 检查点的理由必须用中文说明为何采用当前分值锚点，满分、零分、部分分和未判定都不能省略。
- 不创建下一题任务，不重跑被测 Harness，不聚合跨题结果。

候选没有生成预期产物、产物为空或内容错误时，按冻结 rubric 和可定位证据给出零分、部分分或合法 unresolved；这是被测能力结果，不是终止控制会话或整批评分的理由。不得补造产物、修改候选、让控制器另开评分会话或重跑 Harness。若出现 `Selected model is at capacity. Please try a different model.`，保留当前评分 task；Codex 自身在同一任务内最多重试 5 次，外层不得创建替代会话或切换模型。

## timeout_seconds 与评分边界

任务或执行配置中的 `timeout_seconds` 是运行时/编排参数，不是评分 Rubric。除非任务 Rubric 明确把时长作为可观察产出，否则不得因为超过该时长直接扣分、补零或把能力分改成 `0.0`；评分只依据冻结候选、轨迹和 Rubric 证据。执行确实超时且无法确认终态、候选或必要证据时，按评测异常/未评分处理，仍不能冒充能力零分。

评分控制器的 thread deadline 同样属于运行安全边界，与题目评分标准分离。若线程最终已确认 `COMPLETED` 且冻结 `score.json` 通过 `verify-score`，控制任务可在保留迟到审计的前提下显式执行 late-completion recovery；未知终态、证据缺失或 `verify-score` 失败时禁止恢复。

## 已交付能力与边界

需要开发、校验或接入评分 core 时，读取[评分 core 接口](references/grading-core.md)。当前四个公开 API 可用于确定性契约验证和受管 backend 接入；`run_rules()` 不会自行执行不可信规则，`evaluate_semantics()` 也不会自行调用模型。

需要准备、复核或执行本地规则时，读取[本地受管规则运行时](references/local-rule-runtime.md)，使用 `scripts/score_general_e2e.py`。该入口强制候选原件只读、一次性 runtime 副本、GT 后置、真实本机 workspace 路径、冻结 transcript、专用虚拟环境、环境白名单、超时、独立进程组和进程树清理；不得要求 Docker。规则 v2 逐项理由是确定性分值锚点解释，业务判定依据来自随项落盘的可复算证据，不得调用模型替自动规则补写或改判。

在控制 Harness 的独立评分会话中执行默认语义协议时，读取[Codex 语义评分协议](references/codex-agent-judge.md)。必须先生成冻结证据目录，再通过 `query-evidence` 分页回查；逐项结果只能引用已查询的 evidence ID，并声明已检查支持证据和反例。声称“未发生”时必须用无过滤分页覆盖完整 transcript。缺证据保留 `unresolved`；导入后由 core 校验分值锚点、引用、Judge 身份和请求锁，再合成标准 `score.json`。`verify-score` 会重新校验来源锁并从冻结组件重算标准分，不只比对结果文件自带的哈希。

显式选择 API 后端时，读取 [API Judge 评分协议](references/api-judge.md)。使用 `prepare --api-runtime-config ...` 冻结 provider、endpoint、模型、输入/输出预算、timeout、重试与凭据环境变量名；凭据值只能由运行环境注入。`run-api-score` 可恢复地完成规则、语义请求、合分和校验，API 最终失败形成合法 `evaluation_error / total_score=null`，不会补零、切换模型或回退到 Codex。

需要对有效分或合法评测异常重新评分时，读取[独立重评分 attempt](references/rescore.md)。重评分只复制冻结候选与评分输入，重建干净 runtime，并显式冻结新的 Judge 配置；不得复用 attempt ID 或修改源评分目录。

G4-03 的五题验收与 G3-05 的真实 API Judge smoke 已完成双后端准入。后续 Windows、60 题全量和裁判校准仍按各自验收项独立留证，不能由本状态自动推导。
