# AStudio原生运行时中断的失败证据收口

新通用70题round1的两题SDK在2026-11-05 23:05:46同时记录`turn_aborted / reason=interrupted`。次日原生SQL投影已明确`termination_origin=runtime`、turn/session均interrupted且无active turn；用户另明确并非手动停止。旧执行器可信地登记FAILED/cancelled，但没有历史`timeout.cancellation_confirmed`字段，原采集器因此拒绝正式收口。不能手填确认、把中间回复当终稿、改成能力零分或重发旧Prompt。

Collect0.11.28及resource组件1.3.7为此增加`bound-native-runtime-interruption/v1`。只对FAILED/cancelled且native_status=interrupted、唯一已发送并验证的原attempt启用，要求显式SDK规范来源。原state不改字节，额外保存三份bindings：原state、该次只读数据库快照的精确turn/session/最新head及目录记录、可离线复算的确认证明。

确认必须同时满足：

- SQL原turn确为runtime来源的interrupted；latest head仍为该turn、session interrupted、active turn=null、无待交互、绝对Workspace一致且有原生结束时间。
- 完整SDK的唯一session/CWD、原始Prompt SHA、唯一main turn及唯一interrupted终态一致；不能混入正常完成、人工取消理由、第二次发送或后续turn。
- 同一provider原件有且只有一个对应终态，宿主thread/turn、provider session/turn、interrupted状态、completedAt和durationMs与SDK逐项相同。

正式finalize在真实进程清理之前独立复核该闭包；verify-only和报告资源复算再次读取归档原件并复算。原有人工确认字段和普通成功流程不变；未知来源、未结束会话、缺证、修改SHA或混用身份继续失败关闭。新字段仅确认原生物理停止，不推断人工取消，不改变原cancelled结果、不改变可评分性或判分标准。中断题若不满足评分契约仍保持UNSCORED/null。

真实中断原件已独立归档并验证；单元与集成回归覆盖SQL/SDK/provider交叉身份、来源/待交互/目录漂移、重复终态、额外发送、原件及证明损坏，和正式冻结/不可变校验。旧冻结Skill、失败state/record、旧SDK及历史成绩保留；修复以独立发行和新的取证输出目录采用，不重执行模型或修改Harness。

Collect0.11.29另登记`bound-native-runtime-interruption-missing-projection/v1`，处理原provider投影已经不可读的已结束失败。它不能替代普通三方Profile：同一只读SQL快照必须额外返回该精确thread/turn的`runtime_turn_event_count=0`，原始provider归档必须确为零字节，SQL运行时来源/已结束状态/空active turn和完整SDK的原Prompt/唯一中断仍须全部通过。非空投影只有全部为`thread.token-usage.updated`资源镜像时才可进入此Profile：同一SQL事件数须等于原始归档行数，每行完整匹配宿主/provider会话身份，raw及归一化的total/last计数须逐项对应原SDK中的同一用量记录；工具、内容、活动或冲突记录一律拒绝，原始资源行完整保留。证明与trace-index显式标记partial，provider终态序号保持null、缺失原因保留；不补造原始行、不推断人工取消，也不改变原失败的评分资格。已有三方Profile及旧原件保持。
