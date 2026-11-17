# 查询生成器合同 v1

仅修复project/query_builder.py。公开辅助模块、公开测试、fixtures、本合同、依赖锁和工具保持原字节。所有数据是惰性原创合成数据；用Python3.11+自带sqlite3、SQLite3.35+本地内存库，无第二引擎、真实数据库、网络或依赖安装。本题不要求JOIN/聚合/第二SQL方言。

## build_query(spec) -> (sql, params)
spec是dict：table为fixtures/schema.json中精确表名，columns为非空list列名，where可缺省/None，order_by可缺省/空list或由{'column':列名,'direction':'asc'或'desc'}组成的list。columns允许重排/重复；不得借标识符输入注入表达式。table、columns、条件列、排序列须按SCHEMA允许表逐项验证；未知标识符、类型或操作符/结构均抛ValueError，不执行SQL。schema固定两表customer/order，公开SCHEMA映射可保留/重构但不能接受任意表/列。

返回非空单条只读SELECT SQL，params为list/tuple（匿名?参数）或dict（:name命名参数）；不得混用两风格，不用?NNN/@name/$name。占位符必须与参数完整对应，命名参数可多次复用同一键；不允许多余或漏绑定。列/表引用可用SQLite接受的引用方式，不固定SQL排版、别名、括号或具体表达式。所有外部非NULL叶值必须通过绑定传递，不能通过转义后拼入SQL取消参数化；可为NULL或实现用常量增加绑定。正常常量0/1用于空组/空集合可内联。相同spec生成的SQL/参数须确定，不修改spec。结果按columns给定顺序投影。

## 条件树
- 叶子：{'column':...,'op':...,'value':...}；op为eq/ne/gt/gte/lt/lte/in/not_in/is_null/is_not_null。is_null/is_not_null不需要value；其它需要。分组只有{'all':[节点,...]}或{'any':[节点,...]}；同一节点不能混入其它键。必须保留嵌套布尔分组，空all为真，空any为假，where=None为真。
- number列接受非bool的int/float或None，text列接受str或None。in/not_in的value必须list，每项符合该列类型；空list有效。顺序比较的value不能None。eq/ne允许None，按可空值的相等/不等语义：None只等于None，None不等于任何非NULL标量。
- in/not_in采用集合成员语义，None作为一个值：in[]恒假，not_in[]恒真（包括NULL行）；in含None时须包含NULL行，not_in含None时须排除NULL行；not_in不含None时须保留NULL行。重复集合值不改变结果，可去重，也可重复绑定。
- gt/gte/lt/lte遇到行值None均不匹配。ISO日期字段是YYYY-MM-DD文本，按该统一格式的字典序比较，不猜时区、不改写日期。字符串比较区分大小写；引号、Unicode、注释样文本均为普通数据。
- order_by按列顺序排序，asc时NULL在前，desc时NULL在后；不指定时按结果多重集合核验（重复行不得擅自去重）。不隐式增加额外WHERE、DISTINCT、LIMIT或截断结果。

## 交付与实际验证
只改/tmp_workspace/project/query_builder.py，不增添其它源码。可以在results写额外说明；Python自动__pycache__/*.pyc忽略。运行公开测试：python -B -m unittest project.test_public -v。它只覆盖正常基础行为，原工程也可能全绿，不等于边界正确。

修复后执行python -B tools/run_regression.py，生成results/query_audit.json和results/tests.txt（后者也是JSON格式，保留.txt扩展名）。audit逐项保留fixtures/queries.json全部固定ID的实际SQL、params、SQLite结果/错误与源码/输入SHA；tests记录真实命令、returncode、完整stdout/stderr、逐测试状态、最终源码及audit SHA。更改最终源码后须重跑。参数与SQL应来自当前源码，不能写死参考结果、删掉失败用例改变分母或自述已验证。评分侧会实际重新生成、执行与重绑定SQL，不依赖参考SQL字符串。

所有保护输入保持不变，不能放宽公开测试、改数据或依赖锁来获得通过。离线完成，不读取GT。结论区分事实、推断和未知，不编造跨引擎实测或缺失信息。
