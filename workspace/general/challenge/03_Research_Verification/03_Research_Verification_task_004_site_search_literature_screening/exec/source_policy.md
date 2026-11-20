# 发现、来源与证据记录

## 发现与公开访问

从arXiv（arxiv.org）和PubMed（pubmed.ncbi.nlm.nih.gov）自行发现报告。可使用站内搜索、搜索工具、浏览器或等效导航；不规定第一条query、搜索语言或`site:`语法，不提供答案题名、编号或URL。应实际尝试两个平台，记录真实query/导航、时间、返回线索及不可用情况；不要求某个平台最终贡献固定篇数。

可从发现记录跟随公开DOI、出版者、官方全文库、相关官方公开只读元数据接口或身份明确的公开全文稿。不能把某个域名、标题或URL名单当合格论文白名单。不要登录、付费或改变安全网络规则；不可达时可寻找可核的公开等价全文，并记录路径及其版本身份，不能把其他论文或摘要替代原全文。

区分搜索结果、报告书目记录、完整正文和实际引文。HTTP200、搜索摘要、空壳、登录页、验证码页或部分下载不证明全文可读。仅摘要或局部摘录只支持实际看到的事实；无法继续访问应说明，不写成已读全文。一次有明确理由的切换或重试可以记录，但不要求机械完成固定重试次数。

评分侧会独立获取实际引用的公开来源并核对原件、元数据、投影和回执。你保存的快照或自写文本不能自行成为独立供证；你无需创建私有来源包或运行评分程序。评分侧取证缺失与候选交付错误应分开处理。既有可信快照如被独立采集流程明确复用，其原获取时间及复用事实应保留，不能写成此次新GET或当前网页仍可达的证明。

## evidence_matrix.json公开结构

JSON根为对象，包含`schema_version`（`h030-evidence-matrix/v1`）、`searches`、`records`、`works`、`sources`、`flow`。除下列最小字段外，可增加确实有用的信息；不要为凑字段制造事实。

### searches：实际检索/导航记录

每项包含：

- `site`：arxiv或pubmed。
- `query_or_navigation`：实际query、筛选条件或导航过程，不能用事后计划替代。
- `performed_at`：可观察到的ISO8601时间并带时区；确实不可观察时为null并说明`unknown_reason`。
- `outcome`：实际得到的线索、没有命中或不可用情况的简述。

不强制给每次搜索额外分配ID，也不要求重复一份全部命中ID清单。与某条报告的发现关系在该报告的`discovery`中说明即可。结构化记录本身不能证明检索动作已经发生，过程证据以实际绑定轨迹为准。

### records：报告/所读版本记录

每项包含：

- `record_id`：本文件内唯一、非空、稳定的字符串，不限定前缀。
- `work_id`：归属的工作ID；身份关系未解决时为null。
- `title`、`authors`：实际书目事实；作者可用字符串数组或清楚字符串，未知部分明确说明。
- `identifiers`：对象，按实际可核内容填写doi、arxiv_id、pmid等，不要求所有平台标识同时存在。doi、arxiv_id使用字符串或null；pmid可以是字符串或正整数，两者按同一标识核验，JSON布尔值不充当整数；未知使用null。arXiv版本另写`report_version`，不要把base ID与版本混淆。
- `discovery`：包含`site`、`record_url`和`context`（实际query/导航关系简述）。`record_url`是发现平台的真实报告记录地址，不是任意全文站点地址。
- `report_version`：所读报告/版本的明确描述；未确认则说明unknown。
- `report_date`：对象，包含`value`、`precision`、`basis`、`status`。`value`为真实精度的年/月/日字符串或null，`precision`为year/month/day/unknown，`basis`说明arxiv_v1_submitted、first_online或issue_only等来源口径，`status`为documented/unknown；未知日期使用value=null、precision=unknown并写`reason`；后备日期在已有说明中解释原因。若来源给出带时区的具体时间点，还应在该对象中保留`timestamp`，按Asia/Shanghai换算得到用于判窗的日历值。
- `version_date`：按平台口径记录明确修订版本的时间；arXiv记录所读vN的官方Submitted时间，不把它改称announcement或实际公开可见时间。未知或无单独版本日期时为null并说明。它不能替代`report_date`刷新资格。

arXiv的`report_date`取官方v1 Submitted，属于本题采用的平台提交口径。实际announcement/首次公开可见若另有证据，可在已有说明中保留并解释差异，不另建一份重复日期字段清单，也不以索引或修订刷新判窗。期刊仍取first_online或明示的issue_only后备口径。

书目、日期与版本关系的已知主张应有来源引文；引用通过下面`citations.supports_fields`指向相应字段。不要再复制`date_citation_ids`之类的并行清单。

### works：去重工作及六类内容

每项包含：

- `work_id`：唯一、非空、稳定字符串。
- `selected_record_id`：include工作所用的报告记录，必须归属本工作；exclude/pending没有选定报告时可为null。归属关系只需由`records[].work_id`表示，不要求镜像的`record_ids`列表。
- `decision`：include、exclude或pending；`decision_reason`写资格或具体问题，不能只写“相关/不相关”。
- `research_task`、`input_data`、`method`、`evaluation`、`results`、`limitations`：include工作的六个内容对象，分别对应研究任务、输入、机制、评估条件、结果、局限。每个对象至少有`status`和`text`；`status`为documented、unknown或inference，unknown要给`reason`，inference要交代理据。已知主张的引文用下文`supports_fields`关联，不要求六处再各复制一遍CID数组。

`results`若陈述实验数字，还应有`numbers`数组；每项包含`metric`、`value`、`unit`、`direction`、`condition`。`value`可为数值或保留范围/误差项的字符串，`condition`可为清楚的文本或对象；不要求补造无量纲指标的物理单位。方向可写higher_better、lower_better、not_applicable或unknown；条件按`inclusion_rules.md`披露，未知部分明确标明。没有可核数字时可用空数组并说明定性/未知状态，不强制最低数字数量。

exclude/pending工作不强制填写六类全文主张，但应保留足以理解身份、判断及未决问题的事实和引文。不能用空泛pending逃避已能确认的排除，也不能因未读到正文而编造方法/结果。

### sources：兼容独立来源采集器的实际来源账本

根`sources`为数组，本题最多60条；不默默截断实际引用来源，也不靠重复同一资源凑数。检索过程可在searches或DOCX中如实概括，但实际引用仍须完整列入账本。每个来源包含以下字段；URL对应一份实际访问或引用的公开资源：

- `source_id`：全账本唯一、非空字符串，不限定格式。
- `url`：实际请求的公开HTTP/HTTPS URL，保留必要query、版本及fragment，不用无关入口页代替正文。
- `title`：该资源实际标题或可识别描述，不伪装为另一个报告。
- `access_status`：read_full、read_excerpt、search_only或unavailable。read_full表示完整原件可读且已实际阅读相关正文；read_excerpt只看到摘录/摘要或部分内容；search_only只作为检索线索；unavailable说明不可达。全文纳入不能只靠read_excerpt/search_only/unavailable。
- `accessed_at`：实际访问的可观察ISO8601时间并带时区；未知为null并写`unknown_reason`，不能照搬论文发表日。
- `citations`：对象数组，没有实际引文时为空数组。每个对象包含全账本唯一`citation_id`、原文短片段`quote`、可定位`locator`和`supports_fields`。

`locator`用对象表达可提取定位：HTML提供section及段落/锚点等识别信息；PDF用物理页码（从1开始）及段落/文本表行列等；元数据用字段名及所在节点/记录。无需读图像或从图形估数。`quote`须在该单一来源的实际正文/元数据中可核，不能一条引文拼接不同来源；重用同一真实片段可在一条引文的`supports_fields`中说明多个支持对象。

`supports_fields`是JSON Pointer字符串数组，指向本JSON中的具体字段，例如`/works/0/research_task`、`/works/0/results`、`/records/0/report_date`或`/works/0/decision_reason`。这些仅是字段路径示例，不是论文或答案ID。一个片段确实支持多个字段时可复用；不要求每个字段有不同引文，也不以引文条数越多越好。不要再维护额外的全部CID列表、重复CID计数或逐类镜像数组。

采集器使用`sources[].source_id/url/access_status/citations`，引文使用`citation_id/quote/locator`；read_full、read_excerpt或含任何实际引用的来源会进入独立获取。没有引用的search_only/unavailable仍保留检索或失败事实，但不冒充已经取得正文。不要给根`sources`改名、把它嵌进各工作，或用一个不存在的本地文件路径替换独立URL。

### flow：守恒计数

包含`records`、`unresolved_records`、`duplicate_version_records`、`works`、`included`、`excluded`、`pending`七个非负整数，依次对应`inclusion_rules.md`中的R、U、D、W、I、E、P。由实际数组和归属/decision关系计算，满足两条守恒式及6/4最低要求；与DOCX叙述及XLSX台账一致。未知检索总命中数不填一个猜测数字，也不混入这七项。

## 来源与阅读边界

每个include工作至少关联一个实际read_full的正文来源，其身份对应`selected_record_id`。同一正文中的多个引文可支持六类内容；不能仅引数据库摘要或只给URL而没有方法/结果定位。PDF与HTML若属于同一报告版本，不产生额外工作或报告计数。

发现平台的记录、全文载体和引用片段可以是不同资源：如书目页面不可读但有真实搜索记录，可如实保留该发现路径，并以实际可读的公开等价全文支撑书目和正文事实。不要把不可观察的点击、读取或时间编造成已执行，也不要把评分侧随后取得全文当作你当时已读的行为证明。
