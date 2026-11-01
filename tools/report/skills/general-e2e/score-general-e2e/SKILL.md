---
name: score-general-e2e
description: 对一个冻结的 General E2E 任务运行自动规则与指定语义裁判，生成证据可追溯的标准评分；不负责批量调度、执行 Harness 或报告汇总。
---

`0.10.48` 修复参考补证校验对正式目录evidence_index.entries层级的读取，保留原语义目录和补证格式；新增真实prepare-semantics→query-evidence→record-semantics→finalize→移除runtime→verify-score --archived回归。0.10.47已停止且无正式成绩的失败attempt保留，不改其冻结代码或Prompt；从相同原执行和原score谱系建立新rescore。

`0.10.47` 新增`register-reference-supplement`：仅对获授权的新rescore、在语义请求生成前登记独立参考补证层，绑定原score SHA、任务/执行身份、来源URL/获取时间及全部文件SHA。原题/参考/候选/轨迹/权重不改；补证只供裁判核实事实，不能算作Agent检索、阅读或自验行为。补证清单与文件进入正式证据目录及请求锁，晚补、冲突、链接越界与归档漂移失败关闭；未登记补证的旧attempt保持原行为。

`0.10.46` 的行内距离兼容v2保留原唯一同步grade入口，在原证据导出后将完整适配审计挂入原diagnostics；不创建第二个grade，也不占用原业务证据预算。v1未通过规则入口准入的attempt保留失败原件，使用相同冻结执行建立新评分。

`0.10.45` 仅对精确Office022原契约的新attempt修复Writer行内图片缺省距离导入：在原render函数自行创建的临时副本中补齐缺失distL/distR=0，避免额外0.319cm间距导致五个标志换行。原件、已有显式值、图片尺寸、页边距、字体、正文、一页基准、原编辑检查和34/66权重不变；逐次变化及SHA完整保存在Worker原诊断。旧attempt不启用，其他任务不扩大适配。

`0.10.44` 的语义合分归档校验只重放已冻结响应、输入锁、原函数源码和受管Worker回执，不依赖已剔除的一次性runtime，也不重启Worker。创建新的合分检查仍要求真实runtime；归档中响应/候选/GT/查询或Worker字节漂移继续拒绝。原分数、权重与已冻结回执不改。

`0.10.43` 为新状态复核启用v3侧表索引与选项缓存，不向原候选行插入内部字段，保留原词时逐行返回自身原值；旧v1/v2源码和receipt按冻结Profile原样重建。工单封顶仍仅作用业务总分，前置规则失败且没有Worker结果时可形成原始错误的invalid/null终态，有效分仍强制原policy。原评分、权重和已冻结发行不修改。

`0.10.42` 仅对精确Office024契约的新attempt增加三项明确英文表头的原字段回退：Est. Total incl. goods (USD)、Estimated Delivery (from order)、Rate Validity。原PATTERNS优先，未知/模糊表头不扩大匹配；原公式求值、时间数值、可见性、分母、60/40和既有真实限分全部不变，独立裁判仍重新判断实际决策问题。旧attempt不原地启用。

`0.10.41` 仅对新Office018精确Profile将适配器新增的公开输入兼容审计移到独立受管sidecar，原业务证据74000总字符、18000单文件及原分页保持不变。sidecar作为显式评分端材料完整冻结、可查询、归档重验，冻结contract不修改，不计候选行为。旧v1快照Profile和旧失败字节保持原行为。

`0.10.40` 为精确Office018/029原契约的新attempt修复公开输入快照比较：只接受原版本化数据集已证明的51份LF/CRLF文本身份及7份Office严格CWM属性变体。原件、实际SHA、业务OPC部件、GT、题目、数值函数及原权重不改，独立兼容审计不得计作候选行为。旧attempt与旧Profile仍按原字节验证。

`0.10.39` 在精确原契约的新attempt保留Office026原final_total_cap，按原0.9/0.1合分后仅对业务总分执行一次min封顶，原规则分、语义分与能力项不改，归档验分独立重推。Data014–016原details对象完整保存在raw_result，数值接口只分离已注册布尔诊断。Data010状态复核v2按同表/字段/原词去重并保留全部位置，原10000问题上限不提高、歧义不猜测。Office007只接受原数据集8份受保护公开文本的精确LF/CRLF身份，其他变更仍拒绝。原题、GT、权重及旧冻结attempt保持不变。

`0.10.38` 还为精确登记的原业务+取证双grade结构消歧、errors诊断list分离、公开文本LF/CRLF完整性和工单完整分页资源预算提供新attempt兼容。合同托管原规则声明的逐行状态等价性由独立布尔复核后运行原比较，未知不猜测、不同原词不修成GT事实。仅对精确采购核对原contract/source的新attempt补入“已匹配订单”这一等价汇总标签，原括号限定解析和matched口径、数值、可见性、原分母、金额义务及80/20不变；未知标签/公式继续失败关闭。旧v2抽取实现及已冻结attempt不修改。

`0.10.37` 同时为Office003新attempt冻结公开允许的等价中文表头、显式双日期合计布局和唯一相对来源文件名，并在原六份材料中保全全部单元格/原列/位置/公式与缓存；原数据、比较、分母和权重不改。完整取证采用显式4MiB/16MiB资源上限，不截断。按精确task/contract/source/dataset注册四题声明的取证文件名通配符。仅在evaluator_evidence内展开固定父目录的文件名，收齐全部匹配项；零匹配、原候选预存匹配文件、目录及链接越界仍拒绝。已冻结旧规则产物可用新只读Reader核对原声明，原输入、规则、权重和已有成绩不改；快照、分页查询及archived验分沿用全部真实文件，不造占位材料。

`0.10.36` 为Office001精确原契约冻结原Rubric明确声明的四项连续[0,1]语义分；仍保留C1/C4离散锚点、原权重、引用与反例门禁，record/archived均从原契约重算，旧attempt不改。另按原提交、版本化manifest和冻结ZIP注册三题原文本校验常量纠正：仅已确认的私有参考旧校验值及Office014逐字节LF/CRLF文本身份，原参考、候选、业务值和计分函数不重写，其他漂移继续拒绝。

`0.10.35` 对精确Office001原contract/source SHA绑定的新Codex attempt，先在受管隔离副本发现原规则明确无法抽取的逐任务数值，再由独立裁判逐项查证、填写布尔复核和具体位置。原字段全集、已确定比较、重复一致性、分母、公共数值接口及60/40权重不变；不改用六态重归一/扣分成绩。未知仍阻断数值发布，旧attempt/HR路径保持原字节。

`0.10.34` 对新 trace 中 bound-sdk-completed-turn-projection-status/v1 证明独立重算原 state SHA、唯一原生 SDK 完成事件、会话/turn/Prompt/终稿及标准轨迹绑定，冻结到 trace handoff 并支持 archived 验证。原 running 投影不改写；证明不完整、取消、内容冲突或来源漂移仍拒绝，不将证明当作能力得分。

`0.10.33` 对齐Office001原探针的候选打开失败分支：只有同一原生应用已打开已知好控制文件、却不能把候选打开为原生文档时，才返回原C5的fail/0；连接、控制文件、后续检查、导出、保存重开、超时或收尾故障仍评测异常。上游结构损坏判定不代替该实际打开检查，旧attempt不重写。

`0.10.32` 为Office001新macOS attempt提供显式已验证的原生Writer API编辑探针。先按[本地运行时](references/local-rule-runtime.md)配置独立JDK/固定UNO JAR并真实跑合成文档编辑、保存、重开；只有精确原contract/source和实测runtime marker匹配才启用。原C5正文位置、段落、两份必需表格及逐表单元格编辑条件沿用，原grade数值函数/权重不变；Windows原WPS COM和旧attempt不改。评分端原生PDF、两版全页图、编辑副本及进程回执独立冻结，不冒充候选交付或主动验收。未知原生错误仍评测异常，不补零。新建grader-evidence里的Office副本也做只读字节保护；旧快照不原地修改。

`0.10.31` 为精确契约/规则SHA绑定的四象限PPT、XMind转PPT及库存分析002–004新attempt冻结公开Office输入兼容v2。仅当业务OPC部件与原公开材料逐字节一致、差异限于CWM属性及必要登记时，原哈希判据接受该有审计变体；原权重、分母、公式、候选和原件不改。模板未修改识别同样只在注册的交付路径检查等价模板，不把属性变体当作实际改稿。旧attempt没有新marker时沿用原有效源码，包括旧分页/跨月协议；不原地启用、不改旧分数。完整规则见[本地受管规则运行时](references/local-rule-runtime.md)。

`0.10.30` 提供显式原生 Office 运行环境配置脚本，适用于尚未开始评分的 macOS 专用 runtime。启动器在 Worker 的最小 PATH 下使用绝对 Python/Office 路径，每次调用独立配置字体目录、可写字体缓存和缺省用户配置；保留规则显式提供的 UserInstallation。配置不等于实际渲染验收，须用合成 Office 文件在同一隔离环境执行渲染、编辑重开及中文页面截图验证，详见[本地受管规则运行时](references/local-rule-runtime.md)。不替代原规则明确要求的 Windows WPS COM，不修改旧 runtime 或评分标准。

`0.10.29` 精确注册15道新检索题的独立业务/能力协议v2，保留每题原业务权重、能力m、诊断依赖及原聚合函数。独立裁判完整填写每项证据状态、单独能力分与原函数辅助参数后，先运行 check-aggregation --attempt-root ABS --response NEW_JSON --runtime-python FROZEN_PYTHON；只有受管Worker原函数校验PASS才record-semantics。预检只做结构和算术，结果与原响应SHA绑定、未知保持null；不得普通Python exec grader、代判事实或用数值占位发布分数。旧SPY v1、旧attempt、API及旧60/七维路径保持原契约。


`0.10.28` 对精确 HR 原源码绑定的新 Codex attempt，显式冻结等价来源行定位 Profile：接受“文件.xlsx#工作表!行N”这一公开允许的物理行引用，沿用原存在性、来源相关性、排班必须具体单元格和78/22计分。修复不修改候选，不扩大10,000复核资源上限；仍无法确定的字段/来源继续独立裁判复核。旧 attempt 未启用该 Profile 时有效源码和已锁定复核保持原样。


`0.10.27` 对精确原源码绑定的新采购题 attempt，支持有明确标题的横向汇总、订单总额字段和字面条件 SUMIF/COUNTIF/COUNTIFS。保留原单元格定位、可见性、原差额方向、候选总体因果口径及80/20公式；未知列/条件、重复矩阵类别继续失败关闭。旧 attempt 沿用原 Profile。


`0.10.26` 对原源码及 contract SHA 精确绑定的 SPY/VOO 新 Codex attempt，按题目原有协议分开发布业务与能力有效性。全部6个语义 key 仍须判定并保存在原始组件；响应还须完整填写模板中的 run_validity 和5项 capability_evidence_statuses，均以实际 query_ids、证据和中文理由说明。运行有效性为valid须已无过滤覆盖完整标准轨迹。业务仍按core_accuracy 85、source_binding 15合分；零业务权重能力项缺证不会阻断已有效的业务分。能力缺证保留null、预算45不删项重归一，运行污染/隔离缺证则两类都禁发。原始组件不改写，独立 capability-evaluation.json 保留全部检查点、状态、m预算及来源SHA；标准score.json发布业务视图并引用该文件，verify-score重新推导校验。旧 attempt、其他任务和API路径保持原行为。

启用独立有效性Profile时，以CLI返回的business_semantic_status及最终score.json判断业务有效性；原始semantic-component.json可能因某项能力unresolved而保留evaluation_error。不得修改原始组件或把未知能力补零。所有运行有效性/能力证据查询须在record-semantics前完成，之后只合分和验分，避免漂移已锁定的query-log。

`0.10.25` 为精确绑定原源码的人事工时题加入独立语义复核交接。`prepare-rule-review` 仅在隔离副本收集原规则明确无法决定的字段/来源问题，抑制发现阶段所有临时数值，移除自身临时 runtime，原评分 runtime 保持未执行状态。独立裁判用 `query-rule-review` 分页查询全部问题，按冻结候选/参考判断 passed 布尔值及中文理由，写新的 UTF-8 JSON 并 `record-rule-review`。该命令核对身份、Judge、输入锁、精确范围和实际查询，不接受数值占位或控制器代判。随后裁判用 request.json 中冻结的 runtime_python 运行原数值规则，再完成正常语义评分、合分和 verify-score。原确定性判定、公式、分母和78/22权重不改，未知问题继续失败关闭；回传保留完整复核及 Worker 谱系。旧 attempt 和 API 路径沿用原行为。

复核响应须复制 `rule-review/response-template.json` 的身份、Judge 和 locks。可判定项填写 status=judged、passed（仅 true/false）；证据不足时保留 status=unresolved、passed=null并解释具体缺口。每项都填写中文 reason 和实际返回的 query_ids，不得覆盖模板。不可判定复核会留证 NEEDS_ATTENTION 并阻止数值评分，不能猜测或补零。发现阶段的 Worker result 是空对象，不能作为规则分；其产物不得替代候选或正式评分端证据。完成全部复核后才允许 run-rules，后续证据目录由 prepare-semantics 正式冻结。

`0.10.24` 为精确绑定原源码的采购核对题补充等价的“单号”、订单/入库笔数、匹配笔数、净额等字段名称，并完整分页导出取证；原总体、数值、汇总计分函数、80/20权重及分值锚点不变。未识别的数字主张和未求值公式仍不能补零或跳过。

`0.10.23` 将跨月销售原规则明确返回的 evidence_status 文本按注册的原源码 SHA 分离为诊断元数据，避免把说明文字当数值检查点。Worker 保留完整 raw_result；有效适配策略与原冻结契约分别存证并复核。仅显式声明的 evidence_status 字符串可分离，数值、对象或其他未知字段继续拒绝；规则数值和原总分不改变。

`0.10.22` 的新 AStudio completion 冻结回执显式记录文档追加 LF 的传输 Profile：仅当正式采集文档恰为绑定原生终稿全文加一个 LF 时，规则输入采用原生正文，并记录文档 SHA、原生正文 SHA 和移除的文档后缀。旧回执沿用原行为；其他 Harness、正文/前后空格/CRLF 差异仍拒绝，不修改任何原件。

`0.10.21` 为跨月销售规则提供精确源码绑定的公开 Office 输入兼容：评分包内携带原公开输入字节与 SHA，仅当全部业务 OPC 成员逐字节相同、差异限于 CWM 自定义属性及其登记时接受。原候选、旧 SHA、题面、GT 和权重不改写；变体审计写入评分证据。业务、公式、样式、其他属性或登记变化继续触发原 ReviewRequired。

`0.10.20` 对精确绑定原源码 SHA 的四象限 PPT 和整改溯源评分器启用完整分页取证：每文件 4 MiB、合计 16 MiB 的资源上限替代过小的内置字符门槛。所有正文完整落盘，沿用 query-evidence 分页接口，禁止截断后判分。规则修正回执保留新旧源码 SHA、资源策略及原冻结契约；只对新评分 attempt 生效，旧题面、权重、检查点、分值锚点和评分记录不改写。

对长行 JSON 使用 `query-evidence --mode file --evidence-id ID --file-char-offset 0 --max-chars 16384`；按返回的 `next_file_char_offset` 继续，直到 `has_more=false`。此 offset 按 Unicode 字符计数，保留中文、emoji 和原换行；不得与行级 `--offset` 混用。每页 query_id 都保留在复核引用中，全部契约要求的取证正文读取完整后才能记录语义判定。原有行分页继续兼容。

`0.10.19` 支持显式 bound-qwen-native-utf8-redecode/v1 传输补采：原记录、回执、原始快照与 SHA 均保留；原生身份、候选、执行时间、人工介入及资源值不变，只准许字节分块解码造成的 U+FFFD 替换恢复。新回执以显式 --execution-record task=path 选择，评分再次验证原/新闭包；不重发、不重判旧成绩、不修改题目或权重。

`0.10.18` 为新 attempt 冻结正式采集的终稿、完成回执和证据清单。只有已验证原生终态、原执行记录与证据清单受到采集回执 SHA 绑定、终稿受到证据清单绑定，且终稿与标准转录中最后的助手正文完全一致时，才在规则输入视图追加有来源的 task_complete 收据；原标准转录保持原字节，不合成候选内容。rule-input-completion.json、Worker 请求和规则审计均重新核验，完成收据可按 rule_audit 分页查询；移除 runtime 后仍可验分。旧 attempt 没有该冻结描述时保持原行为，不猜测最后一段计划是终稿，不重评已完成语义分。

`0.10.17` 在 macOS 为新建的评分原件 Office 副本设置用户不可变标志并再次验证原 SHA，保护已冻结的输入字节。新增 `prepare/prepare-rescore --protect-runtime-office-inputs`：仅在审查原规则不会改写这些候选 Office 文件后显式使用，对一次性 runtime 中的候选 Office 输入也设置同一保护；规则生成的取证目录继续可写。运行时副本默认保持原可写行为，非 macOS 不接受该显式保护选项。manifest 分别记录原件和显式 runtime 的保护 Profile；旧 attempt、原规则、权重和宿主变体不修改，清理受管临时目录仍解除自身保护标志。

`0.10.16` 为 WorkBuddy 原生 user-query 包装增加公开上下文交接：仅当归档 runtime binding 与 execution 的 session/request/cwd、Prompt SHA 和唯一问题一致，原生 user 行明确 startsNewUserRequest、绑定同一 request，且目标 AGENTS.md 路径及全文出现在唯一 user_query 之前，才生成可复核的规则输入视图。助手引用、缺少送达记录、错误目录或其他请求不能替代。原始标准转录、执行证据和候选原件不改写；rule-input-context.json 同时绑定 runtime 原件和 JSONL 行 SHA。

`0.10.15` 在 macOS 准备评分时，对从规范容器恢复的运行时 Office GT 副本设置用户不可变标志，避免宿主追加属性使规则完成后的摘要漂移；只保护评分参考副本，不修改候选或原始 GT。运行时不进入回传包；清理受管临时目录时会解除自身设置的标志。其他平台仍按原有容器与权限保护口径，不据此声明 Windows 真机验收。

`0.10.14` 为新 attempt 冻结 `declared-evidence-and-native-context/v1` 规则输入 Profile。标准转录保持原字节；规则视图仅为已验证的终稿增加兼容的 final/end_turn 标记，并可从同 session/turn/cwd 的原生 SDK user 指令消息补入实际送达的公开 AGENTS 上下文。必须同时核验原生加载目录、完整上下文、唯一任务/问题边界及问题前送达记录，不能以文件存在、助手引用或事后消息冒充送达。`rule-input-context.json` 和 Worker 请求随评分保留并重新核验，裁判可查询其规则审计证据。

新 Profile 还冻结契约声明在 `evaluator_evidence/` 下的全部评分端材料，保留原契约的具体 role；候选的 `results/` 交付物不属于该生成范围。参考、候选终稿抽取、公开上下文和诊断属于裁判输入，不能据此奖励候选创建这些文件或完成自检。

零权重且明确声明 `evidence_preparation_only` 的空规则组件可生成说明文字，不增加业务分。已经完成独立语义判定、仅因该理由生成错误而合分失败时，可用 `repair-zero-weight-finalization --source-attempt-root ABS --output-root NEW` 从原冻结组件产生独立、可归档验证的合分修复制品；原 attempt、失败审计与语义决定保持不变，不重跑规则或调用 Judge。

`0.10.13` 将新准备的 Office GT 封装为单成员 `*.gtref.zip` 参考容器，防止宿主把松散参考文件当作生成制品追加属性。`attempt-manifest.json` 的 `private_scoring.storage.files` 明确记录原始 `logical_path`、容器 `stored_path`、原始字节 SHA/大小及容器 SHA/大小。规则运行时仍获得原文件名和原始字节；重评分恢复同一逻辑输入。旧 attempt、原候选、评分 ZIP 和宿主变体均不改写。

语义裁判须先通过 `query-evidence --mode catalog` 查询对应 `private_reference` 容器证据 ID，通过 `--mode file` 查询清单 JSON，再用 `zipfile.ZipFile` 读取唯一的原始成员；二进制 ZIP 不使用 UTF-8 文本查询。Office 解析器使用成员字节的 `io.BytesIO`，或读取已校验的 `runtime/workspace/gt/<logical_path>`。参考容器属于评分材料，不改变候选的原定文件格式或交付位置要求；GT 不能计作候选产物，也不向私有原件目录解压 Office 文件。归档会保留容器和映射，移除 runtime 后仍可严格验分。

`0.10.12` 在记录摘要前将私有 GT 副本设为只读。只读位限制普通文件写入，但不能单独阻止宿主生成新变体；已漂移的旧副本保留，使用新的评分 attempt，不删除宿主属性或修改旧摘要。

`0.10.11` 按冻结契约的 `judge_evidence.required` 收集评分端取证材料。受管 Worker 成功后校验 runtime 的完整 SHA，再把声明目录复制为不可变 `grader-evidence/` 快照，记录原路径、文件 SHA、contract 和 rule audit SHA，并以 `grader_generated_evidence` 类型加入可查询证据索引。它们属于评分端材料，不能计作候选产物或候选自检。缺失、路径越界、链接、候选预占目录和生成后漂移均阻断准入；回传排除一次性 runtime 后仍可 `verify-score --archived`。旧无此声明的契约保持原行为。


`0.10.10` 兼容新旧数据集。旧 Rubric 继续要求组内权重和为 1；新冻结契约以 `semantic_weight_scale` 显式声明分值预算，转换后仍乘原组权重，原 Rubric 不改写。新规则的 `rule_result_adapter` 仅分离声明的诊断对象，Worker 同时保存原始 `raw_result` 和适配后的 `result`。零规则权重的证据准备不产生候选能力分，缺证和运行环境失败继续返回评测异常。Office 第 1 题仅按其已声明的公共数字接口计算规则等权均值。依赖按更新后的 runtime lock 和带哈希 requirements 安装；旧已冻结轮次的运行时不自动替换。


# 评分 General E2E 单题

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

需要开发、校验或接入评分 core 时，读取[评分 core 接口](references/grading-core.md)。当前四个公开 API 可用于确定性契约验证和受管 backend 接入；`run_rules()` 不会自行执行不可信规则，`evaluate_semantics()` 也不会自行调用模型。

需要准备、复核或执行本地规则时，读取[本地受管规则运行时](references/local-rule-runtime.md)，使用 `scripts/score_general_e2e.py`。该入口强制候选原件只读、一次性 runtime 副本、GT 后置、真实本机 workspace 路径、冻结 transcript、专用虚拟环境、环境白名单、超时、独立进程组和进程树清理；不得要求 Docker。规则 v2 逐项理由是确定性分值锚点解释，业务判定依据来自随项落盘的可复算证据，不得调用模型替自动规则补写或改判。

在控制 Harness 的独立评分会话中执行默认语义协议时，读取[Codex 语义评分协议](references/codex-agent-judge.md)。必须先生成冻结证据目录，再通过 `query-evidence` 分页回查；逐项结果只能引用已查询的 evidence ID，并声明已检查支持证据和反例。声称“未发生”时必须用无过滤分页覆盖完整 transcript。缺证据保留 `unresolved`；导入后由 core 校验分值锚点、引用、Judge 身份和请求锁，再合成标准 `score.json`。`verify-score` 会重新校验来源锁并从冻结组件重算标准分，不只比对结果文件自带的哈希。

显式选择 API 后端时，读取 [API Judge 评分协议](references/api-judge.md)。使用 `prepare --api-runtime-config ...` 冻结 provider、endpoint、模型、输入/输出预算、timeout、重试与凭据环境变量名；凭据值只能由运行环境注入。`run-api-score` 可恢复地完成规则、语义请求、合分和校验，API 最终失败形成合法 `evaluation_error / total_score=null`，不会补零、切换模型或回退到 Codex。

需要对有效分或合法评测异常重新评分时，读取[独立重评分 attempt](references/rescore.md)。重评分只复制冻结候选与评分输入，重建干净 runtime，并显式冻结新的 Judge 配置；不得复用 attempt ID 或修改源评分目录。

G4-03 的五题验收与 G3-05 的真实 API Judge smoke 已完成双后端准入。后续 Windows、60 题全量和裁判校准仍按各自验收项独立留证，不能由本状态自动推导。
