# 原生文件文本证据

score-general-e2e 0.11.0与grading-core 0.3.0为DOCX、XLSX、文本PDF生成`wildclawbench.native-artifact-text/v1`投影，供独立Codex裁判查询和API Judge读取。原始文件、冻结evidence ID和原文件SHA保持不变；投影记录提取文本SHA、记录总数、位置、提取器/库版本以及截断和能力限制。它不是新的评分Rubric，也不是渲染或原生应用验收。

score-general-e2e 0.13.0与grading-core 0.5.0增加PPTX；外层投影仍为v1，PPTX提取引擎明确记录为`wildclawbench.pptx-text/v1`。DOCX、XLSX、PDF的既有记录格式和引擎标识不变，历史attempt继续使用其冻结代码与原件。

- DOCX：读取正文段落、内容控件、表格、页眉页脚及注释等文本，定位为段落号或表/行/列。插入文本保留，`delText`删除文本不作为现行正文。图像、嵌入对象和版式不解释。
- XLSX：记录工作表名、隐藏状态、单元格地址、类型、值、公式及其存储缓存是否存在。空字符串缓存与缺缓存不同，数值0保留为0。日期按工作簿纪元和数值格式注解，记录原始serial，不把货币/百分数或累计时长格式当日期。图表、宏和外链不执行，公式不重算。
- PPTX：按`presentation.xml`的关系顺序遍历实际幻灯片，不按slide文件编号排序或读取孤立部件。定位保留slide/shape/paragraph、分组层次、表格行列、图表系列/数据角色/缓存点和备注；隐藏页及对象保留标记，备注与幻灯片正文分开。图表缓存保留原始点索引、缺失/空值和公式引用，不把缺点补成0；嵌入XLSX另保留包内路径、SHA及单元格缓存，图表值与表格值分别记录。外部package/OLE数据关系只标记未读取，不访问网络；非XLSX嵌入格式只标记不支持。原生chartEx、SmartArt、图像、母版/布局继承文字、动画可见性及字体继承不解释。显式字号用原始百分之一pt记录，不能据此证明字号达标、文字未溢出或图表在目标应用可编辑。
- PDF：使用pypdf逐页提取文本，定位为page编号。无可提取文本、加密或解析受限时明确不可用；不能据此推断扫描页没有内容，更不能由文件名判视觉结论。

## Word结构证据

score-general-e2e 0.17.0与grading-core 0.9.0将DOCX引擎标记为`stdlib-word-ooxml / wildclawbench.docx-text/v1`；外层投影schema仍为v1。原有`paragraph:N`、`table:N/row:N/cell:N`及注释部件段落定位保留；新增记录会改变记录序号和投影SHA。XLSX、PPTX、PDF提取行为不变，历史attempt继续使用冻结代码，不回写旧投影。

- `table:N/grid`记录声明的列宽原值、列数、物理行数和重复表头行。复杂表格的`table_structure`提供从1开始的逻辑列、`gridSpan`、行前后省略网格、`vMerge`及旧式`hMerge`声明；物理cell编号不等于逻辑列。纵向续格只连接前一行相同起始列和跨度的合并区，孤立/跨度不符不猜测；无效跨度保留原值和未知区间。`hMerge`保留同行anchor，不声称已转换为完整合并矩阵。普通表不逐格增加这组元数据。
- 正文段落/单元格的`note_references`记录footnote/endnote类型、规范化包内ID、实际关系目标、内容状态和目标locator。`relationship_missing`、`external_not_followed`、`missing_part`、`note_missing`与`available`分开；外部不跟随。注释摘要如`word/footnotes.xml/footnote:1`绑定部件SHA与实际`paragraph_locators`，不能凭同文注释证明挂接正确。`part_linked_from_document`只说明部件存在关系，不说明每条注释都被正文引用；ID不是渲染后的显示编号。
- 重复ID、冲突的注释关系、错误部件根和越界目标明确拒绝。引用遍历排除删除/移出修订、drawing/pict及嵌套表，保留插入修订；文字提取仍遵循原`w:t`/`delText`规则，未实现所有修订、隐藏与可见性语义。嵌套表文字可能汇入父格，`contains_nested_table`显式标记，但不展开嵌套拓扑。

结构记录的`text`可为空，仍占投影记录和输入预算；应分页读取并核查截断。只有结构或图片而无可提取文字仍返回`NATIVE_TEXT_UNAVAILABLE`。这些字段是OOXML声明证据，不是版面几何、固定渲染、原生可编辑性或独立语义验收；跨页表是否裁切、脚注显示位置及阅读顺序仍须另有证据。

在已冻结单题attempt中，沿用原`query-evidence --mode catalog`找到evidence ID，再用`--mode file --evidence-id ID --offset N --limit M`查询。原生文件的offset/limit按投影记录分页，`line`为记录序号，query-log中的coverage.kind为`native-text-records`，不冒充二进制文件的文本行号。长记录的字符截断仍明确标记，未读或截断内容不能作不存在证明。

API输入的native_text_records包含提取范围与限制。输入预算和逐文件预算必须覆盖所需内容；packet显示truncated或omitted时，不能仅凭已有片段推断全文。证据不足继续返回unresolved。图表缓存的数值观察不能证明图表实际呈现，图像含义与版式可用性需要单独的视觉证据链。

PDF前置条件是**冻结的评分CLI解释器**能够导入pypdf（仓库requirements声明`pypdf>=5,<7`，正式运行仍须锁定实际环境版本）。不要求被测Harness、候选项目或规则Worker为此安装库。缺库会产生`NATIVE_TEXT_DEPENDENCY_MISSING`；无文本或不支持内容不自动补分/补零。Office ZIP有成员数、解压总量、XML大小和路径边界检查，PPTX及实际读取的独立嵌入XLSX共用解压总量上限。重复图表点/对象ID、含糊或越界关系明确拒绝；提取不写入或解压候选文件。图片页无可提取文字或图表缓存时返回`NATIVE_TEXT_UNAVAILABLE`，不假装已经理解图像。

legacy CLI的Workspace证据策略更新为v3，并把同一独立模块复制到容器内；GT仍排除在候选Workspace证据发现之外。该兼容入口的结构化模块复制/独立Python测试不等于Docker实跑，平台和完整评测仍须独立验收。

PPTX支持后的新legacy调用使用`wildclaw-workspace-evidence-v4`，继续分发单文件helper、优先读取显式交付并排除GT。旧v3评分记录不重写。结构记录和库间交叉核对不替代固定渲染、目标应用实测或独立语义评分。

DOCX结构支持后的新legacy调用使用`wildclaw-workspace-evidence-v5`，同样分发单文件helper并排除GT。旧v3/v4证据及其评分记录保持原版本；独立helper与分发包验证不能替代Docker实跑。
