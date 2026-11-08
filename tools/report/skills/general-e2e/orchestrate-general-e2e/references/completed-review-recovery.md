# 原生裁判完成但没有成绩文件

原生线程结束不等于已发布成绩。先检查 `score.json`、规则复核审计与原Worker；不要反复向同一输出路径写原生上下文回执，不重发原裁判Prompt，不将缺分计0。其余已有成绩可以继续校验登记。

Data010完成全部状态复核后，若精确绑定的原Worker仍拒绝“……另N处（见来源索引）”定位，`record-unscored-rule-review` 核验完整查询/原生模型及Prompt、原源码与错误模式、全量上下文、原业务文件未变和未发布数值后，可保留未评分。该证明是控制器对原Worker结果的确定性派生，不伪称原生消息，不改变语义判断或来源内容。旧2276项的已发布证明仍精确回放。

旧0.11.72控制队列恢复时，可使用 `scripts/repair_completed_review_entrypoint.py --legacy-cli ABS --legacy-sha256 HEX` 后接原CLI参数。它验证原入口SHA及版本，只替换当前冻结修复的 `unscored_rule_review` 模块；原Prompt生成、状态机和评分Skill保持。持续通过同一已绑定修复入口操作旧队列，保存原入口/新模块/状态快照与SHA；不要修改旧发行或手改状态。
