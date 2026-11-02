# WorkBuddy共享文档宿主与分阶段收口

WorkBuddy的Tencent Docs `editor_sdk`可以跨题共享，并在原生请求结束后继续持有输入Workbook的读写句柄。
读写句柄只表示潜在写入能力，不证明业务内容已被修改；不能据此扣模型分，也不能在其他题仍运行时杀掉共享宿主。

正式finalizer的完整树静默与不可变校验保持严格。首次出现`WORKSPACE_NOT_STABLE`且未发布本题candidate时，
保留失败日志和所有原件，只读比较完整快照。已有candidate发生漂移不得用此流程覆盖、解锁或改旧SHA。

使用只读工具核对潜在写入者：

```text
node drivers/workbuddy/shared-writers.mjs --workspace ABS_WORKSPACE --app-probe FROZEN_WORKBUDDY_PROBE_JSON --output NEW_JSON
```

工具核对原App身份、PID启动时间/命令与父子链，在lsof前后复核进程未替换；仅明确属于该App的原生共享editor_sdk
可返回`DEFER_FINALIZATION_UNTIL_HARNESS_SHUTDOWN`。陌生写入者、访问模式缺失、PID替换或采集覆盖未知保持NEEDS_ATTENTION。
工具不关闭文档、杀进程、改Workspace、改候选或发送Prompt。

若命中已知共享宿主，采用下列顺序：

1. 每题真实终态后运行原collector，保存完整原生绑定、SDK、标准轨迹和资源；这些是采集输入，不是正式execution record。
2. 保留已有正式候选；对尚未正式收口的题目暂缓finalize。不要修改目录策略、排除受影响文件或把未完成采集标完成。
3. 全批原生任务终态、Prompt发送账本及原生证据全部保存后，按精确PID/启动身份有界停止该Harness及其已核验进程树。
4. 核对共享宿主和端口消失，保存停端证明；未知进程/锁不能直接删除或终止。
5. 离线对同一collector输入逐题运行原finalizer，继续真实Workspace进程清理、完整树静默、Office只读冻结和SHA核验。
6. 全组receipt生成后，对完整范围逐题verify-only。既有候选的严格CWM来源变体只走显式原有补充协议，其他漂移仍失败关闭。
7. 只有执行、正式采集/复验和停端屏障全部通过后才能交接私有评分材料。

允许在全批停端后正式finalize，是因为WorkBuddy collector只消费已保存的终态原生绑定和本机原始日志；
它不依赖仍在运行的客户端来重造轨迹。停端前必须保存这些原件，不得事后从最终文件推测工具、Token或会话身份。

WorkBuddy也可能将被拒绝的模型工具请求投影成cancelled/orphan_pending_history，而SDK只保存同响应model-usage及skipRun准入错误。
此窄范围只在完整身份、响应、parent与原错误逐字对账后接受；错误不是模型撰写的回复，仍保存在原SDK和资源警告中。
取消项继续保留，工具总数不强行与SDK数值相等；已验证小计与null/partial分别发布。未知类型、错请求、伪造结果或真实缺失仍拒绝。
