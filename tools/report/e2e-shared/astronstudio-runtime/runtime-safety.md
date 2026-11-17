# AStudio 共享运行时与异常留证

适用于一个 ACode app-server 承载多个 workspace/session 的 AStudio。进程 cwd 可能只是首次启动目录，不能据此认领为某道题独占进程。

## 执行与正式收口

执行队列完成一题后只腾出槽位。执行期间可只读归档原回合轨迹、资源和诊断；不要自行在完成回调里逐题调用带进程清理的正式 finalize。

正式收口核验同单元已受理任务、队列及 owner 锁，再从冻结 run-config 指向的原生数据库读取全局状态。其他项目的活动会话、孤立活动会话、待处理交互或未知状态都阻断收口；每次发信号前再次核验。门禁错误保留框架诊断，不修改任务终态、分数或旧 attempt，不自动重试或重启。

`closed-structured-gateway-ledger/v1`仅对没有原生线程、会话、runtime或交互的`structured-UUID`一次性请求解释已关闭的网关结算尾账本。完整保留同一turn的开始、请求完成及最后`complete=true / requests=[]`记录；请求身份、原始/归一化状态、时间、顺序和全部已知字段须闭合，不能只有末条或按前缀认定空闲。其它事件、未完成请求、缺历史和未知字段继续阻断。安全快照及进程收口证明保留账本、事件序号和原JSON SHA，不删除或改写原生表，不将其作为候选任务完成、模型身份或能力得分证明。

清理器保护原生应用、后端、共享 app-server 及其依赖链。只有独立、归属于该题目录的普通进程可以按既有身份校验清理。共享子树内还有匹配本题目录的非基础设施进程时，保留它并报告 SHARED_NATIVE_TASK_PROCESSES_ACTIVE，等待原生后台任务收尾或按现有证据协议核实；不能放宽 PID 排除规则继续强杀。

新状态沿用冻结 run-config。缺配置的历史状态只有在采样证明没有原生基础设施时才接受离线收口。已冻结证据的离线验证不要求在线门禁，旧评分和证据继续按原闭包复验。

## 自动采样

Execute 默认约每 30 秒采一次，文件位于控制目录的 diagnostics/ATTEMPT_ID/，不进入候选 workspace；不同 attempt 分目录，重试不会覆盖旧诊断：

- PID、父 PID、启动时间、命令 SHA、CPU/RSS 和基础设施角色，不保存完整 argv；
- 宿主停止、退役、看门狗、断连标记，保留源路径、inode、字节位置及摘录 SHA；
- 原生异常、进程身份变化或新增告警时，读取状态与内核日志库的受限只读副本。

普通输出预算 16 MiB，异常有预留空间，重复读取故障节流。普通输出预算耗尽后仍检测进程/日志告警。增量读取、条目数和数据库查询均有上限；轮转缺口、截断、文件缺失及读取失败写 unavailable，不补造事件。没有完整原始行号时明确 source_line=null，保留 byte offset；导出文件自身行号可直接引用。

日志只保留诊断字段，过滤 Prompt、推理正文、模型输出及登录帧，脱敏令牌、密码等值。原字节 SHA 用于定位；摘录不是未经处理的全文，也不是独立评分依据。

每次采样记录开始/结束时间、自身耗时、框架进程 RSS/累计 CPU 用量以及系统空闲内存/负载。累计 CPU 不是瞬时占用，系统空闲内存也不是 OOM 证明；用于与原生事件、进程 CPU/RSS 对齐，不据单个样本归因。

框架派发、原生终态和收口事件位于单元 .general-e2e/diagnostics/framework-events.jsonl。信号记录包含发送进程、关联 ID、目标指纹、意图/结果时间和错误。信号意图先持久化；审计写入失败时不发该信号。审计达到容量上限时保留原日志并报错，不覆盖旧记录。

正式收口将当时 journal 的完整行前缀复制到 execution/diagnostics/framework-events.jsonl，并附来源路径、inode、字节边界、原始起始行号及 SHA。保留行序便于引用；复制后追加的事件不冒充已冻结证据，当前收口的信号记录同时保存在 process-cleanup.json 中。

## 单独补采

保留现场时可用同一发行 Execute 的只读入口，输出必须是新目录：

~~~text
node /ABS/execute-general-e2e/scripts/capture_astronstudio_diagnostics.mjs \
  --unit-root /ABS/unit \
  --state-file /ABS/unit/.general-e2e/execution/TASK/automation-state.json \
  --output-dir /ABS/control/new-diagnostic-capture \
  --reason native-interruption-review
~~~

该入口不修改源 state、不发 Prompt、不调用工具、不启动/关闭客户端、不改分；receipt 记录来源 SHA 和只读口径。不能用它修改已冻结评分输入，或把后续版本日志冒充历史日志。

## 异常后的边界

1. 保留同 attempt，停止不安全的新派发；不重发发送状态不明的输入。
2. 核对 state.evidence.runtime_diagnostics 引用的 index、框架 journal 和收口失败诊断。正式收口的诊断随证据进入 SHA 校验和回传。
3. 区分框架明确发送的信号、内核收到的宿主 turn/interrupt、尚未知的宿主上游原因。一个动作不等于全部上游原因。
4. 已执行原作答按原检查点处理，故障单独留档。门禁/诊断缺失不自动转能力零分；框架或题源缺陷按既有修复和重新执行规则处理。

外部采样不能创造客户端未记录的 stopAll 调用栈、强制退役旧/新身份指纹或后端看门狗的 PS/信号原因。不能唯一判定时，列出缺失文件、时间窗、PID/thread/turn/request ID 和缺字段，再交由用户决策；不要以“未排除”替代实证归因。
