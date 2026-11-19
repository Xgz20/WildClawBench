# round3 报价总交期表头漏读

Office024 原独立裁判已按冻结Score0.10.122实际完成，原Worker/规则组件完成，但裁判核对原单元格后拒绝发布已知有错的自动检查点：Quotation!E24 的“Est. delivery incl. lead time”及E25:E27总交期可见，旧v1提取器只识别其他明确表头，将三项原总交期漏读为null、elapsed_time记0。原答复、工作簿、Worker和语义查询记录保持；裁判只写了evaluator-extraction-issue.json，没有导入语义响应或生成score。

Score0.10.126为新评分发布quote-explicit-arrival-and-mode-summary/v2，仅把规范化estdeliveryinclleadtime映射到原elapsed字段。原值、可见性、安全公式读取、总交期比较、重大事件封顶及60/40权重保持。旧v1 marker仍生成原f34b07bd…有效源码及原回执字节，不覆盖已用发行或旧分。

Orchestrate0.11.100接受本次新格式的精确裁判问题报告，独立复验原v6 contract/source、原v1 marker及Worker源码/成功回执、三项漏读、导出取证一致、原可见表头/总交期/前置说明、无score或语义导入。正式留证仍须真实完成态SDK的thread/cwd/model/high/完整Prompt核验。旧报告格式及其绑定保持兼容；新格式只锁定原件，不代判分。原attempt未评分保留，同一原执行另建独立评分后，按明确修复范围纳入完整70题。

75项相关检查通过，包含新别名/可见性、v1精确重放、未明确包含lead time的模糊表头仍不识别、严格裁判失败留证、原数值函数与限分AST不变、编排和独立发行。首轮开发测试有1项dotenv导入失败，保留日志；仅测试进程追加已有开发依赖后通过，正式受管运行时未安装额外依赖。正式原件只读验证通过。不push。
