# AStudio 队列异常取证

每个 AStudio 队列在 `<queue-root>/native-logs/collector-v2/` 下保留只读观察得到的原生日志。采集与队列 Worker 分进程，约每两秒读取新增字节。Worker 退出后继续采样最多 120 秒；在此期间接续同一队列会接回原采集进程。采集进程自身退出后，队列可以从已提交游标重启采集，单个 Worker 最多重启两次。准备、派发并发与正式归档门禁仍按各自既有配置执行。

## 取证位置和范围

- `status.json` 记录采集进程实例与心跳；`index.json` 记录原始文件的设备、inode、生成时间和偏移。读取窗口包含 `desktop-main.log`、`server-child.log`、`server.log`、`provider/events.log` 以及各自的 `.1`、`.2`。单次读取每个 inode 最多 1 MiB，剩余字节继续从原偏移读取。
- shutdown、异常退出、SDK 或传输中断，以及已跟踪的 Node.js 后端或 ACode app-server 进程退出，触发异常窗口。通常保留首次触发前 120 秒、末次同波触发后 75 秒；同一角色观察到不同进程代次退出时开启另一个窗口。窗口内可能保留多条互相关联的退出证据。
- `incidents/incident-*/incident.json` 记录触发位置、队列任务和原生 thread/turn、框架事件、进程身份及 I/O。逐片 SHA-256 指向 `raw/` 下的原始字节，`integrity.json` 记录清单 SHA-256。先等待目录从 `.pending-*` 原子收口，再用上述摘要核验。原始字节已经保存在异常目录，滚动缓冲淘汰时仍保留。
- 滚动缓冲上限 64 MiB 或 256 段；单个异常原始字节上限 128 MiB，单队列最多保留 32 个异常。采样首次入场、原文截断、轮转前未读完、写入失败、主机重启、采样中断和预算触顶会留下相应记录。字节不可知时记录为 `null`。窗口按采样时间定位，已保留的原始行提供事件原生时间。
- 异常目录为本地私有诊断数据。工程分享前按现有流程处理原始日志中的任务内容和用户数据。正式 collect 继续等待原生全局空闲。

## I/O 和进程关联

框架共享 SQLite 快照继续在临时副本上执行 `quick_check` 和查询。诊断事件记录复制、副本主库及 WAL 大小、校验及查询耗时、失败阶段和重试原因。WAL 大小为 `null` 表示该次未复制到 WAL。采集进程约每五秒记录 AStudio 和已经确认由本应用启动的共享 ACode 进程 PID、启动时间、CPU、RSS、进程累计磁盘读写量，以及全机 `iostat` 和内存压力信息。字段缺失或采样断点应连同结论一并说明。累计值用于对照区间增量，SQLite 写事务阻塞、文件级 I/O 延迟及信号发送方需结合相应产品或系统事件确认。

## IT 和 AStudio 研发提供的证据

采集进程封存时读取 `collector-v2/external/endpoint-security.jsonl` 和 `collector-v2/external/astudio-lifecycle.jsonl`。接入方按每行一个 JSON 对象写入私有目录，使用 UTC `at`、该机 `boot_id`，可提供 `monotonic_ns`。截至封存时，框架在异常窗口内按启动 UUID 加关联 PID 匹配事件；每个输入读取末尾最多 4 MiB，保留最多 1000 条匹配记录。没有输入、未匹配、读取范围不完整或输入损坏时，以清单中的状态和计数为准。

- **IT**。用获批准的 Endpoint Security 采集器提供 `signal`、`exit` 和 `coverage` 事件。保留 `source_pid`、`source_start`、`target_pid`、`target_start`、`signal`、`exit_status_raw`、`seq_num`、`global_seq_num`，在 `coverage` 提供丢失计数 `dropped_count`。对疑似系统级 I/O 卡顿补充同机同时间段的存储或 I/O 事件。
- **AStudio 研发**。分别在桌面主进程、AStudio Node.js 后端、ACode app-server 和 watchdog 写入进程角色、PID、进程启动时间、`event`、`request_id`、`reason_code`。记录 shutdown 请求来源、信号发送方和目标、SQLite 写事务等待或繁忙超时，以及 SDK 传输关闭的时序。同一次触发的各条事件沿用请求 ID。

框架无需管理员权限，也可生成异常清单。外部证据缺失时，清单仍可帮助区分发生时间与进程身份，信号发送方和 shutdown 请求来源保留待核实。
