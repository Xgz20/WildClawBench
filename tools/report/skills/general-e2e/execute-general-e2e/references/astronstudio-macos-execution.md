# AstronStudio macOS 单题执行契约

## 适用范围

`scripts/execute_astronstudio_macos.mjs` 接收一个已解压的 General E2E execution unit、一个完整 task ID 和 G2-01 冻结运行配置。它完成单题 Prompt 一次发送、`thread_id / turn_id / session_id / cwd` 绑定和原生终态观察。

当前实现不负责任务级超时停止、候选冻结、轨迹归档、资源采集、评分或报告。题目 metadata 的 `timeout_seconds` 只作为数据集兼容字段，不参与被测 Harness 的执行 deadline；执行状态中的 `execution.deadline_at` 固定为 `null`。`--timeout-ms`、`--identity-timeout-ms` 和轮询间隔只服务于 CDP/UI 操作、网络探测和发送后身份绑定。串行批量由 [macOS 队列入口](astronstudio-macos-queue.md) 调用本执行器；采集与正式回执由 `collect-general-e2e` 负责。执行器输出的 `execution-record.json` 因此固定为 `evidence.completeness=partial`、`candidate.drift_status=not_frozen`、`resource_metrics_path=null`，不能直接作为评分准入回执。

## 调用

```bash
node scripts/execute_astronstudio_macos.mjs \
  --unit-root /absolute/extracted-unit \
  --task-id 02_Code_Intelligence_task_001_temperature_cli_fix \
  --run-config /absolute/astronstudio-macos-run-config.json
```

恢复同一 attempt：

```bash
node scripts/execute_astronstudio_macos.mjs \
  --unit-root /absolute/extracted-unit \
  --task-id <完整任务ID> \
  --run-config /absolute/astronstudio-macos-run-config.json \
  --resume
```

输出位于 `<unit-root>/.general-e2e/execution/<task-id>/`：

- `automation-state.json`：遵循 [execution state schema](astronstudio-execution-state-v1.schema.json)；
- `execution-record.json`：遵循仓库 `general-e2e execution-record v1`；
- `final-response.md`：原生终态可取得最终助手回复时写入；
- `driver.lock`：仅在 Driver 进程存活期间存在。

## 一次发送与恢复

1. 校验 execution manifest、Prompt SHA-256、冻结配置 digest、客户端版本、模型、推理强度和权限。
2. 新建空白任务并按绝对路径选择 execution task 的 `workspace/`。
3. 填入 Prompt，保存 workspace 原生会话基线、路由 thread 和 `intent_persisted`；随后把 `dispatch_attempt_count` 原子地固定为 `1`。
4. 只调用一次发送动作。发送返回后记录 `sent_at`；连接在临界点断开时，先用已保存的 route/baseline 查询原生状态库。
5. 只有唯一匹配的 cwd、route thread、新 turn 和 provider session 同时存在时才确认发送。否则写 `uncertain / NEEDS_ATTENTION`，恢复不得再次调用发送动作。
6. 恢复只观察同一 `attempt_id` 和已绑定身份。原 thread 出现其他 turn、身份不唯一、未知状态或待授权/待用户输入时均进入 `NEEDS_ATTENTION`。

`0.11.25` 在发送点击前同次回读唯一可见的 Prompt、完整 Workspace、无遮挡发送按钮和未知对话框数量；点击改为 CDP 鼠标移动/按下/释放事件。点击动作返回不代表客户端已受理，仍以原生 thread/turn/session/cwd 为准。校验失败或发送后无原生身份都保留一次发送意图并暂停，不自动补点或重置计数。

`0.11.26` 只对编辑器自动生成的 `role=link / contenteditable=false` URL chip，在冻结 Prompt 中按 DOM 顺序找到完全相同的 `http(s)` `title`，用 chip 的可见文本重建期望显示值；正文其他字符仍要求完全一致。发送前的同次回读与填入后的回读使用同一规则，缺失 title、未知协议或不一致均失败关闭。超时诊断只记录长度与 chip 数，不再输出完整草稿文本。

`0.11.27` 发送前还要求当前目标 thread 的本地 `server.log` 中有未释放、持续至少 1.5 秒的精确 `orchestration.thread:<thread-id>` 流租约。按目标 route 和 attempt 创建时间过滤结构化 `admitted/released` 事件，不把其它订阅的 active lease 列表当作该 thread 的准入。最多只读等待 120 秒；未取得正证据时在发送意图落盘前失败，`dispatch_attempt_count=0`，不点击按钮。此门禁不替代发送后的原生 thread/turn/session/cwd 绑定。

`0.11.28` 在发送意图落盘前先移开项目预览悬停卡片，并按唯一 Prompt、Workspace、弹窗和发送按钮无遮挡回读目标。此时未就绪属于发送前失败，`dispatch_attempt_count=0`；只有通过该检查后才持久化一次发送意图。落盘后的最终点击仍重新检查目标；若此时出现竞态或断连，保留 `PROMPT_SEND_UNCERTAIN` 且绝不补点。项目本地显示别名不改变 Prompt 或 Workspace 身份。

`0.11.29` 对“项目已创建但当前对话仍留在其他 Workspace”增加发送前回读：仅在项目选择控件缺失时，用状态库中完整 Workspace 唯一查得 project ID，打开该项目侧边栏的唯一“新建对话”按钮；新路由必须空白、可见路径必须精确等于目标 Workspace，原生 thread→project→cwd 也必须一致。任一步失败保持零发送并留基础设施错误，不把项目 basename 或本地显示别名当路径证据。

`0.11.30` 对项目导航与路径控件异步出现的竞态补充二次回读：若目标完整路径已经在当前空白路由可见，且原生 thread→project→cwd 唯一一致，则直接接受当前路由；点击目标项目“新建对话”后即使路由 ID 不变，也只在相同 UI 与原生身份门禁通过时接受。没有正证据仍在发送意图落盘前停止。

`0.11.32` 在发送前读取当前及轮转的 `server.log.1/.2`，按事件顺序核对目标 thread 的流租约；读取期间若日志轮转则重新取一致快照，不能因租约事件刚被轮转而误判为未获准。

`0.11.31` 在项目选择列表找不到目标 Workspace 后，先用 Escape 关闭选择菜单，并新鲜确认没有可见 dialog/option，再操作侧边栏的“添加项目”。若菜单未关闭，发送前失败，不在遮挡层下点击添加入口或意外触发 macOS 原生目录选择器。

状态查询只读取主状态库的临时副本及同批复制的 WAL/SHM，不写源库。AStudio 热写入导致副本 `quick_check` 或查询短暂失败时，单次查询先退避重试；Prompt 已发送并绑定身份后，终态轮询继续保留同一 attempt 重试，不因此创建新任务或再次发送。`--resume --observe-once` 仍只尝试一次上层观察；该次读取失败会持久化 `NATIVE_STATE_READ_FAILED / NEEDS_ATTENTION`，可再次恢复。

执行锁遗留时，只有 `--resume` 且记录的 PID 已不存活才允许清除陈旧锁；普通新运行不会接管锁。单题 Driver 同时持有 unit 级 `astronstudio-ui.lock` 和 task 级 `driver.lock`，因此即使绕过队列直接启动多个单题入口，也只有一个进程可以操作 AStudio UI。

发送前 Driver 失败会写 `FAILED / infrastructure_error / not_sent`，该 attempt 保持终态，`--resume` 只回读而不会在原 attempt 补发。修复环境或 Driver 后，应保留失败状态作为证据并从新准备的 execution unit 创建新 attempt；不得删除状态后把后续发送伪装成同一次执行。

## 终态

`projection_turns.state=completed` 是可信成功终态，不要求 workspace 必须发生变化，因此纯回复任务也能完成。`error/failed` 映射为 `infrastructure_error`，`interrupted/cancelled` 映射为 `cancelled`。执行器会持续观察到可信原生终态或需要人工关注的状态，不会因为题目 `timeout_seconds` 到期而停止被测 Harness；可信停止、静默窗口、任务进程收口和 `timeout` 候选冻结属于采集/故障处理契约，而非题目执行 deadline。

退出码：

- `0`：`COMPLETED`；
- `4`：已发送并绑定身份，当前仍为 `RUNNING`（通常来自 `--detach-after-submit`）；
- `3`：`NEEDS_ATTENTION`；
- `2`：参数、输入、执行失败或原生失败终态。
# 原生启动前拒绝的显式收口

Execute 0.14.47 / Driver 0.4.19 提供 `--resume --observe-once --resolve-native-start-rejection`。此动作不是重试或取消：只有原生用户消息精确匹配冻结 Prompt、原项目/模型/权限、accepted 命令回执和唯一启动事件，并且原生活动明确 `provider.turn.start.failed`、`rejected / not-sent / preparationTerminal=true`、投递 `succeeded / not-submitted-v1`，才接受原生 ACode 20 秒提交超时为 FAILED/candidate_error。必须没有 turn、待交互、queued promotion 或 open turn，预热运行时已停止。原状态及执行记录按字节保存在 `native-start-rejections/`，连同完整同快照读取和 proof 引用；原 attempt 和一次发送计数不变，模型 turn/session 身份不补造。未知发送、额度耗尽、其他启动错误或活动矛盾不适用。收口本身不赋分，评分仍由既定评分入口及明确政策决定。

Execute0.14.49 / 启动拒绝组件1.0.1另支持`bound-native-unsubmitted-start-rejection-idle-prewarm/v1`：只允许明确emptyPrewarm=true、activeTurnId/lastError/emptyPrewarmDispatch都为null的空闲ready/running预热运行时，仍满足原拒绝及全部无turn/待派发门禁，不关闭连接、不重启或重发。若较早的ready投影覆盖失败，只在该投影时刻严格早于失败、原生error session事件与失败activity均有同快照accepted回执及精确指纹时采纳原拒绝；保存ready投影及stale标志。仅有ready、未结算或未知活动不能确认失败。额度通知允许原生单层rateLimits包装，但只有全部额度指标明确null才作为未知通知接受；已知耗尽或未知形状拒绝，不能以故障计零绕过额度停机政策。

Execute0.14.50 / 启动拒绝组件1.0.2保留同生命周期的空预热session connecting/ready及acode_apps 30秒启动失败事件，逐项验证原生thread、lifecycleGeneration、providerThreadId、原始方法/状态/错误；这些连接初始化行不是模型工具轨迹。它们与明确not-submitted的原拒绝共同封存，不删行以绕过门禁，不修改Harness的MCP配置或超时。任何turn/item/content事件、外来生命周期、实际活动turn或未结算请求继续拒绝。

Execute0.14.51 / Driver0.4.20对精确原生终态后重开的用量账本增加只读闭合核验：SQL最新head已completed/error/interrupted、无active/pending，runtime已stopped且原生turn.completed或后续provider.stopRuntimeSession对同一闭合时刻成立；同turn/provider身份的重开tail只能含typed token/gateway usage，时钟和序号均闭合。完整历史事件与计费数据不删除；原provider终态已被客户端消费/清理时，只接受剩余完整typed资源行，不重构终态。任何模型动作、未知状态/身份、未停止runtime或待交互仍阻塞；无项目的活动会话不会被INNER JOIN漏掉。该修复不更改模型/Prompt/槽位/重试策略。

Execute0.14.52 / Driver0.4.21允许显式托管零发送准备恢复与精确已登记同伴共存：保留原失败SHA与attempt，目标无发送意图/接受/会话，活动同伴的session均在队列allowlist且总数低于冻结槽数，没有未知发送；单槽或外来活动仍拒绝。该动作不会刷新页面/重启/停止同伴。添加项目表单只有完整路径精确属于本任务、没有弹窗且唯一取消控件时才关闭并重建；其他路径、Prompt和未知草稿不动。

## 人类明确授权的未受理发送恢复

Execute0.14.55 / Driver0.4.22的`recover_astronstudio_dispatch.mjs --unit-root ABS --run-config ABS --authorization ABS`只准备新attempt，不发送Prompt。授权schema为`general-e2e.unaccepted-dispatch-retry-authorization/v1`，冻结原队列/状态/记录/初始目录/manifest/config摘要、独立新UUID和直接人类原话路径/SHA。人类须明确清理并重试该题；既有中断0政策、自动生成建议或未回答问题不适用。

入口持有原队列及UI锁；同快照原路由仅允许已结算创建/元数据命令，无原生消息、turn、session、interaction、promotion、open turn或provider事件，且全局真正空闲。模型/权限/cwd/完整Prompt不得漂移。原Workspace须与冻结初始树相同，旧state点击计数1与uncertain原字节、完整控制和Workspace封存到独立不可变ZIP。只清精确旧草稿，再次证明无迟到受理后生成PENDING新attempt，保留旧新身份/授权/归档闭包，随后普通队列`--resume`首次发送。重复恢复已准备事务只验证原新attempt，不重新清理或发送；已有原生接受或其他命令继续拒绝，观察原尝试。

0.14.56仅对已有canonical CWM-only审计确认的初始Office属性差异增加准入：实际路径、类型和权限须完全相同，原execution ZIP与manifest和全部业务OPC成员保持原SHA契约。原/现Office字节和比较清单纳入旧attempt封存ZIP，回执显式记录该Profile；不删除标记或改输入。非Office变化、增删文件或业务内容变化仍失败。

0.14.58的派生应用必须同时保存原“框架故障可独立重试”持续指令和原“未送达属于框架发送故障”的人类界定，两份原件路径/SHA、原question ID、原context task均不改。应用schema为`general-e2e.standing-framework-retry-application/v1`，`derived_application=true`，只作用于当前明确绑定task/old attempt及`no-native-prompt-acceptance-owned-draft-restored`边界。CLI和回执标明是控制器对既有授权的应用，不是假冒人类为每题再次答复。任何已受理消息/turn/未结算投递、非本题草稿或活动模型仍不适用；不是自动把未知评分补0。

0.14.60 / 组件1.0.4另用`bound-native-unsubmitted-start-rejection-idle-bootstrap/v1`记录直接初始化连接：cursor只能有threadId；runtime payload字段范围、generation、model/options、cwd、full-access/provider/adapter和显式null activeTurnId/lastError/contextRecovery逐项匹配，无emptyPrewarm或emptyPrewarmDispatch声明不补值。原生精确Prompt/accepted request/明确rejected/not-submitted已结算、零turn/open/promotion/interaction、同快照原生error事件及accepted指纹仍必须闭合。它不是旧empty-prewarm Profile，不能由缺SDK文件或ready文字单独推出无模型或成功。未知动态字段、活跃turn、pending及矛盾来源继续拒绝；所有原行和部分覆盖原样保留。

0.14.61的已知草稿清理在原文/route/唯一editor及无dialog复验后，用原生编辑器selectAll和Backspace，不用DOM Range充当受控编辑器的内部选择。完全空白/无chip/同route须连续稳定回读；只按一次删除，不对残留或未知文本重复按键。未受理授权恢复先写cleanup-intent（原auth、route、完整ui-before摘要），只有该意图/归档及新鲜无受理/原生空闲全部闭合时才可接收已空但回执未完成的清理结果；旧原话及发送计数不改。没有意图的部分残留须保留并人工/控制器核验精确原文后处理，不自动丢弃。
