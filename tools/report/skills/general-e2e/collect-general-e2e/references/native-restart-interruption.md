# 后台重启中断证明

`bound-native-runtime-reconciled-interruption/v1`只为已取消的原执行确认实际停止，不能把失败转换为完成或可评分。

后台退出时可能保留部分工具/内容/用量投影，却来不及写provider `turn.completed`；之后原生client通过`restart-reconcile:<thread>:<timestamp>`将同一最新头及session登记为interrupted。不能补造缺失的provider终态，也不能因没有该行而删掉其他原始行。

采集器从同一个只读数据库快照保留完整provider行、原生head/session/pending/cwd以及原reconcile事件和命令回执。新Profile严格要求：

- 原state仍FAILED/cancelled、原Prompt发送一次，thread/turn/session/cwd及原SDK完整绑定；SDK唯一turn_aborted且reason=interrupted。
- SQL同一最新turn为runtime来源interrupted，session interrupted、active_turn_id=null、pending=0。
- 原始provider行非空且确实没有turn.completed，数量与同快照SQL计数相同；每行属于同thread/turn及已登记的非终态事件类型，出现外来身份或矛盾/未知生命周期继续拒绝。
- 只有一个精确thread.session-set事件，actor_kind=client，command/correlation ID均为该thread及其原时间戳的restart-reconcile；payload中thread/状态/active/lastError/updatedAt与SQL最新头闭合。
- 同快照accepted命令回执必须绑定同command、thread、event sequence、时间、无错误及原64位fingerprint；重放时逐项重验。事件时刻须在SDK中断与原控制器终态之间。

输出保留原state、SDK、全部provider原行与native-binding/reconciliation/receipt及SHA，provider_terminal_sequence=null，completeness强制partial，fabricated_rows=0。资源仍按原SDK和独立缺失覆盖复算，不用重启回执当作完整provider轨迹。旧单一终态、完全缺失及纯用量镜像Profile保持原字节/判断路径。未知回执、重启但没有绑定证据、正常完成或在途状态不适用。

原生后台日志可另作技术诊断，例如同时中断时有SIGKILL/自动重启记录；SIGKILL的发送方及根因不能仅凭此推断。该Profile不修改Harness、原执行、模型设置、候选、GT、规则或权重，不授权重跑，也不将中断归因为人工停止。

## 原执行状态的session字段滞后

`bound-native-runtime-interruption-stale-session/v1`只接受原state已FAILED/cancelled且精确错误码ASTRONSTUDIO_TURN_INTERRUPTED、session.native_status仍running的窄范围。原字段及字节不改；仍须独立满足同一最新SQL头已runtime interrupted、session interrupted且无active/pending、完整绑定SDK唯一中断，以及正常provider终态或上述严格reconcile证明。单独的running、未知错误、SDK正常完成或实际SQL仍活动均拒绝。新索引另记runtime-state-session-projection-stale并保持partial；不会把滞后字段改写为完成或给予评分资格。
