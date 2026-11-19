# round3 无PPT分支的条件取证缺失

v6 Office017 的原生产者在候选 `results` 中无 PPTX 时，明确写出 `candidate_status=missing`、空候选清单、已核验参考及原规则的 `delivery_usable=0`，但不会生成 `02_candidate_*.json`。通用读取器将这条声明当成所有分支的必需文件，因此原 Worker 和规则组件均已成功，后置取证验证却以 `JUDGE_EVIDENCE_MISSING` 阻断整编排恢复。

Score0.10.124 增加独立 `declared-missing-deck-evidence-absence/v1`，精确绑定 v6 原 contract/source 和原通配符。仅在原候选和 runtime 均无 PPTX、无路径风险、原状态逐字段符合 missing 分支、原 Worker 原样诊断及数值完全一致时，记录候选页条件缺失。状态与参考仍完整归档，不新增候选页、占位文件或业务内容，不改原规则及 Rubric。其他缺文件、损坏候选、unsafe 路径、错误参考、状态不明、Worker 冲突仍拒绝。

新只读验证器可显式核验旧失败，供已有 `record-unscored-evidence-glob-error` 严格锁定原 attempt；旧 Score、Worker、候选和回执不改。语义准备必须由新 attempt 冻结该 Profile，不能借新读取器原地续判旧失败。新快照清单明确列出条件缺失及原状态 SHA，独立裁判仍按原全部检查点评分；规则0不冒充整题0。

34项条件缺失、通配符、原缺答复及独立发行检查通过。合成反例覆盖实际PPT存在、损坏/unsafe状态、错误参考、伪造数值、未完成取证、原Worker冲突和Profile漂移；正式旧原件的只读校验通过。首次开发测试因开发解析器的dotenv依赖不在受管评分锁中而有2项导入失败，保留日志；仅给测试进程追加准备环境的开发依赖路径后全通过，没有修改正式评分运行时。
