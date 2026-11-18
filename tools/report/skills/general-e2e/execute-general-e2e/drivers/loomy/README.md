# Loomy macOS General E2E

适配 Apple Silicon Mac 上的 Loomy 0.9.39，当前模型组合为 `spark-x2.6 / high`。
需要 Node.js ≥22、Python 3、Swift 编译器和现有 macOS 辅助功能权限。正式包通过
原生 AX 操作，不需要 Electron CDP；入口不会启动、退出、修改或重启客户端。

先在已登录、无冲突活动的 Loomy 中选好 Spark-X2.6 正式版／高，再运行只读探针：

```bash
node drivers/loomy/probe.mjs --output /absolute/new-probe.json \
  --config-output /absolute/new-run-config.json
```

探针冻结应用 Bundle、精确主进程及启动时间、辅助功能 helper、随包 OpenCode
进程、二进制摘要、数据库实际持有关系和 loopback 状态接口。数据库通过只读连接
在线备份查询。未知应用版本、配置、锁屏、进程身份或活动状态会阻断执行。
后端尚未运行时，探针只冻结随包二进制实测版本/摘要和数据库路径，保留运行状态为空；
实际 PID、端口、数据库所有权及 health 由首次正常发送后的原生观测建立，不另发启动 Prompt。

若上一个批次的主模型 HTTP 5xx 已正式收口，但数据库仍把空终态消息列为未结算，
可向探针重复传入 `--archived-failure-record ABS/execution-record.json`。探针校验
采集回执和归档轨迹，在运行配置中锁定原会话、完整工作目录及终态消息摘要。
后续派发、收口和离线复验继续核对该终态，原生状态为忙碌、待执行工具或
新增未结算子会话时停止。此参数只接受正式归档的 Loomy 原生 HTTP 5xx 执行记录。

使用标准 `prepare-general-e2e-workspaces` 生成并安装的 execution unit：

```bash
node drivers/loomy/driver.mjs --unit-root /absolute/unit --task-id TASK_ID \
  --run-config /absolute/new-run-config.json
node drivers/loomy/batch.mjs --unit-root /absolute/unit \
  --run-config /absolute/new-run-config.json --queue-id loomy-validation --run-slots 1
```

Harness 配置为 `id=loomy`、`platform=macos-arm64`、`requested_id=spark-x2.6`、
`reasoning_effort=high`。队列按 manifest 顺序派发，支持 1–3 个后台槽位，默认 1；
UI 发送固定串行。原生并发能力须另以真实会话区间验收，不由配置值推断。

每题在原生目录面板中按完整 URL 选取目录，并从工作目录菜单的 AXHelp 再次读取
完整路径。已有已登记目录可直接按精确路径选择。客户端按目录保存的权限策略原样
保留，选中目录后记录并冻结该题权限；驱动不点击权限选项。模型、权限和完整 Prompt
在发送前以及原生发送动作内再次核验。

发送意图和次数先持久化，最多调用一次发送。`--detach-after-submit` 只在原生
session、唯一用户消息、完整 Prompt、cwd、`imodel/spark-x2.6` 与 `variant=high`
全部绑定后返回。Loomy 的记忆索引前缀按客户端原生格式单独保留，原题必须唯一且逐字
匹配，High 同时核对原生用户的 `model.variant` 与主助手的 `variant`。
`--resume` 只观察原 attempt，可加 `--observe-once`。不确定发送、
外来活动、配置漂移和未登记恢复均进入关注状态，不能重发旧请求。

任务没有执行 deadline。UI 操作及首次原生身份绑定的观察超时不表示被测模型失败。
主模型 HTTP 5xx 重试后仅留下空的已结束助手消息时，驱动只读取该后端启动时段的原生日志，
逐项核验 session、原 Prompt、Spark/High、请求时间、全部工具结束和新鲜空闲状态，归档
原错误行并记录 FAILED。辅助标题/记忆请求、其它会话、HTTP 402、待执行工具或未确认空闲
不适用此分支。保留候选与原轨迹，交原 Rubric 评分，不重发、不把空消息当作成功终稿。
终态由同一运行时的空闲状态、绑定主助手的原生结束字段及全部关联子会话共同确认，
纯回复任务同样适用。未知交互不自动回答；问题工具需要独立人工介入回执，当前自动
采集会拒绝这类材料。硬终止遗留的 owner lock 不自动删除。

兼容性修复接续旧发行时，单题及队列可显式传 `--source-repair-manifest ABS`。
清单位于 unit 的 `.general-e2e/source-repairs/`，冻结原 manifest/config SHA、旧/新
组件身份、当前八个组件文件 SHA、关键 UI 源码等值证明、旧队列/状态/journal 原字节，
以及已 armed attempt 和从未发送题目的明确范围。已 armed 任务仍只观察原发送，未发送
题目才可首次派发；旧输入和旧发行不修改，清单随正式原件归档并离线复验。

执行状态是采集前记录。正式候选、轨迹和回执由 `collect-general-e2e` 的 Loomy
入口生成。安装包、题目、GT、权重和历史批次不由本适配器修改。

全单元执行及原生采集完成后再统一 finalize。后端在已确认缺失且全局无未结算会话时，可由正常首次发送启动；发送计数仍为 1。
单题仅对无 UI 准备、无发送意图的零发送失败显式加 `--resume --retry-pre-send-failure`，队列使用 `--retry-pre-send-task-id ID`。恢复保留旧状态/journal 原字节，不适用于已 armed 请求。
