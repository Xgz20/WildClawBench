# 归档与版本规范 H036

这是原创虚构材料。incoming 中有48个惰性小文件；后缀可能伪装，.pdf/.docx/.exe等名称不表示该格式或可执行内容，不运行任何文件。只读incoming、本文及protected.json；只在results新建交付，原始文件不移动、删除或改字节。离线完成。

## 内容识别与业务分类
先按内容完整解析，再读取元数据，不能按扩展名或文件名猜类别。JSON为object；CSV为带如下表头的单记录；XML为record根且子元素同名；Markdown以“# H036 business document”开头，逐行key: value加正文。所需元数据是business_area、document_id、version、state、issued_at，body为惰性虚构正文。JSON/CSV支持UTF-8 BOM。解析不了或无上述内容格式标记，detected_format=unknown，reason_code=format_unknown；能识别格式但缺必填字段为metadata_missing；字段值无效为metadata_invalid。

合法business_area：finance、people、sales、operations、compliance、research、procurement。document_id非空；按Unicode NFC归一，区分大小写，不按近似拼写或文件名合并。version为可选v前缀加数字点分版本，2或3段，不按字符串排序，比较时尾部补0。state为approved、draft或withdrawn；issued_at为有时区的ISO8601有效时间，按同一UTC时刻比较。未知对象统一business_area/document_id/version/state/issued_at=unknown，selection=unknown，原字节仍归档，原因如实写出。

## 版本选择
业务键=(NFC business_area,NFC document_id)。每个键先排除withdrawn作为当前版本候选，再依次比较：approved优先于draft；数字版本大者优先；issued_at UTC时刻晚者优先。不同文件名、来源目录和mtime均无优先级。同一原字节SHA256仅为重复来源，不是不同版本。最高优先级只剩一个不同SHA时，该SHA的所有来源selection=current；同键其余SHA= superseded。最高优先级有多个不同SHA并列时，所有并列SHA来源selection=conflict，不任意挑一个为current；其它SHA仍superseded。withdrawn始终superseded。所有状态的不同内容均需保留，不能只保存current。

## 副本和目录
SHA256按输入原始字节计算，不能重写换行、重编码或重新序列化。全局每个不同SHA只保留一个归档普通文件，不使用硬链接/symlink或改变输入。所有相同SHA的来源映射到同一archive_path；任选一来源为代表，其duplicate_of留空，其余duplicate_of填代表source_id。同名异内容必须分开保存，不能覆盖。不同业务/selection的归档文件分目录；每个承载文件的直接父目录仅容纳同一(business_area,selection)，目录名和层级自由，不能仅靠固定目录字面判分。

## 清单与异常
manifest.csv为UTF-8或UTF-8 BOM、逗号分隔RFC4180表，48行原始来源一行不少。列名可用公开英文名或直译中文，顺序任意。字段：source_id、source_path、archive_path、sha256、business_area、document_id、version、state、issued_at、selection、duplicate_of、detected_format、reason_code。source_id取protected.json的输入编号；source_path为含incoming/的路径；archive_path为相对results的archive/...或等价/tmp_workspace/results/archive/...。已知有效元数据reason_code=ok；其它按上面三种原因。原字段版本和时间可保留有效等价原写法。

detected_format取json/csv/xml/markdown/unknown。后缀规范为.json/.csv/.xml/.md（不分大小写）；已知内容格式的后缀缺失或与此不符，记extension_mismatch，包括.text/.txt/.pdf等，不据此改业务分类。

exceptions.md自然语言说明已知冲突和未知项。为便于复核，另放一份Markdown表（kind | source_ids | detail）或fenced JSON数组（每项含kind/source_ids/detail）。source_ids可为数组或用逗号/空格/顿号分隔的编号集合，允许同类异常合并记录、任意顺序和措辞，不要求逐字模板。必须覆盖：extension_mismatch所有相关来源；name_collision即NFC同basename却不同SHA的所有相关来源；version_conflict所有并列最高来源；unknown_item所有selection=unknown来源。detail写真实可用说明而非空字段；可附其它有根据的说明。不把未知当确定类别，不把副本称成内容已删。
