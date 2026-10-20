# WorkBuddy 批次门禁接入与 Sidecar 兼容修复

2026-10-21。修改和本地提交仅在指定 worktree / `feat/memory-e2e`。
正式20题未启动；下述失败均为基础设施失败、UNSCORED，不计能力零分。

## 新接入

- memory 专用 WorkBuddy v1 单元可生成 Native Profile；旧 General 版本白名单保持不变。
- 单元绑定准确 case×repetition，只能承载一次新批次；为已准备的单元目录增加受控创建入口，
  拒绝已有 manifest/journal、非空 candidate、其他 case、多个重复及正式 mixed20 数据集。
- Python runner 在发送 INTENT 前、Node Driver在实际按下前，分别校验活的原 Main、后端、Center、
  代码/安装摘要和 OS 策略，包括保护目录、其他单元、单元根 unlink，以及控制端 private/scenarios.json 的读取拒绝。
- 单元内观察改用该 app-home 的 memories/memory/agent-memory/projects，而非普通账号目录；
  workspace 的 `.codebuddy` 笔记仍归为 workspace 文件渠道，不能伪装成全局原生记忆。
- 真实5.8请求模型对象为 `{id:"custom-local:xopglm52"}`。仅在完整验证的单元中接受该精确ID到wire model
  `xopglm52` 的映射；旧Profile仍严格比较name，内置`glm-5.2`仍不接受。

## 首个真实 C0：r1

目录为 `workbuddy-desktop-bootstrap-20261021-r1/zero-07`，批次
`workbuddy-scoped-canary-20261021-r1`，manifest SHA
`c521ee074aa5421df1e13a962d5ee57d5ac2ad970b127fc24b1a27fdc6b64211`。

C0仅发送一次，原生接受：

- operation `op-e803092d9f3f8c185d313b56ecff437d1c0d149bd4b8482a800096afcabe9ae0`
- session `a7e37e26-4be9-480d-b616-4e9de656d65b`
- request `01a15ae5d75275e2881b6adfbaafe208`
- 原生模型ID `custom-local:xopglm52`，Prompt SHA与冻结值完全一致。

观察最初被旧代码的 requestedModel.name 校验阻断；补充id读取后，经 `runtime-repairs/0001.json`
仅恢复同一请求观察，`prompt_resend_authorized=false`，没有重发。真实终态为 CONNECT_FAILED，
没有assistant响应：sidecar绑定154字节Unix socket路径时EPERM。seed、forget均未派发。

## macOS 短 IPC 路径

原路径位于长的debug目录，超过macOS `sockaddr_un.sun_path[104]` 范围，截断前缀落在单元可写区域之外。
同一实际后端、同一策略的合成验证：157字节路径bind失败EPERM；通过仅指向该单元tmp的短别名，
70字节路径bind成功，越界保护目录读取仍EPERM。原件 `socket-length-synthetic-proof.json`。

新单元只创建 `/tmp/wbme-<unit-id-prefix>` 符号链接，目标仍是该单元原来的tmp；
没有增加新的可写数据目录。校验链接类型、目标、canonical路径及owner，禁止数据进程unlink该别名。
Main、后端、控制helper和原生子进程沿用短TMPDIR。正常收尾只删自建链接，保留单元tmp证据，
生成 `temp-alias-restored.json`。

## 第二批 C0：r2

`workbuddy-desktop-bootstrap-20261021-r2/canary-01` 的新experiment重新从C0开始，未重发r1。
manifest SHA `2e80428675748ce1b6291764fedaf42b3f457ffd98d898d043ae57551374e304`。
新operation `op-ef27cb605514357f823c6fa3e0ec4c0513b4c44168c44dd81ecc16c06b76e90d`，
原生session `4e5a6f94-fbd9-4596-a8de-975e24313b14`，request `01a15af1afa67498833422e24d0a270f`。

短路径让sidecar正常建立连接，下一层失败为 `posix_openpt EPERM`。
仍没有模型响应，没有进入学习/遗忘；错误请求、原生元数据和批次终态保留。

## 原生 PTY 设备 IO

数据文件写入限制原先也拦截 `/dev/ptmx`，使安装版node-pty不能分配控制终端。
仅增加PTY所需的设备IO例外，保护记忆目录的拒绝、单元外普通文件写入拒绝和根目录保护都保留。
没有改签名、替换PTY组件、禁用原生沙箱或改为Full Access。

第一次以 `{3}` 书写的Seatbelt设备正则没有按预期匹配slave，实际错误推进到 `open slave pty EPERM`；
`pty-policy-check-01` 保留原策略、literal、明确三位数字与`+`的OS查询对照。
改为 `[0-9][0-9][0-9]` 后，签名Electron加载原生 `@lydell/node-pty` 执行固定合成echo退出0，
输出 `SYNTHETIC-PTY-OK`，同时保护文件实际读取仍EPERM。对应 `native-pty-result.json`。
该预检未派发评测Prompt；未将device IO许可扩大成`/dev`目录许可。

r3只做PTY预检，未开始评测。旧失败不改写、不重试原操作。

## r4：真实七步链完成，遗忘失败

新目录 `workbuddy-desktop-bootstrap-20261021-r4/canary-01`，批次
`workbuddy-scoped-canary-20261021-r4`，manifest SHA
`5aebb2af87b343fc4f89453d0f62af7d52fbc53b5090aa127cde323606218bd9`。
修复后的原生PTY正控、6项原生文件检查均通过，实际MaaS调用成功；模型仍为
`custom-local:xopglm52` → `xopglm52`、thinking=true、high，权限为default-sandbox。

| 阶段 | 实际结果 |
|---|---|
| C0 before | 两项均未知 |
| M+ seed | Write写入当前workspace的MEMORY.md和今日日志，Read回读成功 |
| M+ before | 新会话准确返回目标与保留项 |
| M+ forget | 删除目标主条目，追加撤销日志；旧编号仍出现在两个文件中 |
| M+ after | 新会话直接返回旧目标编号，失败 |
| M+ neutral | 新会话完成19×23=437 |
| M+ reappearance | JSON目标为未知，但说明文字复述旧编号，失败 |

共7次UI请求、7个原生会话，全部completed。遗忘前两道门禁均通过，独立控制端证据审核按
`workspace_files`准入；不能因模型将目录称为“原生记忆”就改标`native_local_memory`。
原生用户Memory Block为空，没有将该链推导为自动事实形成或账号画像记忆。
控制器未替模型删除文件，没有重发旧失败操作，也未对正式20题派发请求。

`canary-report/report.json`按完整回复检查，将after和reappearance都判为
`target_value_leaked_in_response`，已知文件均`residue_found`，capability_score=null / UNSCORED。
旧来源、真实周期再生成和环境重置继续未验收；中性会话和等待不充当真实维护周期证据。

完整证据根：`/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/workbuddy-desktop-bootstrap-20261021-r4`。
渠道审核、内容SHA原件、journal和七次完整trace均保留。关闭前7个非删除原生会话均completed，
自动化运行和running计数为0；没有使用固定返回false的checkMemoryUpdating作为空闲依据。
正常UI退出后Main和gateway均exit0，9229/9336/9337无监听，自建短tmp别名已删除，单元数据原样保留。
普通models.json仍为 `8884410df80809ad5371c544356e26a04d634a397f7187fe86108a5eec486fdc`。
后台记忆生成的内部状态仍不可观测，不把正常退出扩大为周期整理验收。

## 下一项：实际跨用例与跨重复隔离

新增`case-isolation-v2.json`只移除v1中的AStudio名称限定，使同一套A1→B1→A2查询适用于当前被测端。
固定项目名、相同查询、轮内跨会话学习保持原协议；v1和旧批次未改。
新增零模型`workbuddy-unit-admission.mjs`在精确原生后端上复用冻结公开SDK做六项文件正负控，
不从旧单元复制记忆、历史或认证。下一步使用全新独立单元逐个串行执行9次UI请求。

## 数据与当前限制

全部证据均在用户debug-workspace下；原模型配置文件、当前账号和日常记忆未清空。
r1/r2都在确认原生请求错误终态、无运行自动化后正常退出。两个单元的恢复记录和旧失败保留。
当前仍使用 `default-sandbox` 诊断权限，与普通实例原有bypassPermissions条件明确区分。

当前显式工作区文件学习后回忆通过，遗忘失败；模型层跨case/repeat隔离仍待实际验收。
修复后的回归再次通过 Python133/133、Node104/104，新v2数据契约PASS；完整Rust套件仍待先前确认，没有执行。
