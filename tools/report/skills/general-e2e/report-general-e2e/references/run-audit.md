# 运行编排审计

`report_general_e2e.py generate`及`selected_report.py`支持显式`--run-audit ABS`。
该入口消费管理员已核验的原生运行区间和控制暂停记录，补充报告披露；它不是新的执行、采集、评分或原生上下文验证入口。

管理员须先按执行/编排Skill绑定原生任务或独立裁判的完整身份和时间边界，保留原件及SHA。执行区间来自同一时钟上的原生主任务起止，不能使用配置槽位、UI发送顺序、控制器观察窗、评分Worker或文件修改时间代替。评分区间只适用原生Codex裁判；纯规则、API或从未创建的聊天不补造区间。原生时钟、身份或边界无法核实时留空，并说明缺失原因。哈希相符仅证明文件字节，不能证明管理员没有观察到的事件。

输入为UTF-8 JSON，schema_version固定`wildclawbench.general-e2e-report-run-audit/v1`，包含原`batch_id`、`dataset.id/digest`及`units`。所有报告单元必须各出现一次；每个单元的`task_bindings`须按报告冻结题序完整列出`task_id`、`execution_attempt_id`和`scoring_attempt_id`（未创建时null），包括失败、评测异常和未评分。不能只传已成功题的范围。

单元字段：

- `unit_id`：报告单元的精确ID。
- `execution`和`scoring`：各有`configured_slots`（整数1–8）、`configuration_evidence`、非空`method`及`intervals`。配置证据必须是实际冻结队列/编排或明确绑定的原始配置。每个原生区间包含`task_id`、对应阶段的`attempt_id`、有时区的`started_at/finished_at`和`evidence`。同一题不能重复；执行区间必须落在原执行记录的开始/结束内。只有部分题有区间时必须给非空`missing_reason`。
- 每组`evidence`/`configuration_evidence`是非空`[{"path": "ABS_OR_RELATIVE_TO_LEDGER", "sha256": "64HEX"}]`。文件必须非空、普通且路径祖先无符号链接；发布前再次重验。审计证据使用原生验证回执或必要的元数据摘录并引用原始日志SHA，避免将裁判思考正文带入报告。
- 可选`controller_holds`：每项包含`started_at`、`finished_at`、按两者精确计算的`duration_seconds`、受影响的完整`task_ids`、`native_processes_paused=false`及`evidence`。暂停区间须与每个所列任务的原执行窗口相交；当前只接受被测进程未暂停的控制审阅等待，不能借此修改或扣减原始流程耗时。

峰值按所列半开区间`[start,end)`重算，相接端点不算重叠。没有区间时为null；部分覆盖时只展示已知区间峰值下限。峰值超过冻结配置会拒绝，须保留不一致现场核验，不能删除区间使其通过。

JSON保存完整的规范化审计和来源指纹，MD/Excel总览及效率注释复用同一数据，审计MD列出方法、缺失原因和来源SHA。`data/run-audit.json`纳入标准report receipt及同进程封存。源证据依然保留在原执行/评分/管理员审计中，报告不复制原生裁判思考正文；迁移时须一并保存所引用的证据，不能将规范化元数据称为完整原生日志。旧报告不传该参数时沿用原路径，不修改旧分、权重、资源或冻结输入。

## 显式失败计零的第二计分口径

Report0.8.31可在对应unit内另列`failure_zero_decisions`，每项包含`task_id`、`execution_attempt_id`、`decision:{path,sha256}`、`human_policy:{path,sha256}`。该列表不替代完整有序task_bindings。决策必须绑定已选execution record的身份、Prompt、正式冻结候选和`native_start_rejection`proof；授权保留人类原文、问题身份和条件，明确未决归因不能直接计零。当前只接受AStudio原生20秒启动提交拒绝且`not-submitted-v1`已结算、无模型turn/排队输入、预热runtime停止的共享核验Profile；不会外推其他Harness、未知中断或额度失败。生成时需要可用Node（优先显式`--node ABS`）回放完整原始状态及原生同快照。

JSON保留`total_score=null/score_status=unscored`，另存`failure_policy_score=0/e2e_score=0`及授权证据；已valid题的e2e_score沿用Rubric，未决题保持null。总览分别显示Rubric均分与含策略零分的端到端均分、策略零分数及已计分覆盖；Excel和MD新增完整范围的端到端计分表。原valid数、Rubric权重、能力维度和原始计时不修改。该授权是管理员保存的人类直接指令记录，不声称密码学验证人类身份。
