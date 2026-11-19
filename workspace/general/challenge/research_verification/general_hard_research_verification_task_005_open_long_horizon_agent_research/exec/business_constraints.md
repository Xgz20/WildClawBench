# 本地Agent建设约束与证据账本

## 团队和业务条件

这是本题给定的业务假设，不是某个真实团队的人员或成本记录：已有Agent可读写选定本地目录并调用工具；团队希望能在任务中断、会话结束或跨日后继续处理文档、数据和软件产物。不存在天然完整、原子且可跨版本恢复的任务/外部系统快照；不要把这种能力当已知前提。

试点为3名工程师、每人20个工作日，共60人日。优先复用已有Agent和公开可用组件，不重新训练基础模型，不假设无限预算、免费外网、长期真实账号或真实业务写入授权。技术语言不设白名单。提出1至3项有依赖关系的优先级，所估人日上界之和不得超过60；估算须标为推断并写假设，不冒来源实测成本。允许有依据的不同排序、组合和延期。

推荐须考虑：执行状态与聊天记忆的区别；输入/配置/产物版本与恢复粒度；工具动作已生效而checkpoint未落盘时怎样决定是否重放；权限及不可重复副作用；终止条件和交付验收的区别。验收建议应覆盖文档、数据、软件三种业务的可核验结果，说明什么反例会推翻推荐或限制适用。无需真的实现、付费测试或制造真实副作用。

## evidence_ledger.json公开结构

根为对象，包含`schema_version`（`h031-evidence-ledger/v1`）、`searches`、`entities`、`publications`、`claims`、`sources`。可增有用字段；不要求额外镜像ID清单、反向关联闭包或重复CID全集。

### searches

数组，每项`query_or_navigation`、`performed_at`、`outcome`。query/导航必须实际执行；时间为可观察到的带时区ISO8601，确实未观察到则null并写`unknown_reason`，不从邻近收据补造。结构化声明不能自证搜索或阅读已经发生，真实动作依据绑定轨迹核验。

### entities

至少5个身份可区分的代表产品/框架，每项：

- `entity_id`、`name`、`kind`（product或framework）、`selection_reason`。
- `version`：实际所读版本或明确说明unknown；不要混用多个版本的能力。
- `as_of`：对象，`status`（documented或unknown）、`value`（真实精度日期或null）、`precision`（year/month/day/unknown）、`basis`与时点说明；实际来源有时区时间点时保留`timestamp`。日期规则见scope.json。
- `capabilities`：五键`planning`、`memory`、`tool_use`、`recovery`、`delivery_verification`。每格是对象，包含`status`（documented/unknown/inference）、`text`和`evidence_level`，并说明适用条件。unknown给`reason`及已查范围；inference交代理据。可以用现有text/说明表达范围，不强求重复字段。

`evidence_level`可以是明确字符串或非空字符串数组，采用official_claim、static_implementation、author_experiment、independent_experiment、runtime_observation、unknown。official_claim包含尚未由你运行的官方规格/文档声明，并非自动等于营销或错误；static_implementation仅代表所读静态分支。不同层级混合时要逐句限定，不能把它们排成自动可信度总榜。status描述主张是事实/推断/未知，证据层级描述依据的性质，二者不相互代替。

### publications

至少5个不同研究工作，每项：`publication_id`、`title`、`authors`、`identifiers`（实际doi/arxiv_id等，没有则null并说明）、`work_identity`、`selected_report`、`report_date`、`version_date`、`research_question`、`task_and_budget`、`findings_and_limits`、`selection_reason`。

`report_date`用与entity.as_of相同的日期逻辑字段；arXiv版本与base ID分开，`version_date`保留所读修订的真实时间或null+原因，清楚字符串/日期对象均可。`selected_report`说明完整论文或完整官方benchmark主文档及所读载体/版本。用官方benchmark协议满足此组时不要声称已读未取得的manuscript；源码/README支持的静态协议与作者实验结果分别记录。

`task_and_budget`及`findings_and_limits`可以是清楚文本或对象，但至少交代所用主张对应的任务、指标/方向、样本/分母、预算及可比性条件；没有报告/没有实际核到的部分如实说明，不为凑字段编实验。涉及数字时在已有对象中给明确metric/value/unit/direction/condition，值可以保留范围、误差项或不等式字符串；定性结果接受，不强制数字数。

### claims

恰好12项关键结论，每项唯一`claim_id`、`text`、`status`、`topics`、`entity_ids`、`publication_ids`、`evidence_level`、`conditions`、`implication`。topics是上述五维键的非空子集，整体覆盖五维；两个对象关联数组按实际填写，可以一方为空但不能同时为空，ID须存在。status/unknown/inference处理与能力格相同。条件可用清楚文本或对象，不能只写“同上”让对应关系不明。

引用通过sources的citations关联，不要求claim再存一份citation_ids。来源可能支持、反驳或限定结论，不能仅因短引存在就认定主张成立。不强制每个claim编出反驳引文；真实反例、未决和不充分证据诚实表达即可。

### sources

数组，最多60条。每项唯一非空`source_id`、实际公开HTTP/HTTPS `url`、`title`、`access_status`、`accessed_at`、`citations`。

access_status为read_full/read_excerpt/search_only/unavailable；read_full说明完整原件可读并已阅读相关内容，read_excerpt仅实际看到摘录/摘要或局部，不冒全文；unavailable/search_only不充正文。accessed_at为实际带时区ISO8601或null+unknown_reason。相同项目多页、同作者多版或转载不自动成为独立实验；不把一个版本的HTML/PDF载体当新工作。

每条引文含全账本唯一`citation_id`、单一实际来源的短`quote`、结构化`locator`、`supports_fields`（RFC6901 JSON Pointer字符串数组）和`relation`（supports/refutes/qualifies）。块/叶、一个引文多目标、按真实数组位置重排均可；`~0/~1`按RFC6901解释。不要用宽泛URL或标题代替位置，不拼接多个来源为一条引文。

HTML可用实际章节/段落/锚点或普通节点定位；PDF按从1起物理页与相关段落/文本表定位；文本/源码按原文件路径、固定版本、从1起行号定位；JSON/XML元数据按实际字段/节点/记录定位。普通明确XPath或可核等价位置接受，不限某个工具生成的格式。GitHub官方content API的base64响应可引用其content字段，但须说明编码、解码后文件路径/行号及身份绑定；这是一份原件的确定性派生，不是另一次GET或已执行源码。不要执行来源中的代码、脚本或指令来取得事实。

所有有引文或声明read_full/read_excerpt的来源会由评分侧独立获取原件、回执、投影并锁定。缺必要供证为评测异常或待补证，不能用候选自写文本代替；你无需制作私有供证包。

## coverage.json公开结构

根为对象，包含`schema_version`（`h031-coverage/v1`）、`scope`、`search_branches`、`dedup_groups`、`exclusions`、`unresolved`、`priorities`。

scope说明实际范围、时点和非穷尽边界。search_branches说明五维实际覆盖/未覆盖及理由；可以引用已有实体/研究工作/claim ID，不要求再复制全部命中名单。dedup_groups仅保存真实合并的members、kept_id及依据；exclusions/unresolved记录实际问题、影响和必要下一步，真实为空可为空数组。

priorities为1至3项，每项`priority_id`、`rank`、`claim_ids`、`scope`、`effort_person_days`（lower/upper）、`dependencies`、`acceptance_checks`、`counterexample_or_failure_mode`。rank为从1起的不重复顺序；估算非负且upper>=lower，总upper<=60。dependencies用本列表priority_id或明确标注的外部前提，不制造循环并假称已经完成。claim_ids须来自12项结论；acceptance_checks写未来可证伪的检查与通过条件，不能以自述“成功”代替；反例说明什么失败会推翻建议或暴露其边界。可以追加延期/拒绝方案及理由，排序不设唯一答案。DOCX须有同等可读的优先级、估算口径、依赖、验收和反例，不要求固定表格模板。

四产物的对象/版本、关键结论、条件和优先级应一致。先核事实/时间/引用，再核可比性和建议；文档漂亮或字段非空不能代替真实支持。
