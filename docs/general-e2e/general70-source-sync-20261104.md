# 通用70题源、CLI与两端历史结果复核（2026-11-04）

本次将WorkBuddy调试中验证过、尚未回写题源的8项实现修复发布为`general-custom70-v3`。
真实修改位于`tasks/general_e2e`内的Python评分代码，CLI与E2E打包消费同一源码。
既有WorkBuddy v2、AStudio历史70题和旧60题的冻结输入、评分、报告不覆盖。

## 源级修改

| 用例 | 实现修复 |
| --- | --- |
| Office010 | 明确等价表头、完整原行/表头、明确不发起且金额0的逻辑行；原因类别独立复核后执行原数值规则 |
| Office015 | 无对应订单入库的合并编号表头、汇总矩阵标签、显式双计数、合计行结束表域 |
| Office024 | 三项英文表头、显式目的国与一般运输端点分开读取 |
| Office026 | 工单分摊工时、日总量、非生产事件分开提取，保留全部原行 |
| Office018/019/029/030 | 完整取证总资源上限16MiB，保留原分页、单文件及格式安全限制，超限异常、不截断 |

公开Prompt、执行输入、GT、Rubric、权重和业务比较标准保持不变。
逐题前后SHA与原修复回执见`eval_general_e2e/datasets/audits/general-custom70-v3-source-repairs.json`。

CLI新增`src/utils/declared_rule_review.py`，支持Office010题内声明的原因复核协议：
原规则发现全部上下文（不发布临时分）→配置的独立API裁判逐项判断→验证范围、
布尔结果、中文证据理由及明确终止原因→重验输入SHA→原数值规则。
未知、缺少决定、非布尔值、输入变化或裁判输出不完整均保留错误/null，不补零。
原6个组合、87/13预算及严重错误封顶不变。

E2E使用Score0.10.68、Orchestrate0.11.53，继续采用独立单题原生Codex裁判。
新Office010按精确新契约/源码登记原因复核，已写入题源的修复不重复套用旧替换。
4题声明的文件名通配符有独立v3目录，v1/v2目录不变。

## 历史影响审计

审计复用了原选中评分SHA绑定的候选和实际Worker源码，未启动Harness或新语义裁判。
Office010/015/024/026两端共8份工作簿的新旧业务字段抽取一致。

- AStudio Office010的3条不发起行仍缺可绑定的供应商组合；新增原因复核不会替候选补供应商。
- AStudio Office015没有新增矩阵修复要求的双金额表头及合计后叙述布局。
- AStudio Office024的显式目的国与已识别字段不变。
- AStudio Office026的订单/日字段不发生新增重映射。
- AStudio Office018/019/029/030原Worker已完整完成并有锁定取证快照；提高纯资源上限不改变已交接业务材料。

在最终跨端验收中，另修正了候选版对单金额混合汇总表的过度矩阵识别。
最终版只让有明确订单金额及入库金额列的表进入双金额矩阵；单金额表保留全部原声明。
使用原GT字节核对两端采购工作簿，完整汇总规则与原正式Worker一致。
早期候选v3包未用于正式评测，保留其字节及源码提交，不将它当作最终发行。
最终题源修订号固定为`557fff5b118ec3e3f604f313141dfd3618d8db69`，避免后续Git提交改变历史数据集摘要。

本次未发现最终修复要求改判AStudio原产物的证据，因此未重评这些有效成绩。
原WorkBuddy受影响12题已在上一轮修复后独立重评分，本次也不重复评分。
这是新增修复影响审计，不是全部业务真值、难度或区分度验收。

本轮原始回执位于调试轮次`.general-e2e/validation/`：
`frozen-office-parser-impact-final-20261104.json`、`procurement-complete-summary-impact-final-20261104.json`、
`astudio-resource-budget-impact-20261104.json`。
两端历史评分按各自原题源解释，不将不同版本直接当作严格同版本对照。

## WorkBuddy Info004：原生终止证据

本轮原结果`valid=true,total_score=0.38`。冻结原生API与原始JSONL的末条正文均为2028字符，
结束在“五四时期杂文分析”的“核心段落（原文）”标题后，回忆对照、学术研究解释及综合比较未交付。
正文与评分输入一致，原生历史`hasOlder=false`，没有发现评分侧漏采后半篇。

精确身份：

- conversation：`eecaca7b-fe56-42bc-9e24-c2593b13a29a`
- request：`01a19bd35faf74d4adb60922a24c4050`
- trace：`227577572c484d90991ec40913e7c27c`
- 末轮模型message：`01a19bd5b17c79a3a7858264aafe3547`
- SDK消息：`01a19bd5-b17c-79a3-a785-8265f7b34005`，与模型message属于不同身份层。

按完整身份核对原生日志，获得24轮模型结束记录。末轮发生于2026-11-02 18:37:37.912
（Asia/Shanghai）：HTTP起止均200，`finish_flag=done`，`finish_reason`为空，输入/输出用量均0，
194个chunk，接收及原始长度均122548字节，文本2028字符。
随后状态机`MODEL_RESPONSE_DONE→AGENT_ENDED`；ACP又记录`stopReason=end_turn,finishReason=tool_calls`。

已确认末轮模型终止元数据缺失，客户端仍发布完成态。现有证据不能继续区分服务端提前结束、
协议映射遗漏或流解析缺陷；ACP与末轮结束原因不一致，需要研发核查是否沿用了前轮状态。
缺少原始SSE逐chunk和服务端终止日志，不能把推测写成已确认模型缺陷，也不能仅凭空结束原因
推翻原冻结评分的原生终态准入。

建议研发按同一trace/message查服务端停止原因、输出限制及末个SSE事件；逐轮重置结束原因，
区分正常停止、长度停止、工具调用、连接关闭与错误；缺协议终止证据时明确显示未知，
并检查未完成任务和明显未写完的交付。本次没有修改WorkBuddy源码或自动重跑。

仓库新增`tools/e2e-build/audit_workbuddy_termination.py`，输入明确runtime-binding、session JSONL
及原生日志，可按完整身份生成只读诊断，不赋分。
本轮回执为`workbuddy-info004-portable-termination-audit-20261104.json`。
原生运行日志第2800、2801、2805、2823—2827行及原行/文件SHA另保存在
`workbuddy-info004-native-termination-20261104.json`。

## AStudio Info004：继续保留待核验

原`scholar_claim_binding`保持`unresolved/null`，整题总分null。待核定的仍是候选归于杨联芬
《晚清与五四文学的国民性焦虑（三）》的两个命题：借《三十八》解释爱国话语收编国民性批判的危险；
以包含鲁迅自身的内部反思说明其超越。该任务不要求必须取得整篇PDF。

本次重新访问[官方论文页](https://lxyj.cbpt.cnki.net/portal/journal/portal/client/paper/0e74b482f92af4130394be98e74de9f0)，
HTTP200，保存100767字节，SHA256为`99ce332b719251eb7b741b243f09e5781b6498faf3812fcd1927a2cf2464ca4d`。
公开页含书目、参考引注和转至CNKI全文的提示；其中《三十八》的引注属于鲁迅原文，
不能代替杨文如何解释它的论证段落。

补查[南洋学报第71卷](https://www.southseassociety.sg/publications/images/2017_V71_contents.pdf)中
颜敏《现代中国作家的南洋叙事》第178页，找到对杨文第33页“对话/现实问题”的二次引述。
它不涉及上述两个命题，不能填补原缺口。其他检索结果也未提供足够相关原文。

因此没有追加伪装成原文的证据，没有改变冻结GT，没有补零、给满分或启动无证据重评分。
仍需合法取得相关页或可精确归属的充分证据，再登记SHA绑定补证层，复用原冻结执行、
相同Judge及原权重独立重评分；无法取得时继续待核验，不删未知检查点强行合分。

## 验证与复现

- 70题静态校验PASS，0告警；CLI与E2E全部70题规则源码逐项一致。
- General E2E全套628项通过；末次新增分支另有专项回归；CLI/legacy聚焦45项通过。
- 旧60、历史116-v1、70-v2的manifest均按原摘要重建，旧七维映射不变。
- 最终Score0.10.68只读核验两端140份历史评分全部通过，原score与submission SHA不变。
- v3 digest：`2a9ebd7ee9330a6d7fd7261df44275e8980eb95275b0ada2c80b4005573132b7`。
- v3 bundle已构建验证。CLI复核流程使用隔离模拟API后端，没有运行新的真实模型样本。

```bash
python tools/e2e-build/build_general70_v3.py
python -m eval_general_e2e.datasets.bundle build --dataset general-custom70-v3
python eval/run_batch.py --dataset general-custom70-v3 --parallel 3 --model <已配置模型>
```

`--dataset general-custom70-v2`继续按归档题源和原manifest运行；旧60题默认入口不变。
不同数据集输出进入独立命名空间，禁止混用旧输出。
