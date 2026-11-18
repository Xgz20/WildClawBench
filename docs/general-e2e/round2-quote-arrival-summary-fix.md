# round2 报价总交期与明确方式汇总解析修复

范围仅 `general-custom70-v6` 原 digest 下的 Office024，原契约
`35838d318be427d0d292b7ae866761c4a66f0ada24c977e69ea4e15d9607fb13`，
原规则源码 `9db04e9b4d6dd9abbfbe990454b84022847355ca37093c52109770674ba4a5ee`。
新发行 Score 0.10.118、Orchestrate 0.11.93；不覆盖旧冻结发行。

独立裁判在 `score-v6-registration-001-002` 完成态留下
`scoring-infrastructure-review.json`，没有发布 score.json 或导入语义草稿。
原规则把可见表头 `Estimated arrival time` 下的三个备货加运输总交期提取为 null。
候选另有以原 EXW 与明确 `recommended: sea` 运费为引用的汇总原公式；不能因布局
未识别而把此实际交付也视为缺失。

新增独立 `quote_arrival_summary_profile`，在既有 v3 有效源码
`530705542b2aca0a8c638f2ad642e4bc996c4feaae9a63b5ea832867eb0567e0`
之后接入。旧 Manifest 没有新 marker 时有效源码逐字不变。

- 仅将明确的到货时间表头映射为原 elapsed 字段，仍用原 duration/assessment 函数。
- 可见汇总须有明确总价标签，原公式为两个单元格相加，其中一个是原 EXW 引用，
  另一个由相邻标签明确指定推荐运输方式。只读取原安全求值器的结果。
- 不以 GT、数值相等或最有利分数选择方式，不为其它方式补算总价，不覆盖已存在的
  逐方案总价；冲突汇总拒绝静默选择。隐藏内容仍由原可见性规则排除。
- 原数值比较、重大事件封顶、分母、Rubric 与60/40权重不变。真实缺失与其它缺陷保持。

Orchestrate 的新独立失败类型只接受原生已完成、没有正式分数的匹配裁判；复核原
Worker/source/manifest、候选原字节、实际可见表头、旧取证漏提取、未导入草稿和完整
原生 Prompt/模型/High/终态。锁定全部旧证据后保留为未评分，再从同一执行新建评分。
控制会话不判分，不重跑 Harness，不导入旧语义草稿，也不修改候选。

验证包括六组29项相关回归、旧 v3 回放、完整有效源码入口、原数值函数 AST 不变、
缺失方式不补算、可见性/公式关系/冲突关闭，以及真实冻结作答的只读解析和失败证明
校验。真实作答复核只调用提取器，没有调用 grade；文件 SHA 前后一致。
