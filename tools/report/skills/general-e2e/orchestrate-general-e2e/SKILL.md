---
name: orchestrate-general-e2e
description: 将有效 General E2E 执行回执交接为独立单题评分工作空间并调度 Codex 或 API Judge；用于评分编排，不负责执行用例或亲自判断分数。
---

`0.11.47` 同步修订70题的精确通配符目录，允许用新只读Reader验证并留证旧声明通配符读取失败，再从同一执行独立重评分；不重跑旧规则或修改原件。

`0.11.46` 原生并发核对使用 `drivers/codex-desktop/native-snapshots.mjs`：对每个保留槽位分别做无旧cursor的零等待快照，验证完整目标身份后才顺序record-wait。组等待只回部分目标时不能推断其余仍在运行；缺目标/身份冲突失败关闭。该接口只查询原生状态，不创建、重发或评分。全部仍在运行时再做有cursor的长等待，完成后重新逐目标快照。

`0.11.45` 精确留证Office001旧原生Writer完成后SIGTERM收尾255错误，绑定原契约、数据集、Worker、原生完成上下文及全部探针SHA；仅保留旧未评分，新attempt须独立重评。

`0.11.44` 全批恢复校验以最多3个只读子进程执行原冻结Score的verify，完整重算全部原SHA，不使用跨操作缓存；错误仍按原题序收口。规则、语义裁判与状态修改保持原路径，历史特殊修复验证保留原顺序。减少大批次项目登记与补位的串行验证开销。


`0.11.43` 的compose-full-scope-selection新增显式`--allow-valid-rescore --valid-rescore-reason`，支持在已有完整来源选择中合入多个原生重评分来源。每项必须绑定当前选中score/attempt manifest/candidate SHA及原执行、题面、契约、GT和轨迹，来自有锁定submission和SCORE_RECORDED终态的真实rescore编排；不按高分选择。默认仍拒绝覆盖有效分，基础设施补齐标志不能替代此授权。原分、源编排和完整范围不改写，选择谱系记录逐项替换、来源锁与理由。

`0.11.42` 同步Score0.10.49的新评分传输Profile。修复评分使用同一冻结执行创建新attempt，不覆盖旧分；独立裁判须读取request中的answer_delivery_policy及全部原始证据，不能复制控制器分析作为裁决。对修复前后相同的确定性分数也不按高低择优；完整范围选择显式登记所有替换题目。

`0.11.41` 同步Office022行内距离兼容v2的评分交接：保留唯一原规则入口与原证据预算，失败的v1未启动Worker/裁判，原失败状态和材料保留，新attempt仍按正式独立评分与verify-score准入。

`0.11.40` 为Office022新的独立评分冻结精确原契约的Writer行内图片缺省距离兼容Profile。仅规范原render临时副本，原件/页数标准/权重不改；旧环境失败及旧回传保留，以相同冻结执行的新attempt评分后显式派生完整范围选择。

`0.11.39` 保留旧v1/v2状态复核的原源码生成与回执校验，新attempt采用v3无行内污染的完整位置复核；工单旧失败退役须精确包含原八个数值键和有效policy，其他破损回执不归为已知适配失败。原分数和旧冻结包不改。

`0.11.38` 仅对原生裁判已完成但未发布score的Office024合理英文布局提取失败扩展record-framework-failure。严格绑定原task/contract/source/dataset、原blocker、三项实际工作簿表头/公式、原抽取null、原查询/规则与SDK上下文；旧组件和错误文件锁定保留，不代判能力分。修复须建立相同冻结执行的新initial评分，其他失败不适用。

`0.11.37` 精确识别Office018适配器新增审计导致的旧取证预算失败：原业务材料必须全部处于74000/18000原预算内，新增审计与原输入逐件绑定；保留旧9份原字节到可移植infrastructure-evidence并锁定SHA，原runtime不删改。无Judge、无组件、无score时才能退役，新attempt以独立sidecar完整交接审计；真实业务证据超限和其他失败不适用。

`0.11.36` 仅对精确登记的Office018/029旧公开输入比较误报扩展record-framework-failure：原规则/Worker已完成、未创建语义会话、无score，且全部差异逐件证明为原文本换行或严格CWM变体时才能留证。恢复重验旧组件与原输入，保持旧未评分记录，再建立相同冻结执行的新attempt；真实业务内容变更不准入。

`0.11.35` 为已注册原总分封顶/归因诊断接口失败增加只留证退役；`record-framework-failure` 仅留证已退出的Data010旧复核发现超限，或原生裁判已完成但Office007公开文本基线错误而未发布score的旧attempt。严格核验原输入、失败、进程退出或原生上下文以及全部原评分证据SHA；恢复复放，保留旧thread/组件，不代判、不重试原发送。修复必须建立同冻结执行的新attempt，再显式选择完整范围。

`0.11.34` 仅对精确原task/contract/source登记的包装入口、空errors诊断list、公开文本LF/CRLF校验和原状态等价复核失败，保留真实旧审计为未评分；未启动Worker时明确记录缺失，不造result文件。恢复重验同一原失败与SHA，新评分须从相同冻结执行独立准备，原数值与语义不代判。

`0.11.33` record-unscored-evidence-glob-error只处理已注册通配符被旧读取器当字面路径拒绝的规则收口。须原Worker/audit/component均完成、无Judge/score，新冻结Score读取器完整只读verify实际原件成功；原attempt不重跑、不改写，独立回执锁定原错误与文件SHA，留证旧未评分后另建修复评分。恢复时复放同一验证；未知失败、缺证据、漂移和已有有效成绩不适用。

`0.11.32` 补齐Office020原规则声明的精确RuntimeError校验失败签名；仅在注册task/contract/source/dataset与实际原私有参考字节全部核验后，留证旧失败并允许独立修复评分纳入完整范围。缺文件、形状改变、其他RuntimeError和任意漂移仍拒绝；冻结Score36及其规则/语义判断保持不变。

`0.11.31` 识别已注册原私有参考的旧校验失败，核对精确task/contract/source/dataset和实际原件后可显式留证旧未评分记录，并将合法新评分纳入完整原范围。未知参考、文件漂移或其他异常不进入该分支；原Prompt、裁判、评分权重与既有有效成绩不改。

`0.11.30` 新Office001原生评分Prompt显式交接数值抽取复核、具体证据位置与首次运行原规则顺序。旧失败attempt仅在原contract/source SHA、原RuntimeError和唯一c3_numeric_facts=undetermined/null全匹配时可显式留作未评分，再从相同冻结执行建立独立修复评分；原错误/输入保留，其他错误尤其原生环境故障不能借此跳过。旧Prompt和已准入成绩不改。

`0.11.29` 仅对新冻结的原生终态投影对账 Profile，在 v8 Prompt 中交接原 state 与 SDK 完成证明，并在恢复时复核相同路由。裁判仍独立按原 Rubric 判断；证明只解决执行终态元数据，不代表答案或能力合格。旧 Prompt 字节不变。

`0.11.28` 仅对新冻结Office001原生Writer API Profile的v8 Prompt追加原生编辑/全页图像取证核验，显式区分评分端材料、候选交付和候选主动验收；状态恢复核对同一marker路由。未启用该Profile的旧Prompt字节与原调度行为不变。

`0.11.27` v8 Prompt可对新注册的独立有效性v2交接动态原权重/能力预算、辅助判定与受管聚合预检。该路由在新attempt和Prompt中显式冻结并核验，不把零业务权重都当作可忽略的能力项；旧v3–v8及未启用v2的Prompt内容不变。


`0.11.26` compose-full-scope-selection 可显式 --allow-scoring-infrastructure-repair 并说明 --infrastructure-repair-reason，纳入已修复的原规则基础设施错误及合法 evaluation_error 重评分，保持原执行、题目和完整范围。有效旧分不由此覆盖；--source-selection-root 可延续已校验的原完整范围选择，全部来源锁和旧文件保留。


`0.11.25` 的 v8 Prompt 支持原规则声明的语义复核：精确 HR 源码对应的新 Codex attempt 先由受管 Worker 在隔离副本发现问题，冻结 request SHA 后进入独立裁判项目。发现过程不发布任何临时规则分，不占语义槽；裁判自己查询、判断字段/来源、记录复核，再运行原数值规则及正常语义评分。控制器不代判，缺少/漂移的复核上下文不按0/1猜测。其他 hybrid 路由及旧 v3–v7 Prompt 保持原契约。

`0.11.24` 的 macOS 项目注册默认使用已核验应用包内的官方 `codex app ABS`，再自动点击完整回显同一绝对目录的唯一“Trust folder／信任文件夹”。回执绑定 CLI 路径/SHA/argv、目标目录及实际点击；先前已有的同路径信任弹窗继续可恢复。未知弹窗或目录不符不点击；未观察到弹窗时先用 list_projects 回读复用，不盲目注册、不默认等待人工。只有 CLI 不可用才沿用原生文件选择器，`--no-cli-open` 可显式禁用新入口。

`0.11.23` 的基础设施纠正选择使用真实 initial 编排类型，并保持相同冻结输入与完整范围；历史 rescore 选择规则不变。

`0.11.22` 的 record-score --native-response-recovery-proof 只收口原生 High 裁判已完整写出的原样结构化判定：严格绑定 SDK 身份、Prompt、工具写入调用、响应 SHA、已导入相同 JSON 和 server_overloaded 明确终态，机械导入/合分仍须 verify-score 通过。真实线程 FAILED 状态保留，控制器不补判、不改判定、不重发；未知失败、缺失判定或其他档位不适用。

`0.11.21` 的 compose-rescore-selection 可显式 --allow-native-context-correction 并提供完成态 --native-context-proof：只替换已有真实配置拒绝、从未准入成绩的线程，用相同冻结输入下实际 High 新会话的合法评分补入原完整范围。原始错误配置评分、未评分行、原编排与回执保留，不按高分择优，不覆盖有效旧成绩。

`0.11.20` 的 reject-native-context 只在原线程明确完成且尚未准入成绩后，按原始 SDK 逐项核验线程、工作空间、冻结 Prompt、唯一实际模型档位及完整单 turn，留证拒绝不符的裁判配置。保留原会话与分数文件，不冒充失败终态或纳入固定裁判比较；配置匹配的合法会话不可用此入口拒绝。

`0.11.19` 的状态恢复同时验证显式公共上下文 setup 未评分记录及其原 worker/contract SHA；已创建裁判的登记沿用同一线程，不因该记录类型重建或重发。

`0.11.18` 允许显式留证数据集原规则声明的精确公共上下文准入失败（ValueError: EVALUATOR_SETUP_INVALID: public task context delivery not evidenced）。仅保留 evaluator-public-context-setup-error/v1 未评分，不补上下文、不补零或代替裁判；其他 ValueError、身份和基础设施异常仍失败关闭。

`0.11.17` 支持显式 bound-qwen-native-utf8-redecode/v1 传输补采：原记录、回执、原始快照与 SHA 均保留；原生身份、候选、执行时间、人工介入及资源值不变，只准许字节分块解码造成的 U+FFFD 替换恢复。新回执以显式 --execution-record task=path 选择，评分再次验证原/新闭包；不重发、不重判旧成绩、不修改题目或权重。

`0.11.16` 可显式保留原数据集的两种固定证据预算终止信息为未评分：EvidenceError 的“Required text evidence exceeds collector budget; do not report a valid semantic/capability score”，以及 RuntimeError 的“EVALUATOR_EVIDENCE_LIMIT: no silent truncation; collect complete evidence before judging”。不扩大预算、不截断必需材料、不创建缺证据的 Judge，也不改变规则、权重或能力分；其他 EvidenceError/RuntimeError 继续失败关闭。

`0.11.15` 的 `init/init-rescore --protect-runtime-office-inputs` 显式转交 score Skill 的只读 Office runtime 输入选项。必须先审查冻结规则不会改写候选 Office 文件；默认关闭，原有可写 runtime 契约保持兼容。已建立的编排和 Prompt 不追加此选项；需要修复尚未评分的输入副本时保留旧 attempt，并从同一冻结执行创建新评分 attempt，不重跑 Harness 或重新判断已完成语义分。

`0.11.14` 接受数据集明确抛出的 `EvaluationReviewRequired` 和 `ReviewRequired`，同样仅作留证未评分，不由控制器猜测规则分。运行环境、身份、证据漂移等其他异常仍不进入此分支。

`0.11.13` 提供显式 `record-unscored-rule-error --task-id ID --reason TEXT`：仅接受原数据集规则抛出的 `EvaluationError`，且尚无语义线程、规则组件或分数；保留 Worker/审计 SHA 和完整题目范围，不计能力零分，不用于跳过额度故障或有效评分。`compose-full-scope-selection` 可将已锁定的部分 submission 与明确指定、已严格验分的缺失题目制品合成完整原范围；不重评、不按高分选择、不伪造编排完成状态。

`0.11.12` 接受原生注册器已有的 `confirm-pending-trust` 回执。除原有路径、版本与哈希门禁外，必须证明 `trust-dialog-recovery`、`registered` 和精确的非链接文件夹路径；未知方法或缺失证明仍拒绝。macOS 可用官方 `codex app ABS` 打开目录，再由注册器确认绑定路径的原生信任弹窗。已冻结评分材料、Prompt、裁判和原线程保持不变。

`0.11.11` 支持 `llm_judge` 题的零权重取证 Worker。只有冻结契约同时声明非空 Automated Checks 和必需 `grader_generated_evidence` 时，才先进入 RULES_READY；取证和校验完成后再登记独立语义评分项目。该步骤不占语义评分槽、不产生规则能力分、不改评分类型、Rubric 或权重。新评分 Prompt 冻结此路径，恢复时从原 contract 重新核对；旧纯语义题继续直接进入项目登记。生成证据和归档快照由 score >=0.10.11 校验，失败不创建 Judge、不补零。


# 编排 General E2E 评分

`0.11.10` 的v7 Prompt及preflight将HTML离线验证环境前置；hybrid沿用冻结规则runtime，纯语义HTML可通过preflight的browser-runtime-python/playwright-browsers-path显式配置。预检只读合成fixture，失败不创建Judge；具体协议见冻结score Skill的references/offline-browser-validation.md。旧v3–v6 Prompt与已完成attempt保持原契约。

创建原生评分聊天后及COMPLETED后，用`verify-native-context --orchestration-root ABS --task-id ID --sdk-file ABS [--allow-running] --output NEW_JSON`核对真实thread/cwd/唯一workspace root/model/high/冻结Prompt与turn边界；原生桥XML输入严格解码后比对完整SHA，不使用模糊匹配，也不导出思考正文。初始头未到齐时等待原thread，不新建替代聊天。allow-running只证明已观察身份，不证明完成。

经明确授权的单题重评分完成后，使用`compose-rescore-selection --source-orchestration-root ABS --replacement-orchestration-root ABS --task-id ID --output-root NEW_ROOT`将明确新attempt纳入原完整范围。它复核原/新谱系、相同Judge和冻结输入，归档校验复制的评分，原评分与编排不变；不按高分挑选、不缩小分母、不伪造COMPLETED state。输出是独立完整submission选择目录，可交run的record-submission/package-return，不是新的Judge编排。

`0.11.9` 在前序 hybrid 规则完成、进入待注册状态时，保留已注册项目、已绑定线程、等待/超时和待验分任务的语义槽，避免原线程被 TASK_NOT_ACTIVE 拒绝。空槽按冻结题序补位；规则 Worker 仍不占语义槽，已有预留超过配置容量时以 SEMANTIC_SLOT_OVERCOMMITTED 失败关闭。不创建替代线程、不改 Judge 或评分内容；旧冻结实现和状态保持原样。

正式评测的语义评分统一为每题独立项目、项目内新建独立聊天。协作子代理不作为该路径的评分 transport；注册或会话创建失败时保留编排错误，不静默替代。纯 automated 任务仍由受管规则 Worker 执行，不占语义评分会话槽。

`0.11.5` 的 v6 Prompt 冻结运行评分 CLI 的 Python 绝对路径、版本和制品 SHA，明确元数据文件 `skill-metadata.json` 的绝对路径及 SHA，并要求 UTF-8 文件响应。控制器的子进程和 JSON 输出固定 UTF-8；恢复时复核冻结解释器。v3/v4/v5 的旧 Prompt 和无解释器锁的旧编排保持原契约，不重写历史。

冻结 score Skill 的 `prepare` 返回明确 `EXECUTION_NOT_SCORABLE` 时，只将本题保留为 `UNSCORED`，不创建 Judge attempt，也不阻断其他题目。其它错误仍失败关闭；初始化回滚仅清理本控制器尚未发布的 staging，支持其中的只读候选，不修改已发布评分或执行原件。

`0.11.8` 与 score-general-e2e 0.10.8 配合，原样传播 `EXECUTION_EXTERNAL_QUOTA_EXHAUSTED` 并阻止后续准备和派发，等待人工恢复额度及明确恢复指令。该错误不进入普通 UNSCORED 继续分支，也不记零分。原失败 attempt、证据和已发布结果保留；未发布 staging 按既有规则清理。额度恢复或普通 resume 不会把终态失败自动变为成功；是否重测、创建新 attempt 及选择结果必须另有人工授权。原轮次经授权排除旧失败的特例不作为默认策略。

新轮次优先由 run-general-e2e prepare-score 建立编排，根目录默认当前控制 Harness 会话项目，显式 round-root 覆盖。状态写入 Harness/score/.orchestrations，单题入口为 Harness/score/tasks/<task_id>/current。带 .general-e2e/round-unit.json 的新单元启用完整 trace 交接门禁；旧单元保留显式 legacy 兼容。

新评分任务可以在本题目录读取标准轨迹和 raw_trace 原件。移走原执行目录后仍必须能校验、查询和评分，不把全局 repair-control 或临时运行目录作为评分数据依赖。

为每个任务建立隔离评分 attempt，冻结裁判配置并维护可恢复的评分队列。

## 当前能力门禁

先运行：

```bash
python3 -m eval_general_e2e skills --name orchestrate-general-e2e --json
```

当前 `0.11.8/operational` 已交付 automated/hybrid/llm_judge 路由、默认 3 槽且上限 8 的语义评分调度、Codex 项目/任务编排、API Judge 队列与崩溃恢复、统一 `verify-score` 准入、完整范围 submission、独立重评分编排、动态 Codex Desktop 发现、macOS 一次性托管重启入口，以及保留审计的迟到完成评分恢复。v5 评分 Prompt 明确容量异常与候选能力失败的控制策略。评分任务提交前还必须自检 evidence/query 绑定和未发生类完整 transcript 覆盖。迟到恢复发生在旧 submission 之后时，可用显式入口严格复算恢复前内容、按原 SHA 归档并原子替换 submission；其他内容漂移仍失败关闭。G4-03 已用旧版本 AstronStudio macOS 五题覆盖两题 automated、一题 hybrid、两题 llm_judge，得到 5/5 有效评分、回传和三种报告；语义评分固定为 `gpt-6-astra/high`，三会话并发。该证据只支持当时已验证的平台与版本组合，不能自动升级到本版共享发现/重启实现，也不能外推 Windows 或其他 Harness。

普通生产调用不传 `--acceptance-id`。该参数仅用于显式验收留证；传入后，编排状态、队列摘要、评分 Prompt 与每题 `attempt-manifest.json` 中的 acceptance ID 必须完全一致。API Judge 不接受此标记，缺失或不一致时失败关闭。

## 责任边界

`0.11.0` 把已绑定但仅工具轨迹不完整的窄范围情形交给冻结 score Skill 的 `prepare` 判定。编排器不自行降低轨迹要求；score `>=0.8.3` 仅允许已确认候选文件专用的 automated 规则，其余仍形成明确未评分状态。旧编排和旧回执不覆盖；新增评分入口或准入策略使用新的 orchestration/attempt。

- 输入：有效执行回执、scoring 包和冻结裁判配置。
- 输出：独立评分工作空间、评分队列、裁判任务状态和有效 submission。
- 单题评分会话相互隔离；编排器负责调度，单题评分 Agent 不调度下一题。
- 默认后端是 `codex-agent-judge-v1`，`api-judge-v1` 只能显式选择且不能静默切换。
- 不执行被测 Harness，不替代单题评分判断，不生成最终汇总报告。

## 已交付编排子能力

需要初始化或恢复 Codex 评分任务时，读取 [Codex 项目与任务编排](references/codex-orchestration.md)，使用 `scripts/orchestrate_general_e2e.py`。控制器通过 `recommended_actions` 驱动控制 Harness 调用项目列表、`create_thread`、`wait_threads` 和必要的线程检查，不直接伪造模型或工具结果。

每题项目根是独立私有评分 attempt，项目注册器位于 `drivers/codex-desktop/`。语义评分默认 3 槽、可配置 1–8；原 thread 未取得明确终态时不创建替代任务。`automated` 仅运行代码规则并生成 `not-required` 语义组件，不占语义槽；`hybrid` 先运行并冻结规则组件，再进入控制 Harness 语义评分槽；`llm_judge` 直接进入语义槽。线程返回完成后继续占用原槽位并给出 `VERIFY_SCORE`，只有 `record-score` 调用 score Skill 的 `verify-score` 通过并锁定 `score.json` 后才动态补位。

若评分任务显示 `Selected model is at capacity. Please try a different model.`，Codex 会在原任务中自行最多重试 5 次；控制任务继续等待同一 thread，不调用 `create_thread`、不切模型、不创建替代评分 attempt。只有原 thread 最终明确失败后才按现有失败状态收口。候选没有产物、产物损坏或内容不满足题意属于被评测结果；评分会话按 rubric 形成零分、部分分或合法 unresolved，控制任务不能因此终止队列、停止后续题目或重跑 Harness。评分基础设施证据/身份损坏与候选能力失败必须分开。

macOS 当前控制任务需要为 Codex Desktop 补开 CDP 时，必须按 [Codex 项目与任务编排](references/codex-orchestration.md) 使用 `scripts/restart_macos_desktop_debug.sh`。该脚本随 Skill 的 `desktop-debug` 共享组件独立分发；应用路径动态发现并冻结，退出只对已核对根 PID 执行有界 TERM/KILL，不调用 Apple Events、`System Events` 或退出框 UI Automation；禁止用 `launchctl submit` 或常驻 KeepAlive Job 自重启。

显式选择 `api-judge-v1` 时，读取 [API Judge 编排](references/api-orchestration.md)。API 任务从 `API_READY` 进入 `API_RUNNING` 后才调用 score Skill；恢复始终续同一 attempt，已形成终态时不重复请求，结果未知时失败关闭。API 队列不注册 Codex 项目、不创建线程，也不在失败时回退到 Codex。

全部任务进入终态后，读取 [submission 与重评分编排](references/submission-and-rescore.md)。`build-submission` 完整枚举冻结范围并区分 `valid / evaluation_error / unscored`；`init-rescore` 只从已锁定 submission 中选择已有合法评分的任务，创建新的 orchestration 和 attempt，源文件保持不变。
