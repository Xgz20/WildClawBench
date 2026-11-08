# Office012完整取证资源修复

WorkBuddy同一冻结执行的独立评分attempt在`write_evidence`报`EvaluationError: Evidence would be truncated; evaluation invalid`。Worker已退出，runtime未漂移，尚无规则组件、语义裁判或成绩；原attempt按标准入口保留未评分。

Score0.10.84仅对contract `b4404853...`、规则源码 `64ac633a...` 新增资源Profile。完整JSON存储上限改为单文件1MiB、合计16MiB UTF8字节；原报告30000字符门禁、全部字段、文件名、分页、序列化字节、路径保护及超限拒绝保留。没有截断、合并或删除诊断对象，原数值算法和70/30权重不变。

回归验证旧容量内字节完全一致，较大候选与来源诊断内容完整可还原，新上限及路径安全检查仍拒绝违规输入。旧Profile不追加；修复通过后从相同正式执行建立新独立评分，按明确修复范围选择，与旧分数高低无关。
