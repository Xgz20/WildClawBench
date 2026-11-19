# 学生选课导入契约 2.1

这是合成的离线缺陷修复仓库。只修改project/importer.py；Python 3.11+，仅标准库，无需安装依赖。实现形式不限，成功输入的既有结构保持兼容。错误不能被吞掉或转换成空成功。

## CLI与返回结构

调用：`python3 project/importer.py --input FILE --format csv --course-separator '|'`。
`--format`默认csv，仅接受csv或tsv，文件列分隔分别为逗号或制表符；课程分隔默认`|`，也接受`;`。二者不是同一层分隔符。以下均提供必需参数；缺失参数、未知CLI选项的argparse用法提示不在本题评分范围。

成功退出0，stdout只有一个JSON对象：`{"ok":true,"records":[...],"stats":{"students":N,"enrollments":M}}`。每个record恰含id、name、courses、raw_courses。records保持原数据顺序，courses为解析后的非空字符串数组，N/M必须为非负JSON整数，不接受布尔值或浮点数。M为课程项总数（不同学生相同课程分别计数）。字典key顺序不影响兼容性。

失败退出2，stdout只有一个JSON对象：`{"ok":false,"error":{"code":"E_...","row":null,"field":null,"message":"[E_...] ..."}}`。message非空且包含对应code，不要求特定自然语言，不能包含整条学生原始数据。row为下面规定的逻辑CSV记录序号，field只能取id/name/courses或null。不得输出部分成功records。stderr可记录不含学生原始数据的诊断，不得将正常JSON写入stderr。

## 解析阶段与错误优先级

按以下阶段执行；先阶段错误优先于后阶段。CSV语法必须在业务检查前整体解析完成。业务阶段按逻辑记录顺序找第一条错误，不按错误码字母顺序排序。

1. CLI配置：format或course-separator不合法，E_CONFIG，row/field均null；优先于读文件。
2. 无法读取输入，E_IO，row/field均null。
3. 严格UTF-8解码；只移除文件起始BOM。解码失败E_ENCODING，row/field均null。不得替换坏字节。
4. 按Python标准库csv.reader(strict=True)的引号规则解析整份文件，支持引号内列分隔符、双引号转义与换行，保留原字段内CR/LF；解析失败E_CSV_SYNTAX，row/field均null。支持LF、CRLF。
5. 第一条逻辑记录是表头，必须恰好含id/name/courses各一次，可换列顺序，不修剪/改写表头。空文件、缺列、重列、额外列均E_HEADER，row=1、field=null。表头前不允许空记录。
6. 逐记录业务检查：完全空记录（csv.reader返回[]）忽略，但仍占一个逻辑序号；不是把只有空字段的记录当空行。引号内物理换行不增加逻辑序号。每条依次检查：列数必须3→E_ROW_WIDTH(field=null)；id.strip()为空→E_ID_EMPTY；id不匹配ASCII `[A-Z][0-9]{3}`→E_ID_FORMAT；id已成功导入→E_ID_DUP；name.strip()为空→E_NAME_EMPTY；最后检查课程。id类field=id，name类field=name。除了id.strip()，name和raw_courses必须逐字保留，不进行Unicode或换行规范化。

## 课程字段（在CSV列解码之后解析）

扫描整个raw_courses字段，反斜线只允许转义`\|`、`\;`、`\\`，均形成一个字面字符，转义后的分隔符不再分词。按配置的未转义ASCII课程分隔符分词，对每个结果使用Python str.strip()，保留剩余原文，不改写大小写/Unicode。以下错误同时存在时，按所列顺序选择：

| 错误 | 触发 |
| --- | --- |
| E_DELIMITER_INVALID | 出现全角`｜`或`；`（不能作为课程字符，也不能靠反斜线逃逸） |
| E_DELIMITER_MIXED | 出现另一种未转义ASCII课程分隔符，例如配置`|`而字段为`数学;物理` |
| E_ESCAPE | 未知反斜线转义或末尾孤立反斜线 |
| E_COURSE_EMPTY | 任一分词结果strip后为空，包括整个字段空、首/尾/连续分隔符 |
| E_COURSE_DUP | 对每个strip后的课程做NFC规范化再casefold，存在相同键；输出本身不按此改写 |

课程错误的field=courses，row为该逻辑记录序号。全角字符即使紧跟非法反斜线，也仍触发优先级更高的E_DELIMITER_INVALID。修复必须兼顾CSV/TSV层、课程层和先后错误分流，不能只替换某个输入样本。

## 测试和交付记录

公开测试命令：在project目录执行`python3 -m unittest -v test_public`。记录最终源码SHA-256、实际命令、returncode、tests_run、passed和stdout/stderr相对路径及SHA，写入results/test_report.json。字段名为source_sha256、command（字符串数组）、returncode、tests_run、passed、stdout_path、stdout_sha256、stderr_path、stderr_sha256；日志路径须位于results/。报告必须绑定最终源码，不用旧源码的运行记录代替。

results/compatibility.md使用`## 修复`、`## 兼容`、`## 验证范围`三个标题，说明修复、错误优先级、保留原文与CSV/TSV兼容行为，以及实际验证范围；不能宣称已经看到私有测试。允许生成本地__pycache__，其它新文件只写results。公开测试、fixtures、contract.md及其它原始输入均不得修改。禁止联网。评分会独立运行最终源码，不以自述通过替代结果。
