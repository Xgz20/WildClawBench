# MAC-DOUBAOWORK-WEB-002：COMMON-002 接收与开发 canary 更正

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../general-e2e/README.md) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 创建时间 | MAC-DOUBAOWORK-WEB-002 / 2026-09-19 20:25 +08:00 |
| 来源任务 / 目标任务 | MAC-DOUBAOWORK-WEB / COMMON |
| 与前序交接关系 | `MAC-DOUBAOWORK-WEB-001` 已被消费并保持原样；本文件是增量接收与事实更正，不重写历史交接 |
| COMMON-002 基线 | `SYNC_SHA=46a23a43572aed34bc2eec457d67423e2bce08af`；必需源码 `eb23784a7ed25b0f0364db0392783de277b22b96`；本任务 merge `ca7cc2ed74e3c8bb148ccd702c385f1ba8f62cb9` |
| 平台代码交付 | canary 事后提交 `47dcaee8279309202ebdcabf40cf4777fe758b3c`；它不是精确 live Driver revision |
| 状态 | LOCAL_ONLY；canary `NEEDS_ATTENTION`；`SLOT-MAC-20260919-01` 已释放；未 push、未合主分支 |

## 更正结论

本次开发 canary 只实际发送一次，且 UI conversation 与 native session 已唯一绑定。候选站点及两张截图实际存在；早先“workspace 只有 `.gitkeep`、未生成站点”的记录错误，现已更正。

站点存在不等于执行成功：native `terminal.status=unverified`、`native_cwd=null`，候选服务进程组在只读复核时仍存活，且没有正式 execution record/receipt、score 或 report。因此 canary 继续保持 `NEEDS_ATTENTION`，不能进入评分或生产准入。

## 输入包、live Driver 与事后源码边界

| 层次 | 可确认身份 | 证据边界 |
| --- | --- | --- |
| prepared input / Skills 包 | `source_revision=c098a2e386baec6b04ed4af615349bea974f0746`；execute 1.13.1、run 1.4.1、orchestrate 0.3.1、score 4.5.4、report 1.1.1 | 这是输入包的确定身份，不是 live Driver 源码身份 |
| live Driver | automation state 只记录 `driver.version=0.3.0`；仓库 base 为 `c098a2e...`，其上存在未提交的多轮 Driver 迭代 | 没有归档运行时 Driver 文件哈希或 dirty diff，`source_revision=null`；精确 live 代码快照未冻结 |
| 事后交付 | `47dcaee` 提交 Driver、测试和 canary 索引 | 包含 live observation 后追加的唯一 observation 文件名校验和 pre-send retry 项目身份校验，不得反向冒充精确 live revision |
| COMMON-002 接收后当前分支 | discovery 1.2.0、execute 1.14.0、run 1.4.2、orchestrate 0.3.2；prepare 4.4.0 已支持 `harness=doubaowork` | 属于 canary 后采用的当前代码，不追溯改写 canary 身份 |

## canary 证据与现场

- 唯一实际发送计数 `dispatch_attempt_count=1`；Prompt SHA-256 `04816a6c...c29f`；模型“自动 高”；权限“按需确认”。UI conversation/native session 哈希均为 `a672e6e3...3709c`。
- 11:47:06Z 最新有效 UI observation 的 busy/stop/dialog/question/approval 均为 0，DOM 回复候选 1,893 字节、SHA-256 `2e3157e...25e78`。live revision 复用了固定文件名，最新回复和截图没有唯一原件；旧 `ui-final-reply.txt` 只有 145 字节，不能冒充最新证据。
- 已绑定 native snapshot SHA-256 `5a4d03af...8f803`，有 29 个事件、14 个工具调用 known subtotal；coverage denominator 为 `null`。轨迹包含指向候选 workspace 的 Bash 建目录和 Write 写文件，但不提供可信 terminal/cwd。
- 20:11:13+08:00 只读文件复核确认 4 个普通文件、0 个符号链接、0 个已知禁止运行时目录：`.gitkeep` 0 字节；`countdown/index.html` 18,216 字节，SHA-256 `b43018a6...8f36d`；桌面截图 51,639 字节，SHA-256 `f07eafe4...f647`；移动截图 51,491 字节，SHA-256 `5020624a...ad2c`。HTML mtime 晚于截图，且没有正式 provenance，不声称截图对应当前 HTML。
- 20:20:10+08:00 只读进程复核确认同一进程组内的 DoubaoWork sandbox Bash/Python 两个进程仍以 `workspace/countdown` 为 cwd，其中 Python 监听 TCP 8848。没有终止进程或修改候选，cleanup 未通过。
- 仓库内脱敏索引见 [canary-slot-mac-20260919-01.json](../../../web-e2e/evidence/doubaowork-macos-web-e2e/canary-slot-mac-20260919-01.json)，完整边界说明见 [DoubaoWork canary 证据](../../../web-e2e/evidence/doubaowork-macos-web-e2e/README.md)。

## COMMON-002 已采用项

- `46a23a4...` 与 `eb23784...` 均已核验为当前 HEAD 祖先；合入无冲突。
- desktop-app-discovery 1.2.0 已包含 DoubaoWork macOS Profile；真实安装只读核验返回 `identity_verified=true`，应用为 `/Applications/DoubaoWork.app` 2.28.12，Bundle ID `com.work.pc.doubao`。
- prepare 4.4.0 已识别 `harness=doubaowork`。该项与 discovery 不再列为公共缺口。
- COMMON-002 的 General trace v2 / finalizer wire 对 Web Driver 不适用，不能据此生成 DoubaoWork Web 正式回执。

## 剩余接收动作

| 接收方 | 要求 | 通过条件 | 当前失败关闭 |
| --- | --- | --- | --- |
| COMMON / Web metrics | 注册显式 conversation/session 绑定的 DoubaoWork trajectory adapter，保留 null、known subtotal 与 unknown denominator | parser/collector fixture 不把缺失写零，不把 partial 升级为总量 | 不回填正式资源指标 |
| COMMON / Web finalizer | 支持 nullable native identity、多 artifact provenance、可信 terminal/cwd 判定与正式 receipt | 缺 terminal/cwd/cleanup 时拒绝 `integrity.valid=true`；最新 UI artifact 必须唯一归档 | 保持 `NEEDS_ATTENTION` |
| 平台 Driver / cleanup | 按已绑定 session 和完整 cwd 精确枚举、验证并清理候选进程 | 不按 DoubaoWork/Node/Python 名称宽泛终止；残留为零并有来源证据 | `supported=false` 或残留均阻断正式收口 |
| Web execute/run/发行 | 增加 `run-doubaowork` 入口、macOS application 路由、默认 `ui_slots=1/run_slots=1`、构建与发行清单 | layout/build/脱仓测试通过；全新批次从 probe 与单题重新验收 | 不声明生产执行或发行可用 |

## 验证与后续边界

当前代码通过 DoubaoWork Driver 39/39、共享 discovery 3/3、prepare 33/33、Web Skill layout 4/4，以及六个 `.mjs` 语法、Swift typecheck、JSON 解析和 `git diff --check`。这些是源码/离线验证，不替代本 canary 的可信终态或正式闭环。

本次只读复核后不再连接或操作 DoubaoWork UI，不修改候选，不终止残留进程。若未来另行批准新批次与独占时段，只验证已补齐的 terminal/cwd/cleanup、唯一 artifact 和正式 finalizer 边界，不重复本次 Prompt。
