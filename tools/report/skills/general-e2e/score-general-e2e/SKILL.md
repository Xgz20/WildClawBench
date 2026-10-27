---
name: score-general-e2e
description: 对一个冻结的 General E2E 任务运行自动规则与指定语义裁判，生成证据可追溯的标准评分；不负责批量调度、执行 Harness 或报告汇总。
---

# 评分 General E2E 单题

`0.17.0`补齐DOCX结构证据：保留原段落/物理单元格定位，增加声明网格、合并区间、重复表头与正文/单元格到脚注和尾注的实际关系链。引用绑定部件SHA和内容定位，缺关系、缺部件、缺注释及外部关系分别标记；不访问外部资源。结构声明不能证明渲染、可编辑性或显示编号，嵌套表拓扑尚不展开。新DOCX引擎为`wildclawbench.docx-text/v1`，旧attempt继续使用冻结入口。详见[原生文件文本证据](references/native-text-evidence.md)。

`0.16.0`增加冻结静态图片证据：完整解码PNG/JPEG/WebP/单帧GIF，保留原始字节与SHA，不做OCR、裁剪或重编码。Codex裁判用`query-evidence --mode image`取得核验后的实际图片路径，再用看图工具检查像素；catalog或路径元数据不能证明已看图。API配置可显式增加冻结`image_input`，三种transport发送带evidence ID的原字节内容块，图片预算与文本字符预算分开。缺图/省略不能充当视觉依据，缺依赖与来源漂移保留异常。归档复核附件原字节及保存的provider请求，不要求解码器存在。使用前读[冻结图片证据](references/image-evidence.md)。

`0.15.0`增加PPTX内嵌XLSX的可归档重算链：提取回执绑定冻结PPTX、部件名及原始工作簿SHA，随后清缓存重算的输入可追溯到该部件；原始副本、派生文件与两层回执都保留。归档复核重新比对包内原字节，不要求引擎存在。规则依赖目录新增可选pdfplumber/pypdf，实际Worker锁必须声明并通过版本/导入探测；默认3.11安装Profile不因此自动包含它们。详见[内嵌表格重算](references/office-recalculation.md#内嵌表格重算)。

`0.14.0`增加PPTX可信PDF渲染：任务声明`scoring_runtime: {office: true, office_render: true}`，通过`bootstrap-office-render`冻结独立的Office/字体锁，含明确字体文件及目录成员。Worker在一次性副本上运行固定PDF导出，保留源PPTX、PDF、字体清单与导出选项的绑定；语义证据和归档校验接收派生PDF及回执。缺锁、字体漂移或引擎失败保持评测异常；缺交付由原任务规则判断。PDF转换本身不证明字号、遮挡、图表语义或目标应用可编辑性。使用前读[可信PPTX渲染](references/office-rendering.md)。

`0.13.0`增加PPTX原生文本证据：按presentation关系顺序读取幻灯片、分组文本、原生表格、独立标记的备注、图表存储缓存及嵌入XLSX单元格。图表缓存和嵌入表格保留各自值、定位和SHA，不假定二者一致；外部数据关系不跟随。独立裁判查询、API输入及legacy Workspace证据共用该离线提取器。显式字号只作为原始结构记录，不证明继承后的字号、文字溢出或可编辑应用行为。使用前读[原生文件文本证据](references/native-text-evidence.md)；PPTX版式及图像仍需单独渲染/视觉证据。

`0.12.0`增加显式Office评分运行时：任务声明`scoring_runtime: {office: true}`时，先冻结可信LibreOffice的绝对路径、版本与可执行文件SHA，再由受管Worker重算一次性XLSX副本。所有公式缓存先清空，原件保持不变，派生文件与回执进入语义证据及归档核验。缺引擎、漂移或重算失败不补候选零分；漏交文件仍按任务契约计分。使用前读[可信Office重算](references/office-recalculation.md)。文本投影本身仍不计算公式。

`0.11.0`增加DOCX、XLSX、文本PDF的冻结文本证据投影。`query-evidence --mode file`对这些文件按原生记录分页，保留段落、表格单元格、工作表地址或PDF页定位，并记录原文件SHA、投影SHA及提取边界；API Judge同样接收正文/单元格内容。该能力不解释图片/图表、不重算公式，也不证明原生应用可用性。PDF须在评分CLI解释器环境具备pypdf，缺依赖会显式阻断，不按候选零分处理。使用前读[原生文件文本证据](references/native-text-evidence.md)。历史attempt继续使用原冻结入口，不用新投影改写旧证据。

`0.10.9` 随Skill分发[离线页面观察脚本与协议](references/offline-browser-validation.md)。新版编排在HTML候选评分前验证公共浏览器runtime并冻结judge-environment.json；独立裁判使用禁网字节观察及真实截图验证原Rubric，不依赖被URL策略拒绝的file导航，不绕过安全策略，不把环境故障变成候选能力分。评分core、Worker、原规则及证据政策未改变。

正式语义评分使用独立项目中的独立单题聊天，不能用控制会话或协作子代理替代。纯 automated 任务继续由受管规则 Worker 评分。

新编排的 v6 Prompt 冻结 Python 绝对路径、版本与制品 SHA，并给出 `score_cli_argv_prefix` 和 `skill-metadata.json` 的绝对路径及 SHA。实际命令必须使用该 argv 前缀（含 `-X utf8`），不依赖 python/python3 别名。独立分发包直接核验这份元数据的 name/version/implementation_status，无需导入仓库模块；下面的模块能力命令仅用于仓库开发环境。

语义响应使用文件编辑工具写为新的 UTF-8 JSON 文件。临时 Python 脚本须先保存为 UTF-8 文件并声明 `# coding: utf-8`，使用冻结解释器运行；不得直接执行含中文源码的 stdin/heredoc。所有文本读写显式指定 UTF-8，CLI 的 JSON 标准输出和错误输出也固定 UTF-8。旧冻结 attempt 和 Prompt 按原版本复核，不改写历史结果。

已按精确冻结契约审核同事请假私信、品牌命名方向两题的纯回复评分输入，见 `references/reviewed-fast-output-evidence-audit.json`。这些 Profile 可使用已绑定最终回复和候选保留可选工具轨迹 partial；安全安装脚本题需要完整执行轨迹证明未发生行为，未加入该例外。

新轮次的 prepare 必须将该题完整 trace 包复制到评分 attempt 的 trace/，包括标准 transcript、trace-index、原始日志与绑定证据。attempt-manifest.trace_bundle 锁定 SHA，verify 每次核验；private/transcript.jsonl 必须与交接的标准轨迹一致。新 CLI 缺少 trace-index 时拒绝，只有旧冻结证据显式 --legacy-transcript-only 或经审核的失败产物契约可按旧口径处理。

语义证据目录包含 raw_trace 与 trace_index，按 catalog/file 分页核验原始会话。不要仅以桌面投影缺少某条工具事件断言没有调用。后补轨迹不得冒充旧裁判已经读取；重评分创建新 attempt，复制并复核完整 trace 包。

完成后归档不需要保留 runtime。`verify-score --archived` 仍校验冻结候选、评分、原件和回执 SHA，并按当前规则复核审核证据内容；历史策略标识保持原回执值。正常评分继续强制 runtime 与当前策略版本。

在独立评分工作空间中完成单题规则分、语义分、合分和评分审计。

新 Codex 评分 attempt 默认模型和推理档位为 `gpt-6.1-sol/high`，显式配置优先；已有 attempt 和 API Judge 的冻结身份保持原样。

## 当前能力门禁

先运行：

```bash
python3 -m eval_general_e2e skills --name score-general-e2e --json
```

当前 `0.10.8/operational` 已提供不依赖 Docker 的私有评分目录、本地受管规则 Worker、`codex-agent-judge-v1` 证据查询，以及 `api-judge-v1` 的 Anthropic Messages、OpenAI Chat Completions、OpenAI Responses 三种 transport、重试与独立审计；两类语义结果均经过结构化校验、中文理由门禁、合分审计和 `verify-score`。自动规则组件会为每个检查点记录中文分值解释，并绑定冻结规则源码、候选清单、轨迹与 Worker 原始返回键值。终态评分可复用冻结候选创建独立重评分 attempt；题目 `timeout_seconds` 与控制线程 deadline 不进入能力评分 Rubric。G4-03 已完成固定 `gpt-6-astra/high` 的三题真实 Codex 语义评分并纳入五题闭环；该生产状态不表示 Windows 或其他 Harness 已验收。

评分 Prompt 必须冻结并显式给出本 Skill 根、入口、版本和入口 SHA；不得从项目或仓库中的同名 Skill 猜测入口。普通生产运行的 manifest 不含 validation 标记；显式验收运行仍要求 Prompt 的 acceptance ID 与 `attempt-manifest.json` 完全相同。两种模式都不得省略证据查询、反例检查、合分或 `verify-score`。

## 责任边界

`0.10.8` 在契约评分准入前核验 AstronStudio HTTP 402 `astron_points_exhausted` 的原生失败证明、原记录/状态/候选/Prompt SHA、完整会话身份及错误绑定。核验通过返回独立阻断错误 `EXECUTION_EXTERNAL_QUOTA_EXHAUSTED`，停止评测等待人工恢复和明确恢复指令；不得进入普通 `EXECUTION_NOT_SCORABLE → UNSCORED` 继续路径，不记能力零分、不创建 Judge、不自动重发。证明损坏继续返回 `EXTERNAL_QUOTA_EVIDENCE_INVALID` 并停止。其他原生失败仍走原审核契约；历史候选、评分、回执和冻结发行保持不变。

partial 执行证据必须显式列出缺失项，空列表不得按 standard 准入。`native-tool-capture-incomplete` 仅能由已经验证的 Workspace-only automated 规则按 `automated-workspace-only/v1` 使用；不得因此放行 hybrid、llm_judge 或消费轨迹的自动规则。身份、候选稳定性、原始文件和 SHA 门禁保持有效；旧冻结评分 attempt 不重写。

`0.10.1` 支持两类显式证据政策。`references/reviewed-evidence-policy.json`按冻结契约SHA审核输出型任务所需证据，允许非必需工具轨迹缺口，仍核验原生会话、Prompt、原始trajectory、最终回复及候选。`references/reviewed-failure-evidence-policy.json`只为已审核的输出契约准入有原生失败证明的`candidate_error`；证明绑定原记录、状态、候选、Prompt和文件SHA，不写死某次运行ID。采集器不决定分数，缺产物仍由原规则和Judge判断。保护确认阻断、未知发送和基础设施错误不进入这个原生失败评分准入分支。

原有自动规则准入仍保留：纯 automated 规则的 `grade(**kwargs)` 仅以常量键 `workspace_path` 读取输入、无动态/转交参数、无轨迹或回复引用时，可接受带绑定原始证据的 partial 工具轨迹。候选及原始/标准轨迹SHA必须有效，回执不改成complete。除此推断分支外，hybrid/llm_judge只有命中上述审核政策且通过独立证据核验时才准入。读取缺失轨迹的规则、未知参数形式和缺身份/候选仍拒绝。

`0.8.4` 对冻结 Prompt 明确映射 `/tmp_workspace → ./workspace`、且候选仅在嵌套 `workspace/results/` 产出文件的任务，按已核验的 Prompt SHA 将该目录作为规则 Worker 的逻辑 `/tmp_workspace`。候选原件不改动；attempt manifest、规则审计和语义请求均记录实际路径。若根目录与嵌套目录同时有结果，直接拒绝路径歧义。语义裁判须按 [Codex 语义评分协议](references/codex-agent-judge.md)引用原始路径并评价内容，不因已证明的映射多出一层目录而扣交付位置分。

`0.10.1` 仅对第 58 题已冻结且 SHA 精确匹配的旧规则应用经审核的缺失 `recipient_id` 修正。Worker 请求使用修正源码，原 contract 保持不可变；独立修正记录、规则审计、检查点证据和标准评分均绑定原始与实际执行源码 SHA，`verify-score` 逐项复核。其他任务或源码 SHA 不匹配时不应用修正。

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

需要开发、校验或接入评分core时，读取[评分core接口](references/grading-core.md)。四个主要评分API及原生文本提取辅助API用于确定性契约验证和受管backend接入；`run_rules()`不会自行执行不可信规则，`evaluate_semantics()`也不会自行调用模型。

需要准备、复核或执行本地规则时，读取[本地受管规则运行时](references/local-rule-runtime.md)，使用 `scripts/score_general_e2e.py`。该入口强制候选原件只读、一次性 runtime 副本、GT 后置、真实本机 workspace 路径、冻结 transcript、专用虚拟环境、环境白名单、超时、独立进程组和进程树清理；不得要求 Docker。规则 v2 逐项理由是确定性分值锚点解释，业务判定依据来自随项落盘的可复算证据，不得调用模型替自动规则补写或改判。

在控制 Harness 的独立评分会话中执行默认语义协议时，读取[Codex 语义评分协议](references/codex-agent-judge.md)。必须先生成冻结证据目录，再通过 `query-evidence` 分页回查；逐项结果只能引用已查询的 evidence ID，并声明已检查支持证据和反例。声称“未发生”时必须用无过滤分页覆盖完整 transcript。缺证据保留 `unresolved`；导入后由 core 校验分值锚点、引用、Judge 身份和请求锁，再合成标准 `score.json`。`verify-score` 会重新校验来源锁并从冻结组件重算标准分，不只比对结果文件自带的哈希。

显式选择 API 后端时，读取 [API Judge 评分协议](references/api-judge.md)。使用 `prepare --api-runtime-config ...` 冻结 provider、endpoint、模型、输入/输出预算、timeout、重试与凭据环境变量名；凭据值只能由运行环境注入。`run-api-score` 可恢复地完成规则、语义请求、合分和校验，API 最终失败形成合法 `evaluation_error / total_score=null`，不会补零、切换模型或回退到 Codex。

需要对有效分或合法评测异常重新评分时，读取[独立重评分 attempt](references/rescore.md)。重评分只复制冻结候选与评分输入，重建干净 runtime，并显式冻结新的 Judge 配置；不得复用 attempt ID 或修改源评分目录。

G4-03 的五题验收与 G3-05 的真实 API Judge smoke 已完成双后端准入。后续 Windows、60 题全量和裁判校准仍按各自验收项独立留证，不能由本状态自动推导。
