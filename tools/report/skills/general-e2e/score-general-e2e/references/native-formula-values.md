# 原生只读公式求值

仅新Codex评分attempt可按v6 Data007的原contract/source冻结`promotion-readonly-native-formula-values/v1`。其受管Python必须已配置原生Writer/JDK/UNO，并通过独立bulk Calc验证；不修改已使用的native-calc v1资产。

用受管解释器执行本Skill的`native_calc_values.py self-test --writer-configuration ABS --output-root NEW`。它实际打开134格合成工作簿，区分数值、0、空字符串、中文与错误，并核验不保存、宏/外链禁用、完整来源SHA和进程收尾。只有PASS后，在该受管runtime根中新增`general-e2e-native-calc-values.json`，schema为`general-e2e-native-calc-values-runtime/v1`，包含profile、validation绝对路径及SHA、同一assets和writer_configuration；不可覆盖既有标记。正式prepare冻结解释器、invoker、bulk helper、Java源码、配置及验证摘要。新attempt重新运行原规则；旧失败不原地重跑。

原规则缺缓存时，一次只读求值完整公式范围，再只填data_only内存视图中的原缺值。原工作簿/公式不保存、已有缓存不替换；真实错误原样交原规则，不能改成0或修正公式。环境错误继续失败关闭。`评分证据/原生公式求值/内存视图说明.json`包含来源、范围、全部错误及评分端角色，`native-raw.zip`保留完整值/页/请求/日志，可按工作表与坐标核查，不把ZIP当UTF-8正文。

独立裁判按原Rubric判断，不将评分端求值算作候选自行验证，不因原文件缺缓存再次宣称没有数值。数字单位、精度、错误及字段口径仍按原规则。语义涉及具体数字时可从完整归档回查；原生观察不替代原执行工具轨迹、候选结论或主动验收。
