# DoubaoWork macOS General 接续证据

日期：2026-09-23 至 24。范围：macOS x86_64、DoubaoWork 2.31.3、本地电脑、值守；包含单题与五题三槽开发验证。当前进度与验收项只在[统一接入契约](../../../e2e/端到端自动化评测Harness接入契约.md)维护。脱敏索引：[s1-development.json](s1-development.json)。

早期 r4–r9 开发链路从当前工作区 `feature/astroncode-eval` 的 `9310a96` 开始，工作区有未提交实现。每阶段实际代码由仓库外 Skill ZIP/content SHA 固定，`source_revision` 仅表示基线。它是跨开发版本完成的一次单题链路，**不满足同一发行的新任务 CV15 生产验收**。

原件根：`/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-general-20260923`。原始消息、完整目录、截图和原生会话 ID 不入仓。2.28.12 的只读探测在用户手动更新前完成；随后重新探测 2.31.3 和新监听进程，后续运行均属于新版本。

## 运行事实

- 题目：`02_Code_Intelligence_task_001_temperature_cli_fix`；批次 `doubaowork-general-r4`，执行 attempt `ed5ad5f6-4584-4cee-aa91-76964aa03dfd`。
- r1–r4 的发送前失败均为发送 0 次，分别暴露云电脑默认值、嵌套项目行、输入区项目残留和无 textbox role 的 ProseMirror 编辑器。原状态/目录保留；r4 的发送前失败通过门禁归档后才进入新 attempt。
- r5 实际发送 1 次，冻结显示值为“自动 高 / 全部允许”。Driver 未点击权限提升控件。首次绑定因渲染后的 Markdown 与原文摘要不符而超时，未重发。
- r6 恢复同一 attempt：UI conversation 与原生 session 目录一致；原生用户文本 SHA 与发送摘要一致；用户/助手 `general_task_param` 的两组 workspace 一致，project ID 一致；助手 `final_status.session=Success`、`status=1`、`stage=4`、`ext.is_finish=1` 和全部消息块完成标记一致。保留原生 request session ID 与 reply message ID 的不同语义。
- 原生 elapsed block 为 27 秒；发送边界至同一原生 `task_finish` 接收事件为 31.803 秒。没有把题目 timeout 作为期限或得分条件。
- r7 collector、真实 macOS cleanup、公共 finalizer 和 verify-only 通过，候选 SHA `402946787f5781e4d8bf180f52ada5379b88b6dfbfda3be61d71590767fd75ed`。清理前后目标进程均为 0，静默观察 9726 ms；此样本不证明实际 TERM/KILL 分支。
- 当前 trajectory 只有用户消息。正式标准轨迹含用户原文与原生最终回复，完整性保持 partial；原生消息块仍归档，不能把工具完整总量写成 0。Token、请求总数、工具总数、积分均未声明可用。
- 旧评分编排 `general-s1-r4`、`general-s1-r8` 因完整轨迹门禁保持 UNSCORED。新评分入口仅对可确认只消费 Workspace 的冻结 automated 规则接受上述 partial 轨迹；原回执未改写，语义或读取轨迹的规则仍拒绝。
- `general-s1-r9-001` 执行原自动规则，`result.valid=true`、`total_score=1.0`。submission、回传、导入、JSON/Markdown/Excel 报告已形成，Excel 10 个 Sheet/10 个关键范围及公式检查通过；总览和资源覆盖预览已人工核对。

## 实际版本与边界

准备包为 r4 suite；发送为 execute r5，恢复观察为 execute r6，采集为 collect r7，评分为 score r8 + orchestrate r9，回传/报告使用 r4 suite。均保留原始发行目录，未覆盖冻结产物。该组合仅证明当前开发链路，不能继承旧 Web canary，也不能替代新的统一发行验收。

初次共享提取的 Web 聚焦回归 64/64；General 适配和原生状态聚焦 9/9；发行/布局 20/20；评分相关回归 37/37，后续组合回归 38/38。测试对象、日志、实际包摘要与真实运行分别记录；这些数量不代表全部 CV/GV 或 Web 已通过。


## 后续独立运行

- **r10 S1**：同一发行的新 attempt 一次发送，首次 collect/finalize/verify、原自动规则、submission、回传、导入及三种报告完成，有效分 1.0。[包与证据 SHA](s1-same-release-r10.json)。这是 S1 范围的闭环，不是完整 Harness 准入。
- **r11 三题串行**：S3→S1→S2，各一次发送、原生完成。产品的非语义排队引导以唯一关闭按钮关闭后恢复原队列；控制操作单独归档。未正式评分收口，旧轨迹完整性不倒填。
- **r12 S2**：发送前安装本地原生工具 observer，6 次 started/settled 与同 agent 的结果账本逐条对账；14 条标准事件，完整工具轨迹。原 grader 有效分 1.0，同发行首次采集至回传/报告完成。[包与证据 SHA](s2-same-release-r12.json)。
- **r13/r14 S4**：纯回复题一次发送并原生完成；服务器 calculator 回放重复已保留诊断。r14 首次正式回执为 partial，旧编排保持 UNSCORED，不能覆写或补成 complete。
- **r15 五题尝试**：第一题一次发送，第二题目录助手失败且发送 0 次，其余未发送。队列 NEEDS_ATTENTION；第一题用原发行只读恢复至原生完成。未通过并发验收。
- **r16/r17 发送前失败**：r16 五个项目预建成功，但选择菜单只暴露近期项目路径，回读被拒；r17 原输入区项目被侧栏折叠，选择器拒绝。两轮全部发送 0 次。修复为精确项目编辑对话框的目录 tooltip 只读回验，以及输入区项目菜单自身语义定位。
- **r18 首三题并发**：S4/S3/S1 各发送一次，原生区间证实重叠3。切换会话后客户端转为历史 API 消息，缺实时 session/stage/perf 字段，旧 Driver 未放行；通过共享 UI 锁竞争安全停止队列，后两题未发送。新增历史消息 Profile 只读恢复原三题，并按同一请求ID收回工具原件，属于跨开发版本恢复。[三题证据](three-overlap-development-r18.json)。
- **r19 新五题**：冻结原生历史消息 Profile 和 trajectory 前缀/本地回调尾部合并后重新发行，五题各一次发送、原生峰值3及动态补位完成，首次 collect/finalize/verify 通过。S1/S4/S5 complete；S3/S2 partial，未评分门禁保留。S3 UI 有2次 calculator，而滚动轨迹只保留1次；旧工具字段13只能看作已知小计，不得作为已验证总量发布。S2 的本地-only 顺序被过度降级；新代码已修正，但不改写旧回执。[本轮证据](five-execution-collection-r19.json)。
- **r18 真实进程清理**：两个受控目录内进程被精确 TERM/KILL 清理，对照目录同类进程存活；实际 ps/lsof 和 signal，没有替换 inventory/signal hook；静默9069ms。[证据](cleanup-live-r18.json)。

当前生成的三份 Doubao vendor 来自构建产物，未手工维护分叉。r16 共享/General/Web 聚焦 94/94；Python 发行、布局和 partial 准入 19/19（仓库 `.venv`）。首次用系统 Python 运行的 1 项 dotenv 依赖错误单独保留，不归因于 Driver。统一接入契约是唯一待办状态来源，以上只是运行事实索引。

- **r19 迟到进程清理**：初始0目标；受控进程10秒后进入目标目录，真实进程枚举发现后终止，最终0目标、静默14625ms，对照存活。[证据](cleanup-late-r19.json)。本轮共享/General/Web 聚焦100/100；三个影响包构建校验通过。

- **r20 执行 / r21b 采集**：五题均一次发送、原生峰值3与动态补位完成；新增绑定 session 的滚动 trajectory 归档，S3 捕获7个版本。首次正式 collect/finalize/verify 完成，S1/S2/S5 complete、S3/S4 多源顺序仍 partial。S1/S2 原自动规则均有效1.0；S5 待语义评分。历史 API 的完成时间与本机 dispatch 不同钟域，流程耗时保持 null。该执行/采集跨开发版本，不冒充同发行全五题闭环。[证据与 SHA](five-development-r20-r21b.json)。
- **独立评分与报告**：用户确认创建后，r19 S4/S5 分别在两个独立 Codex 任务中以 gpt-6-sol/high 完成评分并通过 verify-score，分数为0.55/0.875。完整五题 submission、return/import 和 report0.5.2 已完成；3个有效评分、2个未评分，有效均分80.83/100。报告按绑定源 SHA 将旧 partial 工具总量降为已知小计，跨钟域流程/壁钟时间保持不可用，原回执与分数不改。Excel10个Sheet、关键范围、公式检查通过，并核对总览与资源覆盖预览。[证据](semantic-report-r19-report052.json)。r20 S3/S4 仍为 UNSCORED。
- **r22 构建候选**：`release-candidate-r22/` 为仓库外 General 独立 suite（含 report0.5.2）；`affected-r21b/` 包含单独的 General execute/collect 与 Web execute ZIP，均已构建校验。Node 104/104、Python 38/38；`git diff --check` 通过。源码未提交，候选未作为生产发行发布。Web 本轮只有共享改动回归，正式闭环未完成。

报告0.5.2的资源投影、报告视图、发行及布局回归40/40；report Skill ZIP独立构建校验通过。本次评分证明llm_judge分支可闭环，不把两题UNSCORED或其他未验CV/GV/WV转为通过。


- **r23/r24 生命周期调试**：r23 observer未绑定、r24绑定偏晚，均保留原attempt且未重发；没有把这两题认作新增生命周期计时通过。
- **r25 并发计时**：两题各一次发送，发送前安装生命周期观察并按原生request绑定；每题4个采样、无采集错误并恢复observer。首次collect/finalize/verify通过，两题trace均complete；原生任务耗时27/10秒，流程耗时29.698/12.398秒。精确切换为历史API消息后，S1仍从原本机绑定证据得到29.698秒，未改旧回执。本轮未选择评分。[证据](lifecycle-timing-r25.json)。
- **r26 S3 hybrid闭环**：一次发送，原生正常完成；任务耗时1183秒、流程1185.805秒。12次工具、26条标准事件，trace complete；本地事件与原生trajectory的6次重叠调用对账。首次collect/finalize/verify、原自动规则、独立gpt-6-sol/high语义评分、submission、回传、导入和同源三种报告完成，评分1.0且verify-score通过。Excel10张表、10个关键范围、公式扫描和全部预览已核验。模型并行请求顺序的优先分支另有聚焦测试，本次轨迹采用本地事件顺序，不把它当作所有混合来源通过。[同发行证据](s3-hybrid-same-release-r26.json)。
- **Token来源审计截至r26**：26份trajectory、26份绑定原生消息，3份可读SDK日志中的8380行关联记录未发现累计input/output/total/cache/reasoning Token计量字段。26份窗口占用、11份订阅显示和6处技能usage列表不作为Token；first-token字段是时点。2份原生二进制日志尚未解码。标准Token、模型请求及重试字段保持null。[脱敏索引](token-source-audit-r26.json)。
- **r27路径与账本加固**：共享Driver0.6.2、General execute0.11.2/collect0.8.2、Web execute1.17.2，按构建产物同步三份vendor。路径检查读取真实文件系统字节预算，恢复拒绝未初始化活动状态。工具账本每秒只读保全已观察调用的uploaded结果及首次观测时间，完成后恢复定时器与原回调；模拟TTL淘汰、迟到采集、冲突和时点篡改测试通过，不能称超过30分钟真机通过。当前聚焦Node114/114、Python31/31；中文/空格目录S2一次发送完成，5次工具全部在终态前留下uploaded账本证明，observer恢复；任务68秒、流程70.766秒。同发行首次采集/冻结/verify、原自动规则1.0、回传/导入和三种报告完成，Excel全10表已核验。六类真实文件系统负例均在调用客户端前拒绝，发送0；最长数据集ID62字节仅预算预检，未声称真实UI验收。[路径与账本证据](path-and-ledger-r27.json)。

- **r28边界复核**：正式r27材料的完整副本verify通过；五类材料篡改/缺失/链接/迟到写入/身份漂移分别拒绝。独立General/Web包共享锁使用真实进程身份验证竞争、dead owner及release owner变更，原锁保留；外部监听者和关闭端点在CDP连接前拒绝，均发送0。公共finalizer15/15、评分编排19/19；初次finalizer使用系统Python3.8失败，切换仓库Python3.11后通过，原失败日志保留。迁移batch副本的重复导入尝试被MANIFEST_DRIFT先行拒绝，不能当作幂等导入验证。未强制客户端重启、锁屏或中断活动任务。[边界证据](boundaries-r28.json)。

- **r28当前核心五题闭环**：五题各发送一次，原生峰值3与动态补位，首次采集/冻结/verify全部trace complete。S1/S2自动规则1.0；控制任务按已授权全流程自动创建三个独立sol/high评分任务，S3 hybrid=1.0、S4=0.95、S5=0.875，均通过verify-score。完整submission、回传、导入、重复导入幂等与三种报告完成，5有效/5，均分96.5/100。任务耗时383秒、流程耗时395.3秒、工具23次，覆盖均5/5；Token/模型请求/重试仍null。[完整证据与包SHA](five-same-release-r28.json)。
- **报告显示修正**：r28原suite使用report0.5.3，发现L1均分95.625在Markdown显示95.62、Excel显示95.63。report0.5.4统一十进制ROUND_HALF_UP，另建`r28-report054`，未覆盖旧报告；原始overall/units/tasks/presentation/lineage完全一致，显示现为95.63，29项回归、10张表/10范围/公式扫描和全部视图检查通过。该补丁与r28原suite分开留证，不改写执行、评分或旧回执。`release-candidate-r29`纳入此报告补丁并完成构建，尚未发布，也不表示所有加固项通过。


- **r30–r33 发送边界与恢复**：五个真实 SIGKILL 窗口覆盖 intent 前后、点击前后及接受确认后。点击返回后未落盘的发送仅凭原生用户确认恢复，同 attempt 不重发，未知点击返回时间保留 null；有 owner 证明的单题锁独占归档，journal 字节不变。已发送原请求活动时拒绝恢复；不确定零发送只读暂停。r33 在明确零发送后显式重试，新 attempt 一次发送，首次 collect/finalize/verify 完成。r30 执行与 r31 采集属于跨开发版本，不替代同发行验收。[发送恢复索引](interruptions-recovery-r30-r33.json)。
- **r31 延迟采集、r33 清理故障**：真实约35分钟后采集5条工具账本，首次观测均在原TTL内，首次collect/finalize/verify完成；原生Map仍保留记录，未证明真实淘汰或35分钟任务。实际ps/lsof加时序barrier覆盖子进程重挂；真实inode替换使cleanup及正式finalizer拒绝发布，对照存活，原inode与文件恢复后verify通过。[账本与清理索引](cleanup-ledger-r31-r34.json)。
- **r34–r37 交互与后台交付**：真实权限漂移、陌生弹窗、第二安装端点错配均发送0；陌生弹窗由Driver保留。独立授权fixture真实出现CDN iframe，新增原生授权与侧栏标记绑定，自动collector拒绝缺人工介入回执的结果。前台Success后仍残留后台Write，新门禁阻断新发送并拒绝原题完成；精确Abort未清除残留，保留证据后受控重启DoubaoWork，前台/后台/pending均0，权限恢复原值，外部标记文件始终不存在。未重启Codex、未重发Prompt，fixture不计能力分。[交互与重启索引](interactions-restart-r34-r37.json)。
- **r37 正常与并发回归**：S1与纯回复S4各发送一次，原生峰值2，首次collect/finalize/verify均complete。任务耗时32/8秒、流程35.428/10.223秒、工具6/0次；Token与模型请求/重试仍不可用。本轮未评分或生成新报告。共享/General67项、Web64项测试通过，独立Web包真机probe通过，正式receipt/batch路由继续拒绝。[回归、包与指标索引](concurrency-packaging-r37.json)。
- **r37b 发行候选**：修正r37内部Driver版本标记0.6.8与目录声明0.6.9的不一致，只改变lib.mjs常量和生成的组件摘要；三个独立包及完整General suite重新构建，三份vendor的19个文件保持同源，新增版本一致性检查后Python发行/布局21项通过。候选未发布，原r37包和执行材料未改写，未把版本标记修正记为新增真机执行。
