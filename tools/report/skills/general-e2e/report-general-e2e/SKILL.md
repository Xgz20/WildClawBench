---
name: report-general-e2e
description: 校验并汇总 General E2E submission 和回传包，生成同源 JSON、Markdown 与 Excel 报告；不执行用例、补评分或把评测异常计为能力零分。
---

`0.8.65` selected_report可显式绑定工作空间内既有的--report-output-root，将报告写入与私有批次分离的交付目录；默认仍限制批次内的新目录，拒绝越界、既有输出及符号链接。来源验证、评分和同进程封存保持；并发注释明确最终选定尝试范围，历史尝试另留审计。

`0.8.64` 独立保留SDK已完成后原生运行时再中断的证明：同回合完整终稿、较晚原生中断、停止运行时及仅用量尾账本须闭合；原FAILED/cancelled不改，不伪称SDK被取消或全文已在客户端展示。沿原检查点交独立评分，不生成策略零分。

`0.8.63` 分发源码指纹约束的原生发送前中止证明回放。原生受理失败、保守提交账本和原Rubric成绩分别保留；本Profile不推导策略零分，不改历史回执或模型/资源未知值。

`0.8.62` 分发独立的原生终稿严格后缀差异校验，按冻结原件与SHA复放同回合SDK证明；原短回复、partial、显式评分授权及差异谱系保留，报告不替代裁判、不改分数或旧回执。

`0.8.61` 对已证明未派发的基础设施失败单列模型覆盖：已执行记录全部核验为同一模型时，显示真实模型并明确已核验与未派发题数；不为未执行题推定模型，不隐藏已执行但模型未知的记录。

`0.8.60` Excel 单元身份表对整行启用换行和自适应行高，完整显示长模型标签与原始单元身份；保留全部数据、分数和已封存报告。

`0.8.59` 多来源报告逐包展开输入谱系，独立核对可选回传归档与原包清单、导入回执、submission 的哈希绑定。JSON、Excel 和来源索引保留全部包，不改分数或原件。

`0.8.58` 显式多来源报告按冻结单元各自题目范围汇总，不补成全题笛卡尔积。仅显式允许的单元可汇总版本信息不齐的来源，目标版本必须为空，逐题原版本及覆盖保留；已知客户端、模型和历史身份不改写。

`0.8.57` 对同次 AgentCube 原生完成后的控制器断连使用独立恢复来源，复验原始文件、清理证明、身份与唯一发送；原失败和旧发行保持，不能伪造 WGUI RunReport。

`0.8.56` 多来源报告按原单元清单的嵌套 unit 身份验证 AgentCube 资源补充层，并保留旧无补充层的范围验证。普通报告与显式逐题报告同源复算资源，原包、分数和父批次范围不改。

`0.8.55` 支持显式 AgentCube 原生资源补充层：独立重验原 Prompt、会话、MCP 调用、终态及清理证明，再按原 last/total 用量复算 Token 和请求数。原执行、资源字节与分数不改，缺失字段不补零；回传、导入和报告须使用支持该 Profile 的冻结发行。

`0.8.54` 整合 Loomy 模型展示与主线自动规则数量说明：只列出真实语义裁判，not-required 组单独显示，空协议组不冒充独立裁判。原判分、分母、资源覆盖和历史报告不变。

`0.8.53` 单一单元的领导版报告不把 not-required 自动规则组显示为 None / None 独立裁判；自动与语义协议分组、原分数、冻结来源和资源覆盖保持原样。

`0.8.52` Loomy 开发发行：新增 Loomy Harness 显示名称，未知资源继续按字段状态和覆盖率展示。

`0.8.52` 主线发行：单单元领导版将 `protocol=not-required` 的纯自动规则组单独说明，不再把其空模型/推理字段显示成“None / None”独立裁判；实际语义裁判身份继续按原组展示，缺失身份明确写“未记录”。仅修正展示，不改judge分组、分数、资源或历史封存报告。

`0.8.51` 评分详情内部工作表名将`@`规范为`_`并继续做大小写冲突与长度消歧，模型展示名及原始身份不变，避免XLSX导出器将引用中的`@`当成隐式交叉运算符删除。Markdown与领导版共用显示舍入：只校正浮点聚合在十进制半分界附近不超过两个ULP的机器噪声；显式Decimal/字符串和实质低于边界的值仍精确处理，原始分数与资源不改。

`0.8.50` 执行异常与评分有效性分别汇总。按`evidence-accountability/v1`形成的正式0分属于有效评分，计入有效数和既定平均分；Harness异常不等于评测框架异常。框架/题源故障及尚待用户决策项保持null并说明原因，报告端不补零、不代替裁判、不删项重归一化。原有平均分算法和报告格式不变。

`0.8.49` 目标单元领导版在有效题集不一致时，仍逐维度总结目标单元的实际分数与有效/涉及样本数。总览同步写出有效评分、正常完成和执行错误覆盖；跨端自动评分排名继续沿用原门禁。仅切换总结目标时复用同源规范 Excel 并记录字节一致。

`0.8.48` 端到端计分说明按当前报告的计分政策生成。仅冻结 Rubric 评分的报告直接说明有效分及空分状态；已归档的历史政策保留在来源链中。

`0.8.47` 总览「执行错误数」按用例统计 Harness 执行报错及经冻结执行记录明确识别的原生中断。AstronStudio 的 cancelled 与 ASTRONSTUDIO_TURN_INTERRUPTED 联合识别原生中断，其他取消状态沿用原分类。评分覆盖、有效零分及空分分别核验。

`0.8.46` 统一 WorkBuddy 工具总数与分工具明细。按冻结资源回执的精确调用 ID 对账，取消投影仅保留在原始轨迹，分工具明细统计已持久化调用。已知小计及覆盖状态按原资源回执，原执行、评分与原始证据继续封存。

`0.8.44` 领导版Markdown支持同源端到端计分表，明确Rubric与经核验的用户失败政策分数分别展示；未知值及原评分保持不变。

`0.8.43` 失败政策回放支持已选scoring/execution-records副本：仅按完整身份定位唯一原正式证据目录，并要求原execution-record字节与已选副本完全一致；原Node/SDK/状态/人类政策门禁保持。未知定位或内容差异继续拒绝，不改原分、原件或哈希。


`0.8.41` 同源回放原生空SDK线程初始化通知的合法先后差异，不将MCP初始化当模型执行，不放宽真实turn/待派发/身份与原生拒绝门禁，Rubric和未知资源保持原样。


`0.8.40` 对原生连接清理后的独立stopped-bootstrap证明重放同一严格来源，区分原生明确停止与缺失SDK；故障政策仍须绑定人类指令、真实原生拒绝和唯一选中执行，原Rubric与未知资源保持null。


`0.8.39` 启动失败政策仅在共享核验严格确认原生SDK线程初始化为空、原请求已拒绝未提交且无真实turn/待派发时消费新证明；保留原Rubric null及同源覆盖，不从初始化事件推断模型执行或成功。


`0.8.38` 回放独立idle-bootstrap原生拒绝证明，保留缺失的emptyPrewarm声明和独立连接身份，不改旧Profile或把连接ready/缺SDK当模型成功。原生失败的人类E2E政策0与Rubric未知仍严格分开。

`0.8.37` 离线回放启动拒绝来源时保留严格绑定的MCP超时后ready setup事件；原原生失败/人类政策0/未知Rubric的区分和权重不变，连接后来ready不补造模型turn或成绩。

`0.8.36` 整轮原生中断故障0可包含严格SDK中断证明闭合的native watchdog candidate_error；保留业务错误和原Rubric/根因，不把普通candidate_error或待核验执行统一补零。

`0.8.35` 启动拒绝证明兼容明确provider.session.starting的空预热连接；仍要求原请求rejected/not-sent/not-submitted已结算，emptyPrewarm=true，activeTurnId/lastError/emptyPrewarmDispatch均null且无任何模型turn/待派发/交互。连接初始化状态不被误认成已执行模型任务；未知活动继续拒绝，不重发、取消或重启。

`0.8.34` 修复共享SDK回放模块在Node stdin或非文件启动器下导入时的入口检测；缺少真实argv文件不再触发主命令或抛lstat错误。轨迹解析、证明、资源数值及评分逻辑不变。

`0.8.33` 支持用户显式指定整轮原生中断计故障0：完整run-audit可传单元级native_interruption_zero_policy，对已正式采集的cancelled原生执行重放SDK/SQL/accepted回执闭包并另列E2E策略0。保留原因未知、原Rubric null/unscored和所有资源/计时，不推断框架或模型责任；无可信中断、未知发送、待执行和评分故障不转零。核验允许受原证明约束的零字节原生投影，不捏造缺失行。当前回放适配AStudio既有四种runtime interruption Profile。

`0.8.32` 支持空闲预热拒绝Profile，并校验持续本轮条件规则的派生应用：保留原始人类指令/上下文和SHA，明确派生记录不是新的人类消息；按同一批次的独立已核验失败应用策略零分，不改原Rubric。

`0.8.31` 支持运行审计中的显式用户失败计零决策：只对完整选定范围内、原生未提交启动拒绝proof离线回放通过的unscored失败另列端到端0分。总览和完整逐题表同时展示Rubric与端到端口径；原score/valid/能力维度不改，未知失败、额度与评分异常不可自动补零。决策、人类条件授权和冻结原证据逐项绑定SHA并进入审计/规范封存。

`0.8.30` 复算显式bound-native-runtime-reconciled-interruption/v1及stale-session证明：核验原SDK中断、SQL最新头的runtime终态、需要时同快照原restart-reconcile事件及accepted回执。原state滞后字段不改，缺少provider终态的原部分行不丢弃，资源保持partial/原生终态序号null；失败或未知分不补零，不推断人工取消或改变评分资格。原版本证明保持兼容。

`0.8.29` 可显式传`--run-audit ABS`，对完整选定范围逐题绑定执行/评分attempt，核验管理员原生区间审计的来源SHA并重算区间重叠峰值，另列配置槽位、区间覆盖及控制审阅暂停。缺失区间不补零，部分峰值仅是下限；不把配置当实际并发，不从区间重叠推断始终满载或同时HTTP请求。MD/Excel/JSON同源披露，规范化审计进入原回执和封存包；分数、原流程/任务耗时保持原值。输入审计必须先完成真实原生身份/边界核验，哈希相符本身不证明未见事件。见[运行编排审计](references/run-audit.md)。

`0.8.28` 完成态原生落盘终稿为同一消息SDK终稿严格非空前缀时，另存分歧原件/精确绑定证明并保持partial；原回复不补全、不替换，评分仍由原证据门禁决定，不能因SDK正文完整自动授分。

`0.8.27` 原生运行时中断另支持显式缺失生命周期投影Profile：同一只读SQL快照须证明0条事件/零字节原件，或全量仅有与SDK total/last用量逐项一致的资源镜像；SDK仍完整绑定原Prompt及中断，只确认失败已停止，缺证保持partial、终态序号null，不补造行、不改变评分资格。

`0.8.26` 资源复算重新核验原生runtime中断的SQL/SDK/provider证据闭包；中断结果及未知分数保持原状态，不作为能力零分，也不将运行时中断归因为人工停止。

`0.8.25` 以豆包共享组件0.8.16复算2.35.19独立原生SDK工具统计；版本/来源证明不混用，旧Profile和未知资源null语义保持。

`0.8.24` 将预览视口隔离固化为正式流程：重算后只导出一次Excel，每张左侧、右侧及异常预览从该内存导出文件独立载入，避免跨图视口残留裁切。预览副本不重新导出，也不改最终Excel；脱仓运行携带独立预览模块，校验回执记录隔离Profile和预览数量。既有评分、资源、工作表布局、冻结输入和旧报告不变。

`0.8.23` 正式分发DoubaoWork共享证据组件0.8.15，报告端可严格复算2.35.15原生MOA SDK工具计数。核对冻结轨迹、assignment、原生身份、媒体及调用SHA后复算，未知Profile和漂移仍拒绝；不从旧GUI展示计数，也不补造Token/请求数。原执行、评分和资源字节不改，旧报告发行保留。

`0.8.22` 同步共享WorkBuddy证据核验组件0.2.7，保留被拒绝响应的原生API说明来源及SDK缺口警告；报告分数、权重和已有封存原件不变。

`0.8.21` 将单一配置领导版和待核验展示纳入正式入口。`--display-config`支持`pending_review: [{task_id, unit_id?, reason}]`；只允许已完成执行且`score_status=evaluation_error / total_score=null`的显式题目，不能隐藏有效低分、真实零分或未评分。原任务状态、分母和分数不改，JSON另记展示别名；MD与Excel总览、用例比较及评分明细同步显示待核验。单一配置不再虚构参照组合，部分资源仍保持覆盖与下限说明。

`0.8.20` 的只读评分校验同时核验历史会话 running 投影与原始 SDK completed 的显式证明；新旧评分、真实零分、评测异常和资源缺失仍按原身份与 SHA 汇总，不改原执行状态或补零。

`0.8.19` 同步 general-resource-supplements 1.3.5 的显式紧邻 compaction 持久化延迟审计；保留完整 SDK 正文、原始来源和旧 Profile，不把冗余镜像缺失变成候选能力扣分。

`0.8.18` 校验原契约独立有效性v2的精确SHA注册、动态能力m、多个检查点同维聚合、证据/原聚合Worker闭包及null传播；来源业务豁免与实际能力可独立记录，不归一缺失项。旧SPY v1和旧60题七维视图保持原行为。


`0.8.17` 支持有SHA引用的独立业务/能力评分文件：逐项重验来源、身份、原始语义检查点及45分能力预算，不把业务有效性当作过程能力证据。能力缺项保留null和涉及样本数；业务分失效但明确有独立有效能力证据时，仅对应能力维度可进入其自身统计。普通旧评分保持原门禁，旧60题七维映射不变；详情保留全部6个语义检查点和未判定状态，不以业务视图替换能力分。

`0.8.16` 在领导版开头和 Excel 总览披露评分覆盖；按真实任务 ID 检查各单元有效题目集合。当集合不同（即使有效数量相同）时，保留各自描述性均分，停止自动撰写得分高低比较，不将部分评分视为完整评测集排名。原分数、分母、资源及来源不改写。

`0.8.15` 按实际选中执行记录读取显式 UTF-8 补采资源：仅接受已绑定的 bound-qwen-native-utf8-redecode/v1、新采集回执中的执行/manifest SHA、相同原执行身份和指标 SHA。初始采集记录保留，不把旧 manifest 的资源路径误用于新评分输入；没有该明确 Profile 的其他漂移仍拒绝。

`0.8.14` 同步 workbuddy-jsonl-metrics 0.2.3，保留原 traceId Profile 的完整历史复算行为，并继续严格验证新版独立 request ID Profile。旧资源字节与统计值不改写。

`0.8.13` 随包分发 workbuddy-jsonl-metrics 0.2.2，复核新版客户端分离的 conversation request ID 和 distributed trace ID；旧冻结快照仍按原协议复算，报告分数、分母和资源口径保持不变。

`0.8.11` 保留 `checkpoint_capability_map7.yaml` 的全部旧七维映射，新 116 题使用独立 `checkpoint_capability_map5.yaml`。按实际任务选择七维或五维列；同时涉及两套映射时分表展示。兼容视图均按任务内映射检查点均值、再对任务均值取平均，披露有效/涉及样本数；不把五维折算为七维，不把缺失证据补零。此兼容视图不代替题目内另外定义的能力预算或父检查点诊断公式。


`0.8.0` 与 Web 统一展示“流程耗时”和“任务耗时”。新流程计时 Profile 从 Prompt 发送至本机确认终态；旧冻结来源继续按原 Profile 核验，调整历史口径只能使用保留来源身份及 SHA 的补充层。

# 汇总 General E2E 报告

`0.8.12` 同步 general-resource-supplements 1.3.4 的 unified exec 计时审计分发。进程耗时与单次输出等待耗时分别保留，不合并为一个工具计时；报告原有任务耗时、资源、分数与分母口径不变。

`0.8.10` 的研发索引引用 submission 实际采用且与 score SHA 绑定的 `scoring/execution-records`；初始正式采集记录单独保留路径与 SHA，不再把合法补采误报为原件漂移，也不声称新旧轨迹等价。原包成员、身份、评分绑定校验保持不变。

生成报告时建议显式传入 `--seal-output-dir /absolute/new-archive-directory`：在同一生成进程返回前验证回执并封存规范 ZIP，避免宿主随后修改独立 XLSX 的元数据。`selected_report.py` 也支持此参数。单独封存已有、仍满足原回执的报告可用 `scripts/seal_report.py --report-dir ABS --output-dir ABS --batch-root ABS`；跨来源 composite 报告不需 batch-root。已发生的字节漂移必须保留并用新生成流程处理，不删除属性或修改旧 SHA。研发导出使用 run Skill 的 `--canonical-report-archive` 读取封存成员，独立变体另存。

`0.8.9` 的独立发行同步 general-resource-supplements 1.2.9 已知原生投影对账组件；报告聚合、分母、分数、资源口径不变，不据此重算或覆盖历史回执。裸 Excel 被宿主追加属性时保留变化字节和审计，以登记后封存 ZIP 内的原始成员为严格 SHA 权威，不移除标记或改旧哈希。

`0.8.8` 更新随包 general-resource-supplements 至 1.2.8，以分发静态复合命令 search 投影兼容。仅更新共享依赖，不改变报告统计口径、评分或历史原件；旧发行与旧报告不覆盖。

稳定轮次使用 Harness/execution/tasks 与 Harness/score/tasks，报告位于根目录 reports。历史归档可通过 run Skill 的 archive_round.py replay 在临时目录重建输入；selected_report.py 的 --data-output 输出已验证 JSON，不必重新渲染 Excel。原执行、评分、资源与 SHA 均须一致，路径迁移另记映射，不能修改已冻结原件。

AstronStudio 归档含 `raw/astronstudio-rollout.jsonl` 时，工具统计从已验证 rollout 复算真实工具名和唯一调用 ID，不能继续按 `commandExecution/fileChange` 分类。原生工具搜索也计入；结果事件不计。模型请求数为已对账的用量推进次数，区别于 HTTP 尝试。`selected_report.py --resource-root` 支持独立 rollout 补充层及其既有资源补充链，保留原执行和评分 SHA，报告记录新旧指标与 rollout 路径/哈希。

rollout profile 2 同时提供 Token 和原生任务耗时。Token 从去重并对账后的单次用量累计；任务耗时直接采用原生 `duration_ms`。新流程计时 Profile 采用 Prompt 发送至本机确认终态；旧记录按原执行器边界复核，不静默迁移。报告必须按补充记录中的 profile 复算：旧 profile 1 的冻结统计保持原样，新评测和新补采使用 profile 2；缺失字段保留 unavailable，不从桌面事件静默回填。

从通过身份、哈希和协议校验的回传包生成可复算汇总，显式披露范围、覆盖率与异常分母。

## 当前能力

`0.8.7` 将管理员报告中验证过的展示与领导版逻辑纳入源码：单元名包含客户端版本，默认不加轮次后缀；用户指定的客户端选项名通过展示覆盖配置设置，原实际模型及验证状态不变。领导版默认优先同Harness、同客户端版本的模型配置对照，所有表格仍保留全部单元；无同版本参照时显式回退组合对照。差值和资源倍数均使用最终Excel未舍入值。“效率与资源”固定包含“Token对比”和“任务耗时对比”，各总结位于对应标题下、表格前。

以新目标重生成领导版、限定主要比较范围、简化展示名或迁移管理员数据输出位置时，读取[报告展示与跨批次审计](references/report-presentation.md)。历史兼容性例外须绑定审计文件SHA和逐题原执行/评分，不能仅凭一组允许签名关闭材料冲突门禁。七单元的来源索引、既有裁决、路径和规范ZIP属于该次报告的冻结审计，不硬编码进Skill，不改写已发布套件。

`0.8.5` 在报告阶段通过绑定执行身份、rollout SHA 和请求 SID 补充 MaaS 模型耗时，使用 `maas_cube.perf` 毫秒累计口径。效率表增加总/平均模型耗时、模型耗时占比及逐题模型耗时 P50/P90，聚合任务耗时统一标为“总任务耗时”。支持离线缓存与按 SID 查询 ES；全量和共同任务视图复用同一份逐题结果。认证只读取环境变量，原执行、评分与资源协议不改写。用法及覆盖规则见 [MaaS 模型耗时](references/maas-model-timing.md)。

`0.8.4` 支持在效率 Sheet 下方追加显式资源筛选对比：保留全量表，在 `presentation.tables.效率对比.additional_views` 写入同格式的 Token 表和原生任务耗时表。只按用户指定的单元/任务排除，不自动剔除其他失败或长尾任务；逐单元披露纳入用例数，平均值分母及分位数使用筛选后的任务集合。部分小计、缺失值、覆盖表和排序规则沿用全量表；排除清单及原身份另存，原始任务、资源和评分不改写。追加视图显式设置 `header_row`、`timing_table` 和 `render_row_count`，主视图的预览范围覆盖追加区域。

用户要求统一剔除异常用例时，取指定异常任务 ID 的并集，从所有参评单元统一排除这些任务，而非只删除发生异常的单元行。须验证每个单元剩余任务 ID 集合完全相同；均值以共同集合的用例数为分母，分位数按该集合重新计算。AstronStudio 不同版本仍保留为独立报告单元。

`0.8.3` 的领导版“工具调用”总结围绕配置的目标单元说明每题平均调用次数、相对各参照的倍数及主要工具构成，不逐项陈列参照总次数。平均调用次数使用冻结用例数作分母，倍数从最终 Excel 的未舍入计数计算；计数覆盖不足时披露下限或观测值比较，缺失及零分母不计算倍数。工具明细覆盖不完整时，占比只针对已知明细，不能表述为全部调用占比；不从次数推断工具成功率或能力优劣。

`0.8.2` 在效率 Sheet 和领导版“效率与资源”章节增加任务耗时总量、平均值、P50、P90表。只读取原生 `agent_duration_seconds`，平均值以冻结用例数为分母，包含失败任务；分位数仅在逐题计时完整覆盖时按线性插值计算。缺失任务耗时不以流程耗时替代，部分统计明确标注下限，完整覆盖另列，不增加工作表。

效率 Sheet 的 Token 表必须在上方显示“Token 对比（总 Token 升序，缺失值置末）”，按展示的总 Token 数值升序排列，未知值置末；已知小计参与排序但保留部分统计标识。覆盖表、单元数据和浅黄色小计标记必须同步重排，不能沿用总览的得分排序。领导版 Token 表复用该顺序。

`0.8.1` 的领导版“效率与资源”总结围绕目标单元说明平均 Token 相对各参照的倍数，使用最终 Excel 提取的未舍入数值计算。目标参数与显示名沿用配置；缺失或零分母不计算倍数，部分覆盖明确披露下限或已知用量比，不能冒充全量精确比较。

`0.7.5` 随资源补充组件分发共用 SQLite 快照复制能力，macOS 优先原生 APFS 克隆；未改变已有报告统计、Token Profile、分母或冻结材料复算政策。

`0.7.4` 提供 `astronstudio_context_diagnosis.py`：从明确选中的执行身份、rollout SHA和原报告用量做只读诊断，统计思考、助手正文、工具参数和工具返回字符，关联相邻请求的原生输入增量。有新内容但累计usage未推进的区间单独保留，不能套用旧usage或并入下一次响应。字符/Token换算只使用本轮已计量文本的经验分布，并标记为估计；完整请求缺失时不作精确输入角色归因。

`0.7.1` 增加：分组工具表头、逐字段覆盖及部分小计、中文分类与用例数、秒级Excel名称、`--target-unit`领导版，以及独立的 `token_growth_analysis.py` 请求级 Token 增长分析。目标单元用于文字总结，各表保留全部参评单元。`report.display_overrides.unit_model_labels`可带`label/reason`修改展示，不改原模型验证信息。采集后的通用资源补充层会在报告时重新核验并复算。

`0.7.13` 支持同一单元从多个已导入的标准回传包逐题选择：source index 的 `imports[unit_id].packages` 枚举原 package ID、target 和 manifest SHA，task index 每题必须显式指定 `source_package_id`。每个来源范围须为目标任务全集的有序子集，客户端版本、模型和执行模式须一致；原 batch/attempt/回执保持不变。单一来源格式继续兼容，不生成虚构的全五题采集回执。

不同冻结来源使用`scripts/selected_report.py --workspace-root ABS --batch-root ABS --source-index ABS --task-index ABS`显式逐题选择；默认只读，追加输出目录与Excel运行时才发布。保留每条原批次/attempt身份和资源修正谱系。普通报告同时生成`developer-source-index.json`及`developer-task-index.json`供研发打包。

先运行：

```bash
python -m eval_general_e2e skills --name report-general-e2e --json
```

`0.7.1/operational` 支持按模型@Harness 展示 General 结果、效率和维度对比、每题各单元并列的用例对比明细，以及每单元独立评分详情，生成不含根因分析的领导版 Markdown、Excel 与单独审计报告。新增请求级 Token 增长分析：AstronStudio 只读取绑定 rollout，WorkBuddy/QwenWork 使用冻结标准轨迹；DoubaoWork 在缺少 Token usage 时默认排除。输出首轮/末轮输入、增长倍数、交互斜率和归一化中位数曲线；系统提示词精确拆分需要完整 outbound request payload，不能从 usage 反推。合法 `partial` collect receipt 可进入报告，未知 Token/cache 等字段继续显示为不可用，不补零。保留 WorkBuddy 已冻结评分后的 JSONL 和耗时补采。仍须使用真实回传包；不得把 Web 报告或旧 CLI 报告仅改标题后发布。

DoubaoWork 历史回执的资源展示另做保守复核：按原 source SHA 验证 trace-index 和 execution-state，partial 工具轨迹只保留已知调用小计；旧回执只有同一本机时钟的原生完成接收事件才与 dispatch 相减；新流程计时 Profile 使用经绑定的本机终态观察时刻，支持经绑定原件证明的 checkpoint perf_mark_samples.task_finish.receiveTimestamp。服务端完成时间或未知时钟不计流程耗时及批次壁钟覆盖。报告 JSON 的 lineage 记录旧值、原因和证据 SHA；原 execution/resource/score 文件及评分分母保持冻结。

`0.7.0` 将 Markdown、审计和单题文字分数的显示舍入统一为十进制 ROUND_HALF_UP，与 Excel 数字格式一致；只改变显示，不改报告 JSON 中的原始分数、聚合分母或资源值。

## 责任边界

- 输入：校验通过的 submission、回传包和冻结报告配置。
- 输出：同源可复算 JSON、Markdown、Excel，以及资源覆盖率和异常分母。
- 枚举冻结任务全集；失败和未评任务保持显式状态，不能缩小分母。
- 未全量覆盖的资源指标只展示已知小计与覆盖数；全缺失不补零。
- 不调用被测 Harness、不补做 criterion 判断、不覆盖旧 attempt。

## 运行前提

- 批次根目录含 `manifest.json`、`report-config.json` 和 `.general-e2e/run-general-e2e-import-index.json`。
- 每个 unit 必须已有唯一显式选择的 return package；冲突未选择时失败关闭。
- 使用带 `@oai/artifact-tool` 的 Node runtime。通过 `--node-modules` 指向该 runtime 的 `node_modules`，或设置 `GENERAL_E2E_NODE_MODULES`；可用 `GENERAL_E2E_NODE` 固定 Node 可执行文件。
- Skill ZIP 内已 vendoring `general-contracts`，运行时不读取 WildClawBench checkout。

## 输入校验

先独立校验批次和回传内容：

```bash
python scripts/report_general_e2e.py validate-inputs \
  --batch-root /absolute/path/to/batch
```

校验会重算已选 package 的成员 SHA、package ID、unit manifest、collect/package/import receipt、submission、execution record、score 和 resource metrics；导入后的漂移仍会失败。

若回传包含 `unit/evidence/resource-supplements/<task-id>/`，报告端用随包 `workbuddy-jsonl-metrics` 组件重验原 execution/resource/collect receipt 的 SHA、session/cwd/Prompt/请求归属，并复算每个补采数值。验证命令需要 Node（默认 PATH，可用 `GENERAL_E2E_NODE` 指定）。失败不能回退为旧值。补采仅替换报告的资源观测；score、submission 与原 execution record 保持原哈希，JSON lineage 同时保留新旧指标及补充清单哈希。旧 WorkBuddy 顶层 request=1 不能继续冒充模型调用次数，未补采时该值展示为 unavailable。

## 生成报告

### 请求级 Token 增长分析

报告生成后，可用独立入口分析每题内的模型请求序列。AstronStudio 只读取绑定的 `raw/astronstudio-rollout.jsonl`；WorkBuddy/QwenWork 读取评分工作空间冻结的标准轨迹；DoubaoWork 默认排除。该分析不改写标准报告、分数或资源回执：

```bash
python scripts/token_growth_analysis.py \
  --round-root /absolute/evaluation-root \
  --report-json /absolute/evaluation-root/reports/<report>/general_e2e_report_data.json \
  --output-json /absolute/evaluation-root/reports/<report>/token-growth-analysis.json \
  --output-md /absolute/evaluation-root/reports/<report>/token-growth-analysis.md
```

输出首轮/末轮输入 Token、末轮/首轮增长倍数、每轮输入斜率、输入/输出/推理合计和归一化交互曲线。`system_prompt_tokens` 在没有完整 outbound request role payload 时必须保持 unavailable；首轮输入只能作为混合基线，不能解释为纯系统提示词。

### AstronStudio 输入增长定位

完成结果选择并生成逐题 `TASK_INDEX.json` 后，提供同源报告JSON与绑定rollout，可进一步定位大幅输入增长前的内容来源。支持索引引用的rollout补充层或原执行trace-index。默认报告路径为根目录reports/final，也可显式指定：

```bash
python scripts/astronstudio_context_diagnosis.py \
  --round-root /absolute/evaluation-root \
  --task-index /absolute/evaluation-root/TASK_INDEX.json \
  --report-json /absolute/evaluation-root/reports/final/general_e2e_report_data.json \
  --output-dir /absolute/evaluation-root/reports/context-diagnosis-new
```

输出Markdown、JSON及相邻请求变化CSV；原始内容只保存行号、SHA和长度，不复制完整思考正文。`--jump-threshold`默认为10000 Token，是排查筛选条件，不是能力评分或因果判定阈值。输出目录须为新的目录，原回执和结果不覆盖。

若回传包含 `unit/evidence/timing-supplements/<task-id>/`，须按归档的运行时请求起止时间和原 execution record 的 `prompt.sent_at` 复算，同时核对它绑定的 Token 补采 SHA。原生请求生命周期为 `agent_duration_seconds`，发送到原生完成的流程时间为 `duration_seconds`；不等同于模型推理时间，批次墙钟时间仍按冻结 execution record 计算。任一补采漂移均拒绝报告，不覆盖旧评分、原始证据或旧报告。

```bash
python scripts/report_general_e2e.py generate \
  --batch-root /absolute/path/to/batch \
  --output-dir /absolute/path/to/batch/reports/report-id \
  --node /absolute/path/to/node \
  --node-modules /absolute/path/to/node_modules
```

默认渲染 `9 + 单元数` 个工作表及其 PNG 预览，顺序为：总览、效率对比、分类对比、难度对比、Agent能力对比、模态对比、工具调用对比、用例对比明细、各单元评分详情、资源覆盖与异常。只有明确不需要预览时才传 `--skip-preview`；这不会跳过工作簿结构、关键范围和公式错误扫描。

`--output-dir` 必须位于 batch root 内，使 report receipt 的 artifact 路径能由 `run-general-e2e` 以 batch root 为基准重验。最终目录必须不存在或为空；生成器使用同父目录暂存并原子发布。

## 输出

- `general_e2e_report_data.json`：唯一可复算数据源。
- `通用场景端到端自动化评测报告.md`：不带根因分析的领导版报告，与 Excel 使用同一组单元对比表。
- `通用场景端到端评测审计.md`：执行状态、裁判协议、资源覆盖及谱系，保留异常、未评分和历史状态。
- `通用场景端到端自动化评测报告.xlsx`：九张公共表加每单元一张评分详情。
- `previews/excel-validation.json`：Sheet、关键范围和公式错误扫描记录。
- `previews/*.png`：各 Sheet 视觉检查图（未使用 `--skip-preview` 时）。
- `cli-adapter/`：`score.json / usage.json / execution_status.json / task_output.json` 兼容视图；异常和缺失仍为 `null`，不会补零。
- `receipts/report-receipt.json`：可供 `run-general-e2e record-receipt --stage report` 登记的标准回执。

## 统计口径

- 主均值分母仅含 `score_status=valid`；真实 `0.0` 是有效能力零分。
- `evaluation_error` 和 `unscored` 保留在冻结全集但不进入能力均值。
- 分类、难度、unit 与裁判协议均复用同一任务运行集合；裁判按 protocol、model、reasoning effort 分组。
- 每个资源字段独立统计。仅所有任务运行均完整覆盖时写 `total`；否则为 `null`，并展示 `known_subtotal`、任务运行覆盖和原生事件覆盖。
- 批次壁钟按最早任务开始至最晚任务结束计算；任务耗时之和单独展示。

## 对比报告口径

- 总览每个 `模型@Harness` 一行，优先使用执行记录中已核验的实际模型；无法确认显示“未知模型”，单个 unit 中实际模型混杂时显式显示“混合模型”。显示名重复时加 unit ID，不能自动合并。
- 总览不展示成本、超时数；拆分“任务耗时(s)”（原生请求/Agent 耗时之和）与“流程耗时(s)”（含发送及等待）。保留有效评分数、未评分数；评测异常数按执行基础设施异常或评分异常的任务并集计数。完成率仅指原生正常完成率，不是正确率。
- 效率对比：模型@Harness、总 Token、平均 Token、普通输入 Token、缓存命中输入 Token、缓存写入输入 Token、输出 Token、缓存命中率。普通输入=归一化输入总量−Cache Read−Cache Write；三项完整可观测时才计算，未知缓存不能按 0 扣减。Cache Read/Write 分别映射 `cache_read_input_tokens`/`cache_creation_input_tokens`，缺失显示 `-`。平均 Token 分母为冻结任务运行数；缓存命中率仍使用缓存命中输入/含缓存的输入总量，不能改除普通输入。输入为 0 或覆盖不全时为空，不平均逐题比例或重复累加缓存。
- 工具指标本版只展示调用数与按工具名分组的已知数量，标准 transcript 中每题 call ID 去重，与原指标对账后标注明细覆盖。`completed` 不等于工具成功；不实现格式准确率、执行成功率、不确定占比。
- 七维能力复用公共 `checkpoint_capability_map7.yaml`。自动检查点来自评分引用并带 SHA 的 `rule-component.json/raw_scores`；语义检查点来自 score.criteria，按规则/语义命名空间对齐。任务内映射检查点均值再对任务取均值，缺少任一映射检查点的该任务不进入该维度；同时披露有效/涉及样本数，缺失不补零。不重做判分、不把任务总分替代未映射检查点。
- 构建时冻结公共实体显示名和能力映射为 `data/report-reference.json`，随包携带 canonical YAML 及 SHA；脱仓报告无需 PyYAML。公共字典来源在 JSON 和资源审计表保留。
- 分数展示统一为 0–100；底层评分与 CLI adapter 保持 0–1。Excel 和领导 Markdown 都读取 `presentation.tables`，禁止在渲染层另算分数。单元题目范围不同或模型/Harness 同时改变时，明确属于组合对照，不做单因果归因。

## 用例对比与单元评分详情

- 总览“工具调用数”紧随“总请求数”，后接任务耗时与流程耗时。
- 用例对比明细沿用常规报告前十列：分类、用例ID、用例名称、难度、模态、标签、输入(Prompt)、预期行为、评分标准、检查点；后接每个模型@Harness 的总分与检查点明细，以及最优单元、最大分差。每题一行，缺席/无效评分不补零；至少两个有效单元才计算最优和分差，并列最优全部保留。
- 从已选 return 的 scoring attempt 读取 `attempt-manifest.json`，核对 dataset、执行/评分身份与 task/contract SHA，再读取冻结 `private/task.md` 和 `contract.json`。不读取当前仓库题目补写历史；旧包缺少题面时显示 `-`。同题不同单元的题面哈希或基础元数据冲突时失败关闭。
- 评分详情每 unit 一张，名称 `评分详情_<模型@Harness>`，超过 Excel 31 字限制或发生重名时截断并加 unit 摘要；`presentation.score_detail_sheet_names` 保留精确映射。
- 详情可展示冻结题面、预期、规则、Workspace/Skills/Env/Warmup 声明，执行/评分状态、总分、检查点、失分点、裁判判词、执行/评分错误、Token/请求/工具数、双耗时、标准 JSONL 引用。Env 仅为题目声明，不读取运行期环境变量值。未加入超时、多轮统计、根因分析或工具质量比率。
- 题面、规则和判词等长字段显示明确标注的节选，全文保留报告 JSON；执行记录展示回传包内标准 JSONL 路径，不将整段轨迹塞进单元格。对比格以总分背景色提示，不使用颜色推断各检查点结论。组件总分和诊断计数不冒充检查点或失分点。

更多字段说明见 [报告数据与 CLI 适配](references/report-data-and-cli.md)。
