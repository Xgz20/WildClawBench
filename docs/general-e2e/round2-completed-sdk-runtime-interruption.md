# SDK完成后原生运行时中断的证据交接

本轮Data008的同一SDK回合在19:18:21 UTC完整结束并保留终稿，原生状态库随后在19:24:21标为runtime中断；采集时该运行时已停止，仅剩与SDK精确对应的用量记录。原执行记录仍为FAILED/cancelled。旧采集器要求所有原生中断均有SDK turn_aborted，因此拒绝了这组不同的原生事实。

general-resource-supplements 1.3.17新增`bound-native-runtime-interruption-after-sdk-completion/v1`。限定AStudio3.6.4、原生受理/同thread-turn-session-cwd、唯一无错误SDK完成及匹配的完整助手消息、严格较晚的原生runtime中断、显式停止运行时、相同cursor与生命周期、无active/pending，以及空投影或逐行匹配SDK的纯用量投影。未知字段来源、实际活动、错误/多回合SDK、非匹配终稿、时序矛盾和非用量尾记录均继续拒绝。

规范轨迹将SDK生成的终稿按SDK来源保留为final消息，不能据此声称客户端展示了全文。证明分别记录sdk_completion_confirmed=true、sdk_interruption_confirmed=false及原生运行时中断；原状态、原始SDK、原生绑定、工具回执和候选均不改写。Collect0.12.20、Score0.10.112及Report0.8.64离线重放同一证明。原FAILED/cancelled及实际计时保持，仍由原规则和独立裁判逐检查点评分，不赋策略零分。

验证使用合成SDK/原生快照及专门的负例、可移植回放、三种原grading_type交接、未改数值规则读取终稿的检查，并对真实Data008原件只做不判分的纯推导。运行时锁、候选、任务范围、Rubric和权重不变；旧证明按原逻辑回放。原生中断的上游原因并未因此闭环。
