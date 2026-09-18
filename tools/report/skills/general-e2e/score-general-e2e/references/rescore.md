# 独立重评分 attempt

`prepare-rescore` 只接受已通过 `verify-score` 的终态源 attempt，包括 `result.valid=false / total_score=null` 的合法评测异常。命令复制冻结候选、任务、contract、GT、标准轨迹、运行时锁和执行回执，重新建立干净的 runtime workspace，并写入 `lineage.kind=rescore`。

必须提供新的 `scoring_attempt_id` 和完整 Judge 配置。切换 `codex-agent-judge-v1` 与 `api-judge-v1` 是显式的新评分，不是 fallback；API 后端还必须提供新的 runtime 配置。新 attempt 记录源 manifest、score、候选和 Judge 摘要的哈希与身份，不复制上次规则执行或语义判断产生的可变文件。

源 attempt 不得被修改。目标目录已存在、attempt ID 复用、源分数未终态、候选哈希不一致或 lineage 不完整时失败关闭。
