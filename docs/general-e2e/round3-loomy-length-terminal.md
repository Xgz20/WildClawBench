# round3 Loomy 原生长度截断终态

正式第3题的同一原生主助手消息以 `finish=length` 结束，存在明确完成时间，全部
工具均已结束且原随包服务空闲。旧执行器只接受 `stop` 或原生错误，因而持续观察
这个已结束的会话。此次框架修复不重新发送该题，也不修改原回答或能力评分。

共享 Loomy 组件 0.1.14 增加独立长度失败证明。必须绑定唯一原 Prompt、工作目录、
原生 session、用户模型 variant 和全部主助手 High，核验全部工具与关联子会话结束、
同一服务新鲜空闲后才记录 `FAILED / candidate_error / LOOMY_NATIVE_OUTPUT_LENGTH_LIMIT`。
原消息、step finish、截断前内容、工具结果和原候选全部保留。没有主终稿仍明确缺失；
新证明不把缺失答复当成功，不产生策略零分。待处理问题工具停止新派发，不能代答。

Collector、离线 trace/resource 回放、正式 finalizer 与独立评分准入共同核验该证明。
评分端从原 JSON 列、完整消息子树、一次发送、冻结配置和来源 SHA 独立复算；沿原
Rubric 逐检查点交规则与独立 Judge，不重跑 Harness，不改权重、题面或任务范围。
Token/缓存/请求数继续不可用，原生耗时保留 inferred 来源。

适配时仅在队列没有 DISPATCHING 行、没有单题 owner 锁的明确边界停止本控制器。
Loomy、OpenCode 与被测子进程均未收到信号。旧队列、状态、journal、控制器身份、
原 owner 字节及 SHA 先留证；不手删未知锁。新增显式 `recover-controller-lock.mjs`
只接受 SHA 绑定的已知控制器停机回执、同主机且已退出的精确 owner、所有来源字节
未变、全部已有发送原生身份明确、没有单题锁及新鲜全局安全状态。原 owner 通过
rename 归档保留，不删除；未知、仍存活、漂移或未绑定的 owner 均拒绝。该入口本身
不派发、不停止原生进程，也不改变队列或发送次数。

恢复仍使用同一队列、原配置及新的显式 source-repair manifest，冻结旧源码、队列、
状态、journal、已 armed attempt 与未开始题范围；关键 UI/Swift 源码必须逐字相同。
已发送题只观察，未发送题按冻结题序首次派发。旧发行、原执行 attempt 和原始证据
完整保留。六个下游阶段独立另存新发行，原正式批次与数据集身份不变。

验证覆盖完整长度终态、同一来源的主会话/子会话、缺完成时间、忙碌服务、未结束
工具、错误模型、错误 finish、未知 owner/活 owner 与锁漂移拒绝；原 HTTP 5xx、
一次发送、Prompt/High、资源保守值和 source-repair 回归保持。正式原生第3题另有
只读证明验证，通过后才恢复旧队列，不使用合成材料代替真实终态。
