# round3 采购汇总与缺缓存公式的评分读取视图

Score0.10.125、Orchestrate0.11.99 仅修复评分端读取/恢复，不重跑 Harness，不改原候选、公式、GT、Rubric、权重或既有分数。旧失败 attempt 和旧冻结发行完整保留，同一原执行另建独立评分，最终按修复范围显式合入完整70题。

Office015 的原 Worker 已因未识别的数值汇总抛 EvaluationError，未生成分数或 Judge。新 `procurement-explicit-category-subtotals-currency/v1` 精确绑定 v6 原契约/源码及已核验前驱，读取订单↔入库明确匹配标签、带“元”的数字文字，以及连续四类表格中明确的笔数列字面小计和金额差异净额。数值、备注中的笔数、隐藏状态及物理位置均保留；分类笔数和不当作独立订单总数。未知币种、模糊/缺行/隐藏区段不放行。原所有比较、容差、上下游归因、分母与80/20均沿用。前驱按已验证修复链和SHA绑定，不把含绝对native helper路径的旧完整源码SHA硬编码为新发行。

Data007 原规则明文要求对缺缓存公式安全求值，原 GradingIndeterminate 不能计能力0。新精确退役分支验证 v6 contract/source、原请求源码、失败前后身份/运行时、无Judge/分数、Worker清理、原候选与runtime字节，以及原报错坐标确为缺缓存公式；其后沿既有正式framework-failure协议留证。旧Worker不重跑。

新原生 `readonly-native-calc-bulk-values/v2` 使用独立Java类，保持已使用的v1 helper/Java字节和验证标记不变。坐标通过UTF-8文件传递，一次原生只读打开/重算后以 `XCellRangeData.getDataArray` 批量取数，使用 `queryFormulaCells(ERROR)` 另取真实错误；不会把数字0、文本空串和错误合并。宏NEVER_EXECUTE、外链NO_UPDATE，外部内容严格检查，独立Office Profile、精确进程身份收尾，原件和不可变副本SHA必须不变。新v2输入上限128MiB、单成员96MiB、最多100,000请求格/2,000,000包围格；原v1的64MiB/64格边界保留。首次真实包因85,019,321展开字节超旧边界的预检失败保留，无进程创建；v2新上限另做新自测，不覆盖旧验证目录。

134格合成自测已实测数值、0、空字符串、中文及公式错误。原冻结Data007的85,072格只读开发观察通过：83,671数值、921文本、480错误，源文件不变、未保存、无残留。错误代码均522，原公式示例分层比较L2为 `=IF(J2=0,"",L2/J2)`；原自引用公式不修正，正式分由原算法与独立裁判判断。此观察不代替正式新attempt的规则运行，也不作为候选主动验收。

新Profile只把完整原生结果填入openpyxl的data_only内存对象中原来缺缓存的位置，已有缓存不替换，原工作簿不保存；数值、文本及真实错误都交原比较函数。完整原始JSONL、请求、原生日志、观察索引与分页装入native-raw.zip；内存视图说明列出源SHA、全部错误定位及评分端角色。新裁判Prompt要求按工作表/坐标回查完整归档，C1/C7只认原执行轨迹。运行时/环境故障仍是评测异常。

相关回归87项PASS，含新读取视图、旧失败严格匹配、旧Profile重放、编排/Prompt/复合选择及独立发行；13项采购初检和原生真实/合成观察另存。所有原始失败和测试日志保留。参考原生接口：[XCellRangeData](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1sheet_1_1XCellRangeData.html)、[XCellRangesQuery](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1sheet_1_1XCellRangesQuery.html)、[FormulaResult](https://api.libreoffice.org/docs/idl/ref/namespacecom_1_1sun_1_1star_1_1sheet_1_1FormulaResult.html)。
