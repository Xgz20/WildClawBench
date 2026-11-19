# 服务记录字段对齐规则

数据均为合成服务登记。目标是按键提取实际发生金额、实际工时、实际计费记录数，并保留不能唯一匹配的全部来源。

## 业务键与期间

1. 目标项目编号非空时，唯一允许的连接条件是规范化项目编号相等且服务月份相等。即使没有找到，也不改用合同号或名称。
2. 只有目标项目编号为空时，才使用规范化合同编号与服务月份相等。目标两种编号都空则no_key，不靠项目名称猜测。
3. 编号作为文本，只去除首尾空白并把ASCII字母转大写。前导零保留，0001和1不同。不删除内部字符，不补号，不按相似度匹配。
4. 月份接受YYYY-MM、YYYY/MM或YYYY年M月，均规范为YYYY-MM；年份和月份必须一致，不跨月取最近记录。名称仅供展示和人工回查。

## 字段与单位

| 来源表 | 标识字段 | 需要的实际字段 | 同名但不得提取的字段 |
| --- | --- | --- | --- |
| 东区填报 | 源记录编号、项目编号、合同编号、服务月份 | “发生额（元、小时、次）”组下的金额、工时、次数 | “预算（元、小时）”组的金额、工时 |
| 南区导出 | source_id、项目代码、合同号、month | “实际（万元、分钟、次）”组下的金额、时长、记录数 | “预算（万元、分钟）”组的金额、时长 |
| 合作方回执 | source_id、project_no、contract_no、report_month | actual_cny、actual_minutes、actual_count | budget_cny |
| 补录数据 | 源记录编号、项目编号、合同编号、月份 | 发生金额（千元）、工时（分钟）、计费记录数 | 预算金额（千元）、预算工时（分钟） |

输出金额统一为CNY元，工时统一为小时，记录数为次。万元乘10000、千元乘1000，分钟除60。保留真实零、负调整与缺失的区别，不把空值补为0，不从预算字段补实际字段。金额允许0.01元、工时允许0.000001小时的数值误差，记录数精确。

## 对齐与未匹配

每个target_id只出现一行，保留原五个目标字段和120个目标ID。可以改变结果行顺序，不改目标原值。

- 恰好一个源行：status=matched，match_count=1，提取三项规范化实际值，空值仍空。
- 多个源行：status=one_to_many，match_count为实际条数。主表三项实际值保持空白，不选第一条、不求和、不按值去重。每个源行分别进入join_audit.csv，即使两条业务值完全相同也保留两个source_id。
- 有可用键但无来源：status=no_match，match_count=0，实际值空白。
- 目标两键都空：status=no_key，match_count=0，实际值空白。

aligned.xlsx包含主结果和未匹配视图，后者分别列出no_match/no_key目标行及未被任何目标使用的每个源行，标明side为target或source、稳定ID及原因。主结果沿用模板字段名；附加status、match_count、amount_cny、hours、count，或使用明确等价中文表头。模板结构供填写，不限定输出工作表名或物理行位置。

join_audit.csv使用UTF-8，列为target_id,target_sheet,target_row,source_id,source_sheet,source_row,match_basis,status,amount_cny,hours,count。每条连接一行，match_basis为project_month或contract_month，status=matched；target_row指实际结果工作簿的物理行号。no_match/no_key各一行，源定位及数值空白；未使用源各一行，target定位空白、status=unused_source、match_basis空白，带实际源定位及规范化值。source_row是sources.xlsx真实数据行号。不用只含文件名的自述代替定位，不静默丢弃未匹配记录。

三份输入只读，所有交付写入results。离线完成，无须写脚本交付，也无需原生公式；公式或静态值均可，只要保存并打开后与规定语义一致。文件格式和普通表头读取不要求视觉理解。
