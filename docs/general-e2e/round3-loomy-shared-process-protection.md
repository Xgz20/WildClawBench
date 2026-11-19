# round3 Loomy 共享进程保护补齐

正式收口前检查发现，通用macOS清理器已保护AStudio共享服务，但没有显式识别Loomy。
实际本轮Loomy与OpenCode当前cwd均不属于任务Workspace，因此尚未命中清理目标；
不过若共享服务cwd落入某题，旧选择器会把它当作单题进程，不能满足本轮保护要求。
本修复在任何正式finalize及清理信号之前完成，未停止在途任务或操作客户端。

task-process-cleanup0.2.1保守识别Loomy应用及其Helper；当同父进程的opencode serve
属于已识别Loomy主应用时，将其列为shared-loomy-opencode基础设施根。即使cwd或命令
命中某题，也不向这些根发送信号。依赖树和祖先进程保持保护，共享树内归属不明的
任务进程继续阻断收口，而非直接清理；独立、可归属的任务进程保留原清理路径。
每次实际信号前仍重新核对进程身份及保护树。

共享源码与Collect内的兼容副本只允许既有import路径差异，字节等值已校验。
Execute0.15.21更新携带的共享依赖，Collect0.12.29更新正式清理器及Loomy hook0.1.1。
本轮正在运行的执行队列仍沿原c02e3c6c发行，不迁移、不增加source-repair或重发；
原生采集/收口选用新的Collect，其余评分、Run和Report继续沿c02e3c6c冻结发行。
Loomy共享组件0.1.15的八个文件、原输入、候选、Rubric、资源口径和历史发行不变。

合成反例直接覆盖“Loomy后端cwd命中任务目录”：应用和共享后端不进入targets，
未知共享子进程出现在blocked_shared_processes，独立任务Python进程仍可被选择。
ASTudio原共享服务保护、信号前身份重验和零信号阻断回归保持。正式回执仍须在全70题
可信终态、全部原生collector输出之后逐题finalize，并完成全单元verify-only。
