# WorkBuddy原生错误页与零发送准备恢复

本入口不修补WorkBuddy程序，不取消已受理任务，不判断候选分数，也不处理未知发送。
新队列在零发送准备错误后停止补位，先观察已有原生任务至终态，再保持NEEDS_ATTENTION。
原生React错误页只属于Harness诊断；保留错误文本和组件堆栈，不把它当作模型能力零分。

## 原生界面恢复

先证明原队列owner已退出。活owner只能观察；未知UI/attempt锁不得手删。
如果还有已发送任务，只用原冻结单题execute的`--resume --observe-once`观察相同身份；不能重发或刷新活动客户端。
全部本地原生session空闲后，可调用：

```text
node drivers/workbuddy/recover-ui.mjs --invocation ABS_EXECUTION_LAUNCH_JSON --audit-root UNIT/.general-e2e/ui-recoveries/NEW_ID --expected-owner-pid OLD_PID
```

invocation的argv必须是原队列完整命令。入口校验owner已退出、无attempt锁、应用/进程/本地session空闲及模型/权限；
只在唯一原生“出错了／点击查看错误详情／刷新页面”错误页上点击一次公开刷新按钮。
它保存点击前原件与意图，随后只观察同一恢复，不重复点击或操作Prompt。重新核对同一进程、
完全相同的原生session集合、空编辑器和唯一“新建任务”控件后，返回PASS_UI_RECOVERED_WITHOUT_PROMPT。
失败保留审计目录；不要用新目录盲目重复刷新。未知页面、活动任务、锁和身份漂移均失败关闭。

WorkBuddy5.9.3刷新后可能回到空白“本地助理”首页，其“快速/default-sandbox”属于另一视图，不能拿来核验Task配置。
若原回执严格为一次confirmed刷新后的`REFRESH_NOT_VERIFIED_DO_NOT_REPEAT`，可用新发行的只读入口先核验：

```text
node drivers/workbuddy/resume-ui-task-mode.mjs --invocation ABS_ORIGINAL_LAUNCH_JSON --audit-root SAME_ORIGINAL_UI_AUDIT --expected-owner-pid OLD_PID --verify-only
```

只在同一5.9.3进程/原生会话集合、原owner已死、全局闲、无锁或草稿、唯一新建任务入口均通过时，省略`--verify-only`才最多点击一次原生“新建任务”。
入口不再刷新、不选择模型或权限、不选择Workspace、不发送Prompt；进入Task视图后必须回读原冻结模型/权限。
原`recovery.json`字节不改，新证明另存同目录`task-mode-resume.json`并引用原SHA。已armed的导航只观察，未准入不重击；未知首页、Task配置漂移或新活动仍拒绝。

## 显式队列恢复

创建新的JSON恢复清单，schema_version固定为`wildclawbench.workbuddy-zero-send-queue-repair/v1`，包含：

- `reason`：本次已核验框架问题与恢复原因。
- `original_argv`：原冻结node、batch.mjs及完整参数数组，不加resume/status。
- `original_batch_sha256`、`queue_sha256`、`expected_owner_pid`：原件和已证明退出的owner。
- `retry_task_ids`：按原manifest顺序列出全部待恢复的注册零发送失败。
- `replacement_sources`：新发行实际`driver_sha256`、`batch_sha256`、`ui_sha256`。
- `output_root`：同unit中新的`.general-e2e/queue-repairs/ID`目录。

只接受已登记的新建任务按钮缺失/原生错误边界准备失败：发送计数0，未armed/未返回，
Prompt为not_sent，无原生身份、baseline或已验证UI，且尚无public state/native binding。
恢复前复核初始Workspace全部成员、类型、模式与SHA；有漂移不恢复、不清理。
其他已发送任务须以原Driver取得可信终态，保持原attempt、Prompt和执行证据。

```text
node drivers/workbuddy/recover-queue.mjs --manifest NEW_MANIFEST_JSON
```

入口两次fresh native/UI空闲核验，验证旧与新发行代码及同一完整任务范围、题序、模型和并发。
它先持久化事务，排他归档原队列、原owner和零发送journal，保留原inode/字节和SHA；
不删除未知锁，不改Workspace，不改变已发送attempt。仅将已证明零发送的准备状态恢复为PENDING，
仍使用原attempt ID，后续journal和正式证据保留该题原失败与恢复证明。
新队列同时冻结execute、batch和UI源码SHA；恢复后的普通resume继续复核全部修复原件。

RECOVERED只代表控制状态可接续，不表示Prompt已发送或任务已完成。随后从清单指定的新发行、
沿原完整argv增加`--resume`接续同一queue。中断恢复须使用同一清单与`--resume`恢复事务；
任何未知owner、原件漂移、已发送、armed、不确定发送或其他失败都拒绝。

旧失败记录不纳入能力分，不补零；正式collect仍只消费一次发送且有可信原生终态的执行。
