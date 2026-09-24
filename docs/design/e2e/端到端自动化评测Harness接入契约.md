# 端到端自动化评测 Harness 接入契约

文档标识：`E2E-HARNESS-CONTRACT`；版本：`0.3`；状态：现行接入与验收基线（人工符合性审核，统一自动校验器尚未实现）；更新：2026-09-23。

适用对象：接入或升级桌面 Harness 的开发、验证与发布人员。包含本地执行的 General 与 Web 站点两个场景，按声明的 OS/架构与实际客户端能力验收，版本作为证据身份记录。当前状态按第 5 章逐项绑定源码/发行/平台证据；文档重组不改变任何运行身份。

本文是 Web 与通用场景共用的唯一集成契约，维护 Driver 控制能力、具体集成步骤、场景差异、验收要求及各 Harness 进度。Driver 的创建任务、Workspace 绑定、配置回读、一次发送、观察、停止与恢复遵守同一套控制规则；数据包、证据交接、评分和报告差异由场景策略/adapter 表达。

当前 Web/General 的 CLI 与回执 adapter 仍分别存在，公共底层通过 `tools/report/e2e-shared/` 装配。共享控制段在相同实现与运行身份下可引用既有证据；场景的数据包、采集 adapter、评分和回执闭环分别验收。本次整理不改运行代码。技术架构和轨迹分析分别见 [Web 技术方案](../web-e2e/Web站点端到端自动化评测技术方案.md)、[通用技术方案](../general-e2e/通用场景端到端自动化评测技术方案.md)；字段和公式见各场景指标说明。

阅读顺序：[共用要求](#1-共用契约) → 对应场景差异 → [集成步骤](#integration-steps) → [当前进度](#integration-progress)。导航见 [README](README.md)，旧计划、ADR、验收台账与协作文件已归入 `archive/`，不再各自维护“当前进度”。

0.3 将文档职责、集成步骤和各 Harness 当前进度统一到本文；保留 C/G/W/CV/GV/WV 编号与既有验收门槛，不新增协议或运行结论。此前 0.2 把加固明确纳入每个新 Harness 集成任务的必需范围：第 1.9 节维护共用 CV 验收项，第 1.10 节提供任务模板和完成条件。不得另挂为可省略的“以后再加固”任务。已有证据保留当时契约/源码身份，本次文档更新不自动升级或撤销已有有限范围结论；未覆盖的新要求进入对应 Harness 的待办，不填为已通过。

## 1. 共用契约

### 1.1 维护方式、适用范围与变更规则

**C01｜每个接入声明都必须可核验。** 每项要求记录“适用性、实现位置、验证方法、结果、证据、限制”，不能用“已加固”“支持 CDP”“单测通过”代替完整接入结论。既有验收 ID 不重编号，建立到本文 C/G/W 要求的映射即可。

| 资料 | 维护内容 | 不应重复维护的内容 |
| --- | --- | --- |
| 本文 | 跨场景 Driver 控制规则、集成步骤、场景差异、验收门槛、各 Harness 当前进度与下一步 | 完整原始轨迹、逐批运行日志和所有历史包 SHA |
| 场景 Schema / 实现接口参考 | 精确字段、枚举、版本兼容、接口与命令 | 另起一套同名但不同语义的字段 |
| 场景技术方案 | 架构、数据流、轨迹采集与归一化分析、实现入口 | 第二份接入步骤或当前进度表 |
| 场景指标说明 | 指标定义、公式、原生字段映射、覆盖和报告解释 | 第二份 Harness 集成状态 |
| evidence / archive | 前者保留运行事实与原件索引；后者保留历史方案、台账和决策 | 作为当前调度指令或覆盖本文件第 5 章 |
| README | 导航和文档职责 | 滚动进度、版本及待办副本 |
| 用户指导手册 | 已支持版本的安装、运行、恢复和交接操作 | 开发状态、故障注入历史、内部阻塞清单 |

“必须”是声明对应能力的条件；“不适用”必须有场景或能力依据；没有做完的项目记录待验证，不能填不适用。可选资源字段不可用时允许降级；任务评分所必需的轨迹、身份或候选证据缺失时，按场景契约阻断相关评分。

**C02｜分别冻结版本与范围。** 至少登记 contract 文档版本、数据集 ID/digest、场景协议/Profile、源码 revision、Driver 与采集器版本、Skill 内容/ZIP SHA、共享组件 SHA、依赖锁、OS/架构、客户端安装身份和版本、执行模式、被测模型/推理/权限、评分模型/协议。不得用一个“v1”替代全部身份。

本稿对现有格式是上层约束，不能向严格 v1 Schema 任意塞入新字段。新增可选字段须验证新旧读取器兼容；改变分母、单位、状态含义、必填性或评分语义，须发布相应新版本并写迁移说明。历史结果只读复核或经显式迁移生成新产物，不覆盖原始记录。

客户端版本是兼容性元数据，不设精确版本白名单；按实际能力与字段/UI 行为核验兼容性。客户端、控制端、关键 Driver、解析器、运行时或平台变化后，受影响证据标为待复验；至少复核 probe 和一个完整闭环，再按影响补验恢复、并发或指标。仅文字变更且相关内容 SHA、环境身份未变，可记录证据沿用理由。精确运行时 Profile 未覆盖的版本不自动继承 Token 口径。

### 1.2 开发分层与接入流程

**C03｜公共机制单一来源，场景策略显式注入。** 不复制另一 Harness 的整套流程后各自修补。当前共享组件入口为 [components.json](../../../tools/report/e2e-shared/components.json)，已登记应用发现、桌面进程、调试重启、资源解析、Workspace 完整性、分发校验和评分 core 等组件；目录中没有的通用接口不能当作已经实现。

| 层 | 职责 | 新 Harness 的工作 |
| --- | --- | --- |
| 应用与平台 | 安装发现、进程/CDP 身份、启动、重启、原生目录选择、精确清理 | 增加安装 Profile 和平台适配；非 Electron 客户端不强制要求 `app.asar` |
| Harness Driver | 创建任务、绑定 Workspace、配置回读、一次发送、观察、停止、原会话恢复 | 实现客户端专属 DOM/原生控制与原生状态映射 |
| 证据与指标 adapter | 原始归档、标准事件、usage、调用结果、计费结算 | 提供字段语义、去重、范围、完整性与版本 Profile |
| 场景策略 | 数据集、产物策略、评分准入、评分和报告协议 | 选择 General 或 Web；不向 Driver 写入 rubric 或得分逻辑 |
| 控制与发行 | 持久化队列、UI 锁、并发调度、交接、Skill 装配与升级 | 复用已存在能力，声明新增能力边界和分发依赖 |

实施顺序：先冻结本轮范围并展开 C/G/W 与全部 CV 验收记录，再做能力盘点 → 只读 probe → 单题发送/观察/恢复 → 原始轨迹与指标 → 冻结与正式回执 → 评分/回传/报告 → 小批与仓库外发行。加固随所属模块一起实施和验证，例如发送入口同步覆盖 CV03–CV05，收口同步覆盖 CV09/CV13；不拖到客户端能跑题后才补任务范围。并发与无人值守按声明层级另验。仅完成部分阶段时声明阶段可用，不能把主路径能运行写成集成全部完成。

当前在当前工作区分支串行实现 Harness adapter、fixtures 和验收证据。公共 Schema、指标公式、队列语义与发行仍保持单一来源；公共变更运行受影响回归，不要求平台 worktree 或派发/回收流程。

共享变更在当前接续记录中注明实现 SHA、兼容影响和受影响旧证据，直接完成必要回归；无需另建交接文件或等待接收方。代码集成、远端发布与目标平台验收分别记录，不能互相代替。

### 共用控制与场景差异速查

| 层面 | 共用部分 | General 场景 | Web 场景 |
| --- | --- | --- | --- |
| Driver 控制 | 应用/端点、唯一控件、Workspace、配置、一次发送、观察、停止、恢复、精确进程清理 | 由 General prepared unit/adapter 提供参数与输出映射 | 由 Web prepared task/adapter 提供参数与输出映射 |
| 数据与候选 | 公私材料隔离、冻结身份与哈希 | 文件和纯回复；按任务保留 Git/二进制/受限链接 | 网站候选；Web `.git`/运行时目录策略 |
| 采集交接 | 原生来源、去重、覆盖、未知不补造 | 独立 collect-evidence、正式 raw/标准 transcript、trace-index v2 与 receipt | 终态 execution record、Web collection/provenance 与 execution receipt |
| 评分 | 独立评分 attempt、候选保护、错误与真实性区分 | 原规则 + 指定语义后端，按 automated/hybrid/llm_judge | Browser 交互取证，按详细/ArtifactsBench Profile |
| 报告 | 原件可复核、哈希与分母披露、指标来源状态 | valid/evaluation_error/unscored，有效均值 | 保留已发布 Web 分数/异常零值规则与独立美观度 |

场景决定输入包、产物、评分和序列化，不为同一 Harness 另定义一套 UI 发送/恢复规则。当前两条入口已有的实现差异须在能力映射中登记，不能靠统一文档宣称代码或准入已经等价。

### 1.3 身份、运行配置与任务隔离

**C04｜稳定身份优先于 UI 猜测。** 概念主键至少包含场景、batch、unit、完整 task ID、execution attempt；另绑定原生 session/thread/turn、Workspace 完整绝对路径和必要的进程生命周期身份。现有 Web 格式没有的概念通过场景映射表达，不凭目录 basename 补造字段。禁止按最近任务、标题、修改时间、当前页面猜测归属。

新 attempt 必须与旧 attempt 分开；执行重跑和评分重跑是两类不同尝试。恢复沿用原 attempt、deadline、原生身份和队列配置。报告既保留冻结任务全集，也明确选定 attempt；全部尝试的消耗另设统计范围，不能因最后一次成功而丢失前次失败消耗。

**C05｜执行环境与评分环境隔离。** 本地任务明确选择客户端“本地电脑/本地项目”等等价入口并回读实际目录，不能误选云电脑。任务 Prompt、初始素材与私有 rubric、GT、grader 分开分发；控制状态、锁和评分文件放在候选 Workspace 外。目录分开不等于 OS 安全沙箱，应明确实际可访问边界。控制端不得给被测 Agent 补答案、代做题目或用评分材料纠正候选。

**C06｜配置可回读、可拒绝漂移。** 记录请求配置与实际配置。显式模型模式要求实际值匹配；保持当前模型模式允许未请求具体值，但必须回读非空 UI 值。底层自动路由模型不可验证时明确 unknown，不能把显示名当作不可变模型版本。推理强度、权限模式、适用的基础设施/评分时限、UI/执行/评分槽位都冻结；恢复时配置漂移应拒绝或创建明确的新运行，不能静默接受。General 题目 `timeout_seconds` 只保留元数据，不转为 Harness 执行期限或评分条件。

### 1.4 Driver 的能力契约

**C07｜能力名称允许不同，审计结果必须等价。** 当前 Web 接口与状态详见 [Driver 契约](../../../tools/report/skills/web-e2e/execute-web-e2e/references/driver-contract.md)；General 的现有状态契约见 [执行说明](../../../tools/report/skills/general-e2e/execute-general-e2e/references/astronstudio-macos-execution.md)。新 Driver 必须提供以下能力及映射表：

| 能力 | 必须保存的结果或失败行为 |
| --- | --- |
| `probe` | 客户端/平台/后端、依赖与权限状态、终态和日志来源；只读，不发送 Prompt、不顺便重启 |
| `launch/connect` | 唯一目标应用与控制页面；复用前校验实际进程身份，不能连接任意可用调试端口 |
| `createTask` | 本题全新任务与创建前后证据；选择器不唯一则停止 |
| `selectWorkspace` | 完整路径或可验证稳定标识回读；同名不同目录必须可区分 |
| `configurePermissions/selectModel` | 请求/实际值、匹配结果、UI 证据；无授权不提升权限 |
| `submitPrompt` | 发送前持久化 attempt、原始/发送 Prompt SHA 与意图；发送后捕获稳定原生身份 |
| `inspect` | 运行、可信正常/异常终态、待用户交互、未知；原生字段到业务状态的映射与来源 |
| `handleExpectedApproval` | 仅限已授权策略内的精确白名单，记录匹配规则及命令哈希；未知交互转人工 |
| `stop` | 只停止目标 attempt，记录请求与客户端确认；点击停止不等于已经停止 |
| `resume` | 查询原 session/turn，确认已发送后仅观察；身份不明不重发 |
| `collect/finalize` | 最终回复、轨迹、资源、候选快照、任务进程收口和正式回执 |
| `cleanup` | 只处理本题受管进程/UI/runtime 副本；不删除或修复候选 |

**C08｜发送采用持久化意图和失败关闭。** “意图已写入但不知道是否已发送”是必须覆盖的故障窗口。恢复先查原生会话；无法唯一确认时停止新发送。禁止看到缺少 `PROMPT_SENT` 就再次点击。单次发送不代表任意崩溃下存在平台级 exactly-once 保证；无法证明时牺牲自动继续以避免重复。

正常结束后向用户提出问题，仍是被测候选的结果，不由控制 Agent 代答。OS 隐私授权、管理员认证和未知敏感交互不纳入普通工具授权白名单。人工介入记录时间、原因和动作；若改变了候选内容或语义输入，标注 assisted/受干预并按场景决定有效性。

### 1.5 应用发现、重启、恢复与并发

**C09｜动态发现与控制端点核验。** 使用显式路径、运行进程、平台安装记录、Bundle ID/产品身份和受限标准位置发现应用。多候选、安装身份不符、陈旧 `DevToolsActivePort`、端口被其他进程占用均不得猜测成功。未知版本登记为待验证兼容性，按实际身份与能力检查，不仅因版本号未进白名单阻断。CDP 仅监听 loopback，核对监听者、主程序完整路径、页面 target；CDP 可用与是否 Electron 是不同问题。非 CDP 控制端验证等价目标身份。各平台均检查客户端实际编码/扁平化后的目录与文件名长度、Unicode/空格及路径映射；越限或不可访问在发送前报错，不等到客户端初始化失败。

**C10｜把三种“重启”分开验证。** 下列流程可以在用户既有授权范围内执行；本文不额外要求每次正常启动重新确认，但不允许打断不属于本次运行的工作。

| 场景 | 开始前 | 恢复后 |
| --- | --- | --- |
| 执行前开启调试/usage 开关 | 确认目标应用、端口和无冲突活动任务；冻结配置，必要环境变量只给目标子进程 | 重查进程、端口、版本、模型、权限及开关实际生效证据 |
| 被测 Harness 执行中崩溃/重启 | 先落盘所有活动 attempt、原生身份、deadline 和重启意图；不将非本批次会话纳入清理 | 按原身份恢复观察；原生 cancelled/interrupted 可以安全失败收口，不强求恢复成功、不重发 |
| 控制/评分客户端重启 | 保存 worker/queue、评分 thread/cursor 与交接状态；采用可独立于被重启客户端存活的托管入口 | 核对原 worker 是否存活，避免第二个控制者；沿用原评分任务而非新建替代任务 |

评分期间出现 `Selected model is at capacity. Please try a different model.` 时，沿用当前 Codex 评分任务的内置最多 5 次重试，不新建会话、不切换模型、不创建替代 attempt。候选本身无产物、产物错误或未满足题意是被评测结果，按 rubric 评分或保留合法 unresolved；控制会话不能因此终止整批、跳过后续题目或重跑 Harness。只有评分基础设施身份、冻结证据或 Skill 契约损坏才按评测异常处理。

当前共享 [macOS 调试重启入口](../../../tools/report/e2e-shared/desktop-debug/restart_macos_desktop_debug.sh)只支持 Codex，不能宣称它已经支持重启全部 Harness。被测应用的安全重启属于各 Driver 的能力；新平台需实现等价策略。多活动会话不能证明安全时，进入 NEEDS_ATTENTION 并保留现场。

**C11｜观察结束、业务终态和进程静默分别确认。** 控制 Worker 退出不等于 Harness 已停止；poll/基础设施操作超时不等于任务执行超时；Workspace 稳定不等于 Agent 完成。只有明确终态、目标任务停止、相关进程按身份收口、限定窗口内 Workspace 不再变化，才能冻结候选。停止操作超时且无法确认停止时保留待处理状态，不能继续投递以制造更多未收口任务。此条不为 General 题目增加执行总时限。

进程清理校验 PID、完整命令/cwd、创建时间或平台等价生命周期身份；拒绝按 `node`、浏览器或 Harness 名称批量杀进程。平台不支持精确枚举时标注支持边界，不能伪造“清理成功”。检查迟到子进程、孤儿进程和冻结后再次写入；旧终态补采也必须校验旧候选哈希且不重新发送。

**C12｜运行期 UI 必须互斥。** 串行开发无需申请桌面时段；同一桌面/Harness 的 UI 焦点、原生目录选择和弹窗仍必须互斥，运行期锁覆盖可能争用它的控制进程。UI 槽固定 1；后台执行与评分槽独立配置，未经验证的新 Driver 从执行单槽开始。通过稳定 session/cwd/授权路由与动态补位验收后，才开放已声明的并发数。

任何发送临界点不明、未登记活动 session 或无法路由的授权都应停止新投递，保留已活动任务。恢复检查 worker 的精确身份，陈旧锁只能按规则接管；不能仅删除锁文件后继续。队列范围、顺序、槽位与失败继续策略冻结，不能通过 resume 暗中换配置。

配置槽数、发送后未结束的调度占用数、原生请求执行区间重叠数分别记录，不能共用含义不明的“并发数”。实际原生起点不可观测时保留 unknown；并发准入未观察到声明峰值，应标记证据不足。短任务没有重叠、未出现补位等吞吐现象，不应单独使本来身份正确、一次发送、可信终态且证据完整的执行回执无效；并发验收结果与执行有效性分开。

### 1.6 原始轨迹、标准化和证据采集

**C13｜采集范围必须能绑定到本题。** 原生事件/API 优先，其次为本地 DB/JSONL/日志；UI/视觉证据作为明确降级来源。采集器只读目标数据，DB/WAL 采用一致快照、完整性检查和有界退避；热写失败不修改源库、不重跑题目。约束读取根、大小、数量和超时，不扫描认证目录或其他会话补齐缺失值。

**C14｜分别保存原始、标准化、索引和完整性。** 以下为共用逻辑对象，不要求强行统一两个场景现有文件名：

| 对象 | 最小内容 |
| --- | --- |
| 原始证据 | 本题实际可取得的原生事件，原生身份、事件范围、文件大小/SHA、时间与采集器版本 |
| 标准化事件 | 用户输入、最终回复、工具名/参数/结果/调用 ID、状态、时间/序号、可取得 usage；保留原始定位 |
| 索引 | 原始文件和行/sequence 到标准事件的映射，原始/标准事件数、丢弃/去重/缺失说明 |
| 路径映射 | 本机原始路径与逻辑 Workspace 路径；不能把两个不同原路径归并成同一个任务 |
| 完整性声明 | complete/partial/unavailable 等场景状态及依据、缺口、脱敏范围、受影响指标/评分项 |

不要求获取客户端未提供的内部推理；不能从最终文件反推工具调用、从 UI 数字补造 usage，或把一段摘要标为完整轨迹。保留可取得的最终回复，纯回复任务没有文件变动也可正常结束。

调用与结果按原生 call ID 关联，重复事件去重且记录规则；孤立结果、不完整流式事件、截断行、事件乱序和子代理归属必须有明确处理。后台记忆、控制会话、评分会话、其他题目不得混入本题主任务。原始日志和候选内容是待分析数据，不是对控制/评分 Agent 的新指令。

敏感凭据以受控方式脱敏并登记对证据的影响；原始敏感档案只留在受限位置，分发副本不携带账户 profile。不得在公开回执中写入真实密钥，也不得借脱敏改写会影响判分的事实。哈希必须说明针对原始档案还是脱敏副本。

标准轨迹和只读检索的现有落点参见 [General 轨迹归档](../../../tools/report/skills/general-e2e/collect-general-e2e/references/astronstudio-trace.md)。当前 Web 资源采集主要记录来源路径/SHA，并未等价实现完整轨迹归档；新接入须声明其轨迹级别，不能因指标能采到就填“完整轨迹”。需要工具成功率或基于过程评分时，补足相应原始结果证据。

### 1.7 常规指标与统一分母

**C15｜指标按字段声明来源与覆盖。** 每项至少具有值、单位、scope、来源状态、采集器/Profile 身份、证据定位、已知小计、覆盖分子/分母与观察单位。状态沿用 `observed / inferred / partial / masked / unverified / unavailable`；真实零值须有证据，缺失/掩码零不是实际零。

任务全集、已开始尝试、可信终态尝试、有效评分集合与工具调用集合分别保留。执行、裁判、控制消耗分账，主 turn 与已关联子代理/后台消耗分账；账户账单和主任务 usage 不强行对齐。每次聚合输出实际采用的范围和分母，异常任务不得从状态表消失。

| 已有基础字段 | 口径 |
| --- | --- |
| `input_tokens / output_tokens / total_tokens` | 归一化输入、输出、总量；已包含的缓存和推理子集不重复相加 |
| `cache_read_input_tokens / cache_creation_input_tokens` | 缓存读取与写入分别记录；默认零初始化不算观测到零 |
| `reasoning_output_tokens` | 推理输出子集，未暴露则 null |
| `request_count / request_attempt_count` | 注明原生请求、持久化响应或推导 usage 次数；不可见 HTTP 重试不估算 |
| `tools.call_count` | 唯一原生调用尝试；结果不再计为调用 |
| `duration_seconds / agent_duration_seconds` | 流程壁钟与原生/明确推导的 Agent 耗时；任务耗时之和不等于批次壁钟 |

Web 和 General 的分组结构不同，精确格式分别见 [Web 资源契约](../../../tools/report/skills/web-e2e/execute-web-e2e/references/resource-metrics.md)与 [General 资源 Schema](../../../eval_general_e2e/contracts/schemas/resource-metrics-v1.schema.json)。归一化前保留供应商原始 usage，累计快照必须扣除历史基线或取明确增量，不累计每次轮询的总值。

**C16｜声明支持的补充指标按以下口径接入。** General 已有平均 Token 与输入缓存命中率报告实现，其它统一指标及跨客户端原生对账尚未全部落地；本表规定语义，不直接新增 JSON 字段或支持声明。当前用户范围只要求工具调用次数，格式准确率/执行成功率/不确定占比暂缓，积分等无可信来源字段允许 unavailable。新客户端必须记录这些边界，但不把扩展指标全部实现作为基础加固前置条件。

| 指标 | 公式 | 必须处理的边界 |
| --- | --- | --- |
| 任务执行异常率 | 非正常终止的尝试数 / 实际开始执行的尝试数 | 全窗口终态齐备才给完整率；Harness 错误、超时、基础设施故障、人工取消分别列示；中途错误后恢复正常不算最终异常 |
| 工具调用成功率 | 明确成功的调用数 / 全部原生调用尝试数 | completed/result 到达不等于业务成功；检查结构化 error、工具语义与退出码；重试新 call ID 另算 |
| 平均每次执行积分 | 全部尝试已结算积分 / 执行尝试数 | 失败重跑也计费；单位、结算 ID、范围和延迟结算明确；余额/预估/累计快照不能直接求和 |
| 输入 Token 缓存命中率 | Σ缓存读取输入 Token / Σ含缓存的输入 Token | 分子分母必须同覆盖范围；按 Token 加权，不平均任务比例；cache write 不算命中 |
| 平均每次执行 Token | Σ归一化总 Token / 执行尝试数 | 明确所选 attempt 与全部 attempt 两种视图；不只平均成功任务，不重复加 cache/reasoning |

声明工具结局比率时，至少区分成功、错误、超时、取消和未知，并报告终态覆盖率；未声明比率时仍保留原始结果，不将 completed 解释为业务成功。没有工具调用/输入 Token 时对应比率为 null/不适用。任一关键分子分母不完整，完整比率/均值为 null；可另列成对完整子集结果并注明覆盖，或明确标注的下界，不能用已知小计除以全体冒充完整均值。

缓存归一化按已验证协议：OpenAI prompt/input 已含 cached 子集；Anthropic 原始 Messages 的输入总量需合并普通输入、缓存创建和缓存读取；某些兼容客户端虽使用相似字段名却已含缓存，必须用真实非零样本与终值对账。记录冷/热缓存、顺序、并发和重复运行条件，缓存命中率不是能力分或费用节省率。

积分使用实际结算数据，至少核对单位、结算状态和 task/attempt 归属。AstronStudio 的源码候选为 `turn.billing.settled/chargedPoints`，WorkBuddy 有按请求累加的 `credit_json`；字段名不能替代运行时对账。无可验证来源的客户端标记 unavailable，不从 Token 或 UI“消耗”反推积分单位。各厂商积分不可直接跨产品排名；`cost_usd` 与原生积分、估算成本分开。

指标失败通常只降低该字段覆盖，不改变已确认执行终态、不触发 Prompt 重发。若同一原生身份或证据哈希校验失败，须拒绝关联该数据；不能以“指标可选”为由接受串题数据。报告同时保留执行状态、评分有效性和数据覆盖，不能用 `1 - 评分完成率` 替代执行异常率。

### 1.8 冻结、评分交接、报告与发行

**C17｜候选不可变，目录策略按场景。** 保存初始/终态快照、路径类型、包含/忽略/禁止策略及 SHA。先确认终态与进程收口，再冻结候选；评分和重评分只消费冻结副本，安装依赖、build、缓存写入发生在受管 runtime 副本。漂移应记录错误并拒绝，不能修复候选、重新接受哈希或删除目录来通过校验。

**C18｜跨阶段交接可审计。** 正式 execution/collect receipt、候选、轨迹、资源、score、submission、return/import receipt 形成可追踪链。冻结任务完整有序，失败/未评分有显式状态。重试幂等、冲突不覆盖；不同场景的冲突处理分别遵守原协议。解包校验版本、身份、成员集合、相对路径、链接类型和 SHA，临时写入后原子发布；禁止访问候选外文件补结果。

**C19｜报告与发行必须能独立复现。** JSON 是聚合源，Markdown/Excel 从同一数据生成，检查分数、分母、资源覆盖与异常状态一致。执行错误与评测系统错误分开；两个场景现有能力分协议有差异，不在公共指标改造中顺手改分。

Skill 以 manifest 为安装清单；共享源码通过构建装配，不手改 vendored 副本。验证 ZIP/content SHA、组件闭包、依赖锁和仓库外入口，不依赖兄弟 Skill 或开发机恰好安装的包。Web 安装校验要求 `check_web_e2e_skills.py` 的 `all_current=true`；General 遵守自身 release/能力门禁。打包不执行新评测、不上传云端、不携带认证缓存。回滚保留旧 artifact 与结果，不能把新格式覆盖成旧格式。

<a id="hardening-matrix"></a>

### 1.9 共用加固验证矩阵

**每个新 Harness 集成任务必须纳入 CV01–CV17 全部记录，逐项判定适用性、安排实现和验证；不能挑选几项后笼统填写“已加固”。** 一项包含多个故障分支时记录子项；未做、失败或缺证据不能填为不适用。代码实现、自动化/模拟测试、目标客户端真机验证分别记录，单测数量或录制样本不能代替真机结果。允许引用同 revision 的公共组件回归，但 UI、原生身份、发送边界、终态、进程收口等目标客户端行为不能继承别的 Harness 的 PASS。

| 声明层级 | 必须纳入的验收范围 | 可以明确暂缓的部分 |
| --- | --- | --- |
| 受控、值守主流程完整接入 | CV01–CV09 的基础安全分支、CV10 串行、CV11–CV15、CV16 当前声明平台和 CV17；发送临界、断连/待交互安全暂停与适用的实际任务进程清理须有目标客户端证据 | 自动抢占陈旧锁、自动重启后继续执行等无人值守恢复；未声明平台；无可信来源的可选指标 |
| 并发可用 | 基础范围加 CV10 对应的原生重叠、动态补位、隔离/授权路由与恢复；达到声明槽数要有原生区间证据 | 更高并发和其它未声明配置 |
| 无人值守恢复 | 适用 CV04–CV09、CV14 的完整自动恢复分支，包括 Worker/客户端重启与陈旧锁处理；仍不得重发或误杀 | 未声明平台/后端等，与无人值守承诺无关的扩容 |

基础安全分支允许结论为“安全暂停/可信失败”，不强求故障后自动继续；暂停时必须保留现场并有可操作的恢复说明。主动重启、自动批准、DB/WAL 采集等分支按实际能力触发；未提供自动批准时可以不实现白名单点击，但未知授权/追问的安全停止仍必做。阶段性主流程已跑通而基础必需故障证据未齐时，记录“主流程有限可用、加固进行中”，不得关闭完整接入任务。

受控故障注入使用独立技术验收任务，记录注入位置和预期不变量，不临时修改正式评测题目、缩短题目 timeout 或破坏候选。General 的 UI/CDP、绑定、停止、清理、Judge 等基础设施超时分别注入，题目 `timeout_seconds` 不生效。

| 验证 ID | 关联要求 | 验证动作与通过条件 | 最低证据 |
| --- | --- | --- | --- |
| CV01 | C01–C03、C05、C19 | 全部要求建项、Schema 正反例、执行/评分材料隔离、共享闭包、协议/包身份漂移拒绝、单 Skill/suite 仓库外运行；不设客户端精确版本白名单 | 符合性记录、命令/退出码、版本与 artifact SHA |
| CV02 | C07、C09 | 真机只读 probe；端口占用、陈旧端点、多安装、锁屏/未知状态均不误判 | probe、安装路径、进程/端口、无发送证据 |
| CV03 | C04–C08 | 真机同名不同 Workspace、模型/权限不符、重复 UI 控件；Prompt DOM 与客户端内部状态有分层时核对两者，禁用/布局变化的发送控件不强点；唯一匹配后只发送一次 | 请求/回读、Prompt SHA、原生身份、真实发送计数；reservation 不当作发送 |
| CV04 | C08、C10 | 意图落盘前、落盘后发送前、发送后身份落盘前分别做中断反例；发送临界至少一个目标客户端真机样本，恢复不重复发送，未知时停止 | journal、注入点、前后 session、原 attempt、实际发送次数 |
| CV05 | C10、C12 | Worker 丢失、两个 Worker 竞争、活 Worker 重复接管、两个陈旧锁回收者；值守模式可停住等待人工，不自动删锁或生成替代 attempt | PID/生命周期、锁所有权、queue/thread/cursor、发送计数 |
| CV06 | C09、C10 | 目标客户端断连/重连后原身份续观或安全暂停；声明主动重启时分别验证执行前、Harness 执行中、控制/评分客户端重启；自动续跑另验 | 前后连接/进程身份、restart 状态、配置、原 attempt 或可信失败 |
| CV07 | C07、C11 | 真机正常、最终错误、工具失败后恢复、纯回复、未知状态；不以文件稳定推断完成 | 原生终态、状态映射、最终回复 |
| CV08 | C07、C08 | 白名单授权、未知授权、追问、人工介入；不越权批准或补答案 | 匹配规则、命令哈希、介入记录 |
| CV09 | C11、C17 | 分别验证无残留正常收口、实际残留进程优雅终止、停不掉时拒绝冻结、迟到进程/冻结后写入；声明强制回收时验证 TERM→KILL 或平台等价分支，并保护无关对照进程 | 目标 PID/生命周期与退出确认、termination attempts、无关进程前后状态、静默窗口和快照；仅 targets=0 不能证明终止分支 |
| CV10 | C04、C12 | 三题串行；声明并发时至少五题跨多轮补位，UI 单槽；配置槽数、调度占用、原生重叠分别验证，短题未达并发不得独立判执行回执无效 | 两种起止时间线与覆盖、五题身份/终态、无串题/重发；缺原生起点保留未知 |
| CV11 | C13、C14 | 热写 DB/WAL、重复/截断/乱序/缺失事件、孤立结果、子代理与后台混入 | 原始/标准事件对账、缺口与去重记录 |
| CV12 | C15、C16 | 已支持指标的累计基线、重复 usage、零/掩码零、部分覆盖、原生与流程耗时；声明相应字段时再验工具结局、缓存归一化、积分重复/延迟结算；未知不补零 | 固定预期值 fixture 加支持字段真机样本对账，不以可选指标不可用阻断有效评分 |
| CV13 | C17、C18 | 冻结前后漂移、缺文件、同名不同内容、越界路径/链接、敏感 profile | 明确拒绝及候选未被改写证据 |
| CV14 | C10、C18 | 评分失败/中断、submission 发布窗口中断、同包重复导入、冲突回传 | 独立 attempt、原子发布/幂等/拒绝覆盖记录 |
| CV15 | C18、C19 | 源码→发行包→新任务执行与首次正式采集→评分→回传→导入→JSON/Markdown/Excel 完整闭环；补采旧证据不替代新采集入口验收 | 同一声明范围的 release/运行身份、全部回执、哈希链和报告核对 |
| CV16 | C02、C09、C19 | 声明的每个 OS/架构/安装形态真机复验；升级后标记失效范围，回滚不覆盖证据 | 平台矩阵、复验/沿用理由、回退记录 |
| CV17 | C04、C05、C09 | 在发送前检查实际路径映射、客户端编码/扁平化目录的字节长度和文件系统限制；中文/空格、最长任务 ID、越界/符号链接及越限边界用例 | 原始与编码后路径的受控记录、边界测试、拒绝时实际发送数为 0；使用短根不等于已有自动预检 |

CV09 必须按上述分支保存结果。适用真实终止分支时，至少有一个测试 Workspace 内受管进程和一个与该 Workspace 无关的对照进程；两者均由本次验收创建，不能拿用户既有业务进程作故障注入对象。证明前者按预期终止、后者未被影响，不以扫描到零进程替代。客户端确无该类进程能力时，可对具体分支注明不适用及证据，不能将整个候选静默/冻结检查跳过。未实现强制回收可收窄声明，但仍须验证停止未生效时不冻结。

验证按变更影响复用：公共代码的同版本自动化证据可以引用；新 Driver/采集路径需要目标客户端新任务验证。仅报告排版/聚合变化，可用既有真实冻结回传复算、导出和视觉核对，不为每次报告修改重跑 Harness。复用原因、来源 SHA 和仍需目标客户端验证的项必须写清。

### 1.10 接入完成的交付物与符合性记录

每个新 Harness 的集成任务同时交付：能力/字段映射、Driver 与平台适配、原始样本和解析 fixtures、场景回执映射、依赖及发行更新、C/G/W 要求及 CV01–CV17 的逐项记录、适用基础加固实现和真机证据、支持边界与恢复操作。引用公共实现不免除本客户端接线和适用性核对。仅实现 Web 或 General 时，另一章标为未声明支持，不能填写已通过。

必须留下**人工符合性记录**，可按下列模板填写或映射到现有验收表，不要求另建平行台账。下面只展示一项的格式，实际记录必须覆盖 CV01–CV17，并保留适用场景 GV/WV；各 Harness 的当前状态统一放在本文第 5 章，`evidence/` 保存运行事实和原件索引。当前没有统一 JSON Schema 或自动符合性校验器，这些是集成任务完成条件，由交付审核逐项核对；不能宣称工具已经自动强制执行。

```yaml
contract: E2E-HARNESS-CONTRACT/0.3
scope: <Harness + 场景 + OS + 架构 + 客户端版本>
identity: <Driver/Skill/组件/依赖/数据集/配置的版本与哈希清单>
claimed_capabilities: <执行、轨迹、指标、评分交接、串行、并发、恢复>
admission: <阶段可用、受控闭环、并发可用或无人值守范围>
requirements:
  - id: C08
    applicability: required
    implementation: <文件/符号/提交>
    verification: [CV03, CV04]
    result: NOT_RUN
    evidence: []
    limitation: <缺口及下一步验证动作>
validation_records:
  - id: CV04
    applicability: required
    implementation: <文件/符号/提交或公共实现引用>
    automated: {result: NOT_RUN, evidence: []}
    live: {result: NOT_RUN, evidence: []}
    subcases: <各发送临界窗口的独立结果，不能合并丢失缺口>
    result: NOT_RUN
    next_action: <具体实现或验证动作>
```

记录状态可用 `NOT_RUN / IN_PROGRESS / PASS / FAIL / BLOCKED / STALE / NOT_APPLICABLE`；与现有 Web 的 `PASSED / NOT_STARTED` 等做明确映射，不要求重写旧矩阵。`NOT_APPLICABLE` 必须解释依据，FAIL/BLOCKED/STALE 不能变成 PASS；父项含未验必需子项时不能整体 PASS。未支持的积分/Token 字段允许明确降级，缺少身份、一次发送、终态安全或候选不可变性则不能声明相应自动执行/交接能力。

每条证据注明自动化/模拟或目标客户端真机、源码/包身份、日期、平台、task/attempt、原生身份、实际断言和原件路径/哈希。没有触发对应故障分支的成功运行不算该分支 PASS。要求未建项、基础必需实现缺失、必需真机证据不足或失败未处置时，集成任务保持 IN_PROGRESS/BLOCKED；可以准确记录主流程阶段成果，不能以“正常五题通过”关闭全部任务。

准入分层保留“主流程、并发、无人值守”差别：主流程闭环通过可以在声明的值守和单槽边界使用；并发增加 CV10 及场景并发评分证据；无人值守还要满足适用的故障恢复项。本文不以统一新标签替代 General 的 G0–G7 里程碑或 Web 已发布三级准入，也不要求为使用较低层级而先补完全部高可用测试。

<a id="integration-task-template"></a>

#### 新 Harness 集成任务范围模板

以下清单直接写入接入任务的目标和完成条件，不另派一个可选加固任务；开发方式沿用当时用户约定，不从历史 `collaboration/task-template.md` 恢复并行 worktree 或桌面时段流程。

```text
接入 <Harness> 的 <General/Web>，平台 <OS/架构>，目标支持范围 <值守单槽/并发/无人值守>。
1. 阅读 E2E-HARNESS-CONTRACT/0.3：共用章及对应场景章；记录实际能力、源码/包与客户端身份。
2. 在本客户端的现有进度/证据记录中展开 CV01–CV17，以及 General GV01–GV08 或 Web WV01–WV08。
   每项标记适用性、实现落点、自动化结果、真机结果、证据与下一步；不适用须有依据。
3. 完成 Driver、原生身份/终态、轨迹/指标、精确收口、正式回执和公共评分/报告接入。
   同步实现基础加固：一次发送、锁与安全恢复、UI/草稿核验、路径预检、来源/哈希/不可变性。
4. 执行适用的反例测试和最小真机故障验证，覆盖发送临界、未知交互安全暂停、真实受管进程清理及无关进程保护。
   按声明补验并发与自动恢复；故障注入独立标记，不混入能力评分，不修改题目 timeout。
5. 冻结并验证独立发行，用新任务完成首次采集至评分/回传/报告的 canary；核对分母、缺失值及证据链。
6. 更新本文第 5 章对应 Harness/场景/平台进度，并追加 evidence 索引。基础必需项未通过不得将完整接入标为 DONE。
   保留阶段成果、未验证范围和恢复步骤；不因文档或单测通过自动提升平台准入。
```

## 2. 通用场景专有契约

### 2.1 数据集、阶段与任务语义

**G01｜General 使用独立任务协议。** 以本文 G 条款、[运行契约](../../../eval_general_e2e/contracts/README.md)和 [技术方案](../general-e2e/通用场景端到端自动化评测技术方案.md)为精确依据。数据集 manifest 冻结任务全集与顺序、Prompt、初始 Workspace、私有评分材料和 digest；题意、rubric、规则与权重不随 Harness 改变。路径改写仅按现有确定性映射并保留前后 SHA。

审计每题 Env、Skills、Warmup、网络、命令、素材、链接类型、轨迹要求及平台差异。实际需要而未满足的前置条件不能当作模型能力失败；不通过修改题目或放宽 grader 来让新客户端接入。

**G02｜七个阶段 Skill 分工保持清晰。** `prepare-general-e2e-workspaces` 准备；`execute-general-e2e` 做题；`collect-general-e2e` 形成证据；`orchestrate-general-e2e` 编排评分；`score-general-e2e` 单题评分；`report-general-e2e` 汇总；`run-general-e2e` 串联明确选择的阶段。阶段名 `collect-evidence` 与回传 `import-return` 不混用。新增 Harness 不能只改执行入口而漏掉 collect、打包、能力声明和正式回执。

### 2.2 通用产物、轨迹与正式收口

**G03｜支持文件与纯回复两类结果。** 无文件变更不能判失败；原生正常终态与最终回复可以构成纯回复任务的候选。代码、文档、二进制、Git 仓库、缓存、受限符号链接按任务契约保留；不能套用 Web 的 `.git` 禁止策略或统一删 `node_modules`。跨平台保留必要路径映射、文件类型和可复核哈希，不能跟随链接读取宿主私有文件。

**G04｜轨迹适配必须经过实际 grader 验证。** 工具别名、参数、调用结果、路径和顺序须兼容任务实际执行的规则，不只验证 JSON 可解析。按真实可达 grader 需求声明完整性；缺少必需轨迹时该项/任务不可评分，不能用空 transcript 或最终文件猜测代替。规则读取哪些证据、丢失哪些字段应可定位。

**G05｜collect 回执是评分准入，不是 Driver 自报完成。** 采用 General 的 execution-record、transcript-event、trace-index、resource-metrics、score、submission、receipt Schema，并运行跨字段校验。完成执行还需身份、一次发送、原生终态、证据 hash、任务进程收口与稳定候选相互一致；非成功终态只收实际存在的证据，不伪造完整文件。

当前 General 一个已准备 unit 只登记唯一执行 attempt；需要重新做题时保留旧 unit/queue，准备新独立 unit，不能直接增加目录让旧 collector 自动选“最新”。评分重跑使用新的评分 attempt，并继续引用同一冻结候选。

### 2.3 规则、语义裁判与报告

**G06｜三类评分按任务声明组合。** automated 只跑自动规则；hybrid 按冻结权重组合规则与语义；llm_judge 使用语义协议。自动规则不额外调用未声明的模型；规则运行时异常不转换为候选能力零分，规则正常执行后判定候选不满足要求的真实零分仍有效。评分运行时在私有受管副本中安装锁定依赖、执行任务原规则，超时后精确清理；本地受管进程不是恶意代码安全沙箱。

默认 `codex-agent-judge-v1` 每题独立评分会话；`api-judge-v1` 由批次显式选择。冻结模型、推理配置、证据预算与协议，API/控制客户端失败不静默切换后端。证据压缩、截断和遗漏可审计；逐 criterion 判断由裁判提供，权重合分由确定性代码完成。

**G07｜执行异常、评分有效性、资源覆盖分别报告。** 采用 `valid / evaluation_error / unscored`：真实有效零分保留，后两类不补零、不进入能力均值。候选执行失败仍可能按原规则取得有效分，依据 score 的有效性判定。报告保留完整任务状态，按类别/难度、unit、裁判协议与配置分组；不同裁判不得无提示合并比较。

### 2.4 通用验证与接入判定

| 验证 ID | 关联要求 | 通过条件 |
| --- | --- | --- |
| GV01 | G01、G02 | dataset/release/unit 完整校验，任务依赖可满足，execution 不含私有评分材料，七个阶段边界正确 |
| GV02 | G03、G05 | 真机文件任务与纯回复任务各完成一次；都能归档最终回复、冻结候选并形成 collect receipt |
| GV03 | G04 | 真实工具参数/结果/时序通过有轨迹要求的原 grader；缺必需轨迹被明确拒绝 |
| GV04 | G03、G05 | Git/二进制/受限链接与平台路径按任务策略保留；终态收口和冻结后漂移校验通过 |
| GV05 | G06 | automated、hybrid、llm_judge 三类闭环；仅对声明支持的语义后端分别做真实验收；无双重评分/静默回退 |
| GV06 | G06、G07 | 有效零分、缺证据、Judge 错误、重评分与失败 attempt 隔离的报告分母正确 |
| GV07 | G02、G05–G07 | 显式阶段恢复到 submission/return/import/report；JSON/Markdown/Excel 与回执同源 |
| GV08 | G01–G07 | 声明平台的完整小批与并发验证；跨机评分与本机闭环分别声明；扩大范围后保留全部失败题 |

固定 smoke 使用第 4 章的 S1–S5（保持原 ID）：文件修复、工具过程安全、hybrid 交接、纯回复、第五题动态补位；登记完整 task ID 与 digest，不另造五道近似题。题目 `timeout_seconds` 仅保留兼容元数据，不限制被评测 Harness 总执行时间，也不纳入评分；基础设施/评分控制超时注入使用独立验收批次。实现要求按本文 GV 与归档的 G/MAC/WIN 验收 ID 映射，固定五题见第 4 章。

小批通过只支持对应场景/平台/版本的接入结论，不替代既有方案要求的全量与裁判校准。更新本文第 5 章对应 Harness 的 General 记录；不把 AstronStudio 或某个平台的通过状态复制给新客户端。

## 3. Web 站点专有契约

### 3.1 阶段、Profile 与执行交接

**W01｜站点生成与站点评分分离。** `prepare-web-e2e-workspaces` 准备材料；运行阶段按 manifest 安装 `run / execute / orchestrate / score / report-web-e2e` 五个 Skill，不硬编码安装旧清单。Driver 控制 Harness 在本地项目做题，后续评分由独立单题项目/会话进行；评分目录必须精确为本题 `score/tasks/<task_id>`，不得注册 execution 原件或整个批次供评分。

**W02｜Profile 冻结且不混分。** 精确字段以 [评分 JSON 契约](../../../tools/report/skills/web-e2e/score-web-e2e/references/scoring-contract.md) 为准。`web-e2e-detailed-v1` 使用归一化 criterion、内容/交互/视觉维度及独立审美；`artifactsbench-web-v1` 按原始 0–10 整数锚点判分并确定性归一化，不新增独立审美和详细维度。旧包的兼容默认仅按已定义版本执行，新包显式声明 Profile。

当前 Web 的执行错误、超时、评测异常在其发布评分协议下保留状态并使用零总分；General 的有效分母不同。公共常规指标必须保留状态，不能顺手改 Web 既有得分语义，也不能把该零分当作评测系统故障导致的真实能力零分进行跨协议比较。若调整，单独版本化评分/报告协议。

**W03｜Web 候选目录策略保持精确。** 新执行回执声明运行时目录策略时，execution 原件可保留候选生成的 `.cache / .vite / node_modules`，按策略从哈希/评分复制/回传中过滤并记录实际存在路径；不得删除原件。`.git` 仍禁止。未声明该策略的旧回执按原严格协议读取，不能默默升级。具体策略以 [Driver 契约](../../../tools/report/skills/web-e2e/execute-web-e2e/references/driver-contract.md) 为准。

### 3.2 站点运行时与浏览器取证

**W04｜按候选实际技术栈启动。** 先只读识别 README、scripts、锁文件、包管理器和静态入口；不假设都是 Vite，不为纯 HTML 站点补 package.json。任何安装/build/缓存写入只能发生在私有受管 runtime 副本，原候选只读。服务仅监听 loopback，每题独立端口、进程和浏览器状态。

端口冲突优先用参数/环境变量换端口。仅在现有 [评分 Skill](../../../tools/report/skills/web-e2e/score-web-e2e/SKILL.md) 定义的已证实硬编码冲突条件下，才允许受管工具修改 runtime 副本中的唯一数字端口并保存审计；不能修复候选业务逻辑。按本题已登记 PID/进程组/Windows service ID 停止并清理 runtime，不按 Node 名称或端口批量杀进程。

**W05｜交互必须实际验证。** 每个 criterion 恢复预设状态，实际点击、输入、提交、刷新、改变视口或上传下载；记录动作前后公开状态。源码用于理解控件，静态 DOM 或截图不能替代交互成功证据。日期、取色器、拖放、原生对话框和瞬时反馈按 [浏览器交互评分](../../../tools/report/skills/web-e2e/score-web-e2e/references/browser-interaction-scoring.md) 处理，避免操作没触发就误判候选失败。

视觉 criterion 保存对应视口截图；非截图可表达的事实保存结构化观察。截图按现有受管接收器写入，检查实际图片签名、MIME、文件路径及题目归属；不在题目目录临时写接收服务。每题隔离 Origin 存储，不能沿用上一题登录、缓存或表单状态。浏览器对象、URL、端口和截图都绑定本题评分 attempt。

### 3.3 Web 回传与验证

**W06｜submission 前重新检查所有边界。** 每个 criterion 恰好出现一次，证据满足 Profile；execution/score 两份候选 hash、实际模型、执行回执 SHA、目录策略、服务/截图接收器终态和 runtime 清理结果一致。评分 Agent 只填写判断和证据，确定性脚本生成 task_score/submission。评分和打包不改原件以通过完整性检查。

回传 ZIP 和外置 receipt 按 [离线交接契约](../../../tools/report/skills/web-e2e/run-web-e2e/references/handoff-contract.md) 发布；完整有序 task IDs、Profile、模型/Harness、source revision 贯穿导出导入。Web 禁止 ZIP 符号链接；过滤候选策略允许忽略的目录和浏览器 profile，不与 General 允许的受限链接规则合并。同 SHA 重试幂等，冲突内容拒绝覆盖。

| 验证 ID | 关联要求 | 通过条件 |
| --- | --- | --- |
| WV01 | W01、W02 | 两种声明支持的 Profile 各有契约样例；Skill manifest 校验当前，评分根精确注册 |
| WV02 | W01、W03 | 一个 L1 真机生成并冻结站点，候选/目录策略/执行回执一致，再完成 Browser 评分与 return |
| WV03 | W04 | 原生静态站点与需依赖构建的站点分别启动；安装/build 不污染两份候选 |
| WV04 | W04、W06 | 端口占用、硬编码冲突、启动失败和受管进程清理可审计；runtime 修改边界正确 |
| WV05 | W05 | 动态交互、刷新/存储、适用视口、原生控件与截图链路真实取证；不靠源码代替判断 |
| WV06 | W01、W04、W05 | 三题串行、五题执行补位和声明的评分并发；项目/会话/端口/浏览器/截图不串题 |
| WV07 | W02、W06 | Profile/criterion/截图缺失、候选漂移、目录策略、浏览器 profile 泄漏均被拒绝；报告分母符合当前协议 |
| WV08 | W01–W06 | 单 Prompt 串联执行、评分、submission、return、import/report；失败评分/控制重启和发布中断按原 attempt 恢复 |

归档的 [Web 生产验收清单](archive/web/生产验收历史-20260923.md) 的 V00–V17 及资源 P6–P9 继续有效，接入记录映射到 CV/WV，不另复制一份滚动状态。主流程生产可用、并发生产可用、无人值守高可用按其分层门槛声明；首个正式批次保留 3–5 个 L1 canary。恢复、并发或特定平台未验收时，明确值守/单槽范围，不能把“已能点击生成站点”写成完整生产支持。


<a id="integration-steps"></a>
## 4. 具体集成步骤

步骤面向一个 Harness 核心 Driver。接入第二个场景时复用控制能力，另验该场景的数据、回执、评分和报告；共享控制代码发生变化时，两条实际入口都需按影响回归。文档中的步骤不是两个 Driver 副本的复制模板。

| 步骤 | 实施与检查 | 可审查交付物 / 门禁 |
| --- | --- | --- |
| 1. 冻结范围 | 选择 Harness、场景、OS/架构、值守/并发/无人值守、模型/权限、Judge；记录安装/源码/包/依赖身份 | 本章状态行及 C/G/W、CV/GV/WV 的适用性记录；未声明范围不提前 PASS |
| 2. 只读探测 | 发现唯一应用和控制端点，验证进程、版本、GUI/锁屏、依赖、活动任务、原生状态/日志来源、路径预算 | probe 与负例；本步不创建任务、不发送 Prompt |
| 3. 接入 Driver | 唯一 UI 控件定位、完整 Workspace 回读、配置冻结、意图落盘、一次发送、原生 session/cwd 绑定 | 单题 journal/发送计数/Prompt SHA；同步做 CV03–CV05 中断和锁竞争 |
| 4. 接入观察与恢复 | 正常/错误/待交互/未知分开；原会话续观；只处理已授权交互；停止需原生确认 | 正常、失败、纯回复及未知交互的真实证据；不确定时暂停而非重发 |
| 5. 接入原生证据 | 只归档绑定会话/turn 的原始数据，保留 SHA、范围、标准事件、缺失与重复；映射可观测指标 | 解析 fixtures 与原始/标准对账；轨迹需求按场景 grader 验证 |
| 6. 接入收口 | 精确终止任务进程、保护对照进程，检查静默/迟到写入并冻结候选 | 真实 TERM/KILL 或声明的停止分支、失败拒绝发布、正式回执和 verify-only |
| 7. 接入场景后半程 | General 规则/语义与 Web Browser 取证分别对接；独立评分 attempt，生成 submission、return、import、报告 | 同一身份的首次执行→首次采集→评分→回传→报告闭环；异常不伪装成绩 |
| 8. 扩到声明并发 | 先串行，再五题默认槽位与补位；UI 单槽；原生重叠和调度占用分别计算 | 五题身份/终态、真实并发、无串题/重发及评分隔离 |
| 9. 发行并判定 | 构建独立 Skill/suite，仓库外安装；按变更复验公共组件与客户端分支 | 清单/内容/ZIP SHA、真实新任务、声明范围和未完成项 |
| 10. 更新唯一进度 | 仅更新第 5 章的对应行和 evidence；失败与旧身份保留 | 不创建新的“当前进度”文件；历史台账移入 archive |

| General smoke | 完整 task ID | 评分类型 / 覆盖 |
| --- | --- | --- |
| S1 | `02_Code_Intelligence_task_001_temperature_cli_fix` | automated；文件修改、测试 |
| S2 | `06_Safety_Alignment_task_001_suspicious_installer` | automated；工具参数/时序、安全副作用 |
| S3 | `01_Productivity_Flow_task_005_support_handoff` | hybrid；文件与语义合分 |
| S4 | `01_Productivity_Flow_task_003_retro_agenda` | llm_judge；最终回复 |
| S5 | `03_Social_Interaction_task_003_colleague_leave_reply` | llm_judge；第五题补位与独立评分 |

执行次序服从冻结 manifest，不按上表重排任务。Web 使用对应 Profile 的 L1 小批；旧 V00–V17 定义与原始验收身份保留在[Web 历史台账](archive/web/生产验收历史-20260923.md)，新任务仍展开共用 CV 与 Web WV，不改写旧记录。

<a id="integration-progress"></a>
## 5. Harness 集成进度与当前任务

更新：2026-09-23。以下依据现有源码和运行记录归并，本次未运行 Harness/Judge。状态必须同时带场景、平台、源码/包和支持范围；当前源码版本不自动继承旧发布的真机结论。历史声明仍仅对其已验身份有效。

### 5.1 源码与运行身份

开发在当前仓库工作区 `feature/astroncode-eval` 串行进行，不恢复旧协作档案的派发、平台 worktree 或人工桌面排期。评测运行仍可使用已验的执行/评分并发。当前用户约定：调试产物置于 `/Users/gzx/debug-workspace/e2e-evaluate`，正式分发置于仓库 `report-workspace`，不 push，不主动重启承载控制的 Codex Desktop。

- General 源码 Skill 版本：`collect-general-e2e 0.8.0`、`execute-general-e2e 0.11.0`、`orchestrate-general-e2e 0.9.6`、`prepare-general-e2e-workspaces 0.2.0`、`report-general-e2e 0.5.1`、`run-general-e2e 0.5.2`、`score-general-e2e 0.8.3`。
- Web 源码 Skill 版本：`execute-web-e2e 1.17.0`、`orchestrate-web-e2e 0.3.2`、`prepare-web-e2e-workspaces 4.4.0`、`report-web-e2e 1.1.1`、`run-web-e2e 1.4.2`、`score-web-e2e 4.5.4`。

- QwenWork General 最近执行实现 `190406c`，独立发行 `qwenwork-hardening-190406c`，execute 0.10.27；Qwen 聚焦 Node 115/115、发行/布局 Python 16/16。记录证明对应变更与 canary，不代表全部准入已完成。
- Web 最近已有分发索引为 `dba9700...` 的 `20260919-125641` 自建 40 / 开源 120 包；历史功能/资源验收另有 `6988b525...`、`ee70a67...`、`24771ce...`、`ff5d476...`、`c257fbd...` 身份。当前源码与这些包按内容 SHA/影响核验，不能只凭重打包继承支持层级。

### 5.2 General 场景

| Harness / 平台 | 已验证范围 | 尚未完成 / 当前判定 | 依据 |
| --- | --- | --- | --- |
| AstronStudio / macOS Intel | G4-03 五题三槽执行/评分/回传/报告；后续双题 smoke 2/2 valid | 已有对应身份的受控生产证据；公共新版本按影响复验 | [五题](../general-e2e/evidence/g4-03/README.md)、[双题](../general-e2e/evidence/macos-current-smoke-20260919/README.md) |
| WorkBuddy / macOS Intel | v8 为 5/5 valid、原生峰值 2；v2 加固 canary 为原生峰值 3、2 次补位，评分 2 valid/2 异常/1 容量未评分 | 不把不同批次拼成 5/5 valid 且峰值 3；未知授权/追问、评分稳定性等收尾，完整接入 IN_PROGRESS | [v8](../general-e2e/evidence/workbuddy-macos-general-v8-three-slot-20260921/README.md)、[v2 加固](../general-e2e/evidence/workbuddy-hardening-20260921/README.md) |
| QwenWork / macOS Intel / 1.2.0 | r21 原生三路五题闭环；r23 核心 Token 5/5 与正式报告；r31–r35 路径、授权、清理、终态/标题加固 | 主流程有限可用，完整接入 IN_PROGRESS；剩余七项见下文 | [运行证据](../general-e2e/evidence/qwenwork-macos-five3-20260923/README.md) |
| DoubaoWork / macOS Intel / 2.31.3 | 共享 Driver/原生证据核心、General adapter；r10 S1 与 r12 S2 各自同发行闭环有效 1.0；r11 三题串行、r19/r20 五题原生三路及补位完成 | IN_PROGRESS；r20 S1/S2 自动评分1.0；S3/S4 多源顺序 partial、独立语义评分与完整加固及 Web 闭环未完成 | [本轮证据](../general-e2e/evidence/doubaowork-macos-general-20260924/README.md) |
| 全部 Harness / Windows、Apple Silicon | 当前 General 台账没有相应完整真机准入 | Windows 暂缓；Apple Silicon 单独验证；不外推 Intel 结果 | [历史 Windows 实施范围](archive/general/AstronStudio-Windows后续实施清单.md) |

### 5.3 Web 场景

| Harness / 平台 | 已有证据边界 | 当前缺口 / 不应外推 |
| --- | --- | --- |
| AstronStudio / Windows | `6988b525...` 对应身份 V00–V17，历史声明无人值守高可用；`ff5d476...` 另验资源 | 后续发行的影响项、跨平台同 revision 包对账仍需明确重绑 |
| WorkBuddy / Windows | `ee70a67...` 对应 5.5.6.0 身份 V00–V17；`ff5d476...` 另验资源 | 同上；旧双路样本不能自动证明当前默认三路 |
| QwenWork / Windows | `24771ce...` 单 L1 执行→评分→return 主流程；`c257fbd...` 1.0.6.0 自动 Token 开关与新 L1 采集 | 当前身份串行/并发、管理员 import/report、V12–V17 未全重绑；不声明并发或无人值守全覆盖 |
| AstronStudio / macOS Intel | `6988b525...` 的独立 macOS 包有单 L1 全流程，历史主流程生产声明 | 与 Windows 包身份不同；新发行并发/恢复和双平台字节对账不自动继承 |
| WorkBuddy / macOS Intel | 有旧执行/并发功能证据及发布 smoke | 后半程与恢复项在原 Web 矩阵为 STALE/待重验，不按 General 成果升级 |
| QwenWork / macOS Intel | 1.0.5 历史执行与资源样本；已有 L1 执行记录 | 1.2.0 General 的 Token/并发/加固不等于 Web 同版本准入，需 Web 入口单独验证 |
| DoubaoWork / macOS | 已提取与 General 共用的 Driver/原生证据源码；Web 初次提取聚焦回归 64/64 | Web 自身正式 collect/finalizer、评分回传仍未闭环，保持 NEEDS_ATTENTION；General 的 2.31.3 原生映射不自动升级 Web 准入 |
| DoubaoWork / Windows；其他未声明架构 | 无本场景完整证据 | NOT_RUN，不凭共用接口推定支持 |

Web 逐项 V00–V17、P0–P10、客户端/Skill/包 SHA 和运行路径见[历史验收记录](archive/web/生产验收历史-20260923.md)；DoubaoWork 专属现场见[证据索引](../web-e2e/evidence/doubaowork-macos-web-e2e/README.md)。历史台账停止滚动更新，新的进度仅改本表并追加 evidence。

### 5.4 当前推进顺序

本任务按用户 2026-09-23 指定顺序推进 DoubaoWork General，再收口 Web；QwenWork 的剩余准入保留原状态。其他已有 Harness 保留各自证据与缺口。Windows 新开发暂缓，历史 Web Windows 结论保留。评分配置在各批次冻结，当前 QwenWork General 后续批次固定 `gpt-6-sol/high`，不回填旧 astra/high 结果。题目时长不作为能力评分条件，不为覆盖状态表改题或逼模型产生指定分数。

### QwenWork 剩余生产准入事项


范围为 macOS Intel / QwenWorkCN 1.2.0 / 值守 / 默认三路。r31 路径预算、r32 未知授权、r33 关键进程收口、r35 终态/标题同步已验证，不再作为未完成项。下面七项区分实现缺口与验收证据缺口；不能把所有 PARTIAL 都解释为功能未实现。

| 事项 | 类型 | 具体收口要求 | 对应记录 |
| --- | --- | --- | --- |
| 环境异常门禁 | 补实现并补测 | Qwen General probe/执行入口尚无显式锁屏或 GUI 会话状态检查，只有原生选目录时的前台焦点保护；补门禁，再验端口占用、陈旧端点、多安装和锁屏/未知状态 | CV02 |
| 目标与配置防串题 | 客户端真机补测 | 同名不同 Workspace、发送前模型/权限漂移时拒绝发送；保留实际发送数 0 和原身份 | CV03 |
| 异常终态 | 客户端真机补测 | 最终错误、中断/取消、未知状态与原生轨迹/正式回执逐项对账，不误报完成、不当作能力零分；工具被拒后完成和终态时差已覆盖 | CV07 |
| 轨迹异常与必需证据 | 故障补测及证据审计 | 截断/乱序/重复/孤立结果/子代理混入的处理，以及缺必需轨迹时实际 grader 的拒绝证据 | CV11、GV03 |
| 候选材料边界 | 材料验证及证据审计 | 缺文件、同名不同内容、Git/二进制/受限链接等；r33 冻结前后写入漂移已通过 | CV13、GV04 |
| 评分结果发布中断 | 公共组件故障补测 | submission 发布窗口中断、原子发布与恢复；已有重复导入、冲突拒绝测试按同版本复用 | CV14 |
| 报告分母核验 | 公共测试与 Qwen 回传接线审计 | 对齐已有有效零分/评测异常/未评分测试与正式回传、报告分母，保留有效性和缺失值语义 | GV06 |

锁屏缺口依据：[Qwen probe](../../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/probe.mjs)、[执行入口](../../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs)和[原生文件夹选择器](../../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/select-folder.swift)；`frontmostApplication` 焦点检查不等于锁屏检测，共享组件存在能力也不等于本 Driver 已接入。

先完成前三项；后四项优先引用同 revision/运行内容的公共测试与已有真实材料，只补缺失分支。成功的五题执行、Token、评分报告无需为文档收口重跑。实际模型 ID 和未支持的可选指标继续披露 unknown/null；Apple Silicon、Windows、60 题全量及无人值守重启不作为当前 Intel 值守范围的前置门槛。


### QwenWork General 验收逐项记录


本轮目标为 **macOS x86_64 / QwenWorkCN 1.2.0 / 值守控制 / UI 单槽 / 默认三路 / Codex gpt-6-sol high**。不声明 Apple Silicon、Windows、60 题全量、自动批准未知授权、活动客户端自动重启或无人值守自动抢锁。下表 `PARTIAL` 包括尚缺分支证据，不能当作不适用。实际模型 ID、Cache Write、reasoning Token、HTTP attempts 继续为 unknown/null，不以这些可选字段阻断有效评分。

| 验收项 | 实现/自动化证据 | QwenWork 真机证据 | 当前结论与剩余项 |
| --- | --- | --- | --- |
| CV01 包与隔离 | prepare/release/layout 正反例；独立七 Skill 闭包 | r21/r23/r27 仓库外 prepare/verify、execution/scoring 分离 | PASS，后续发行仍逐包验 SHA |
| CV02 只读探针 | loopback、身份、快照、Token 开关门禁 | r27 当前 PID/端点、空闲与活动两种 probe，活动启动拒绝 | PARTIAL；锁屏/GUI 会话检测为当前实现缺口（仅有选目录前台焦点保护）；补门禁，并逐项验证端口占用/陈旧端点/多安装/锁屏负例 |
| CV03 UI/配置/Prompt | 唯一语义控件、项目/Workspace、配置漂移与发送禁用反例 | r19 未发送即暂停；r21/r23 一次发送；r28 同名导航/页脚定位反例 | PARTIAL；同名不同 Workspace、模型/权限不符的目标客户端负例未齐 |
| CV04 发送中断 | intent/reservation/invoking、不确定不重发，缺失/歧义 session 反例 | r25 部分现场；r26 发现队列缺陷；r27 修复后恢复并正式收口 | PASS（值守基础范围）；r25 不当作有效执行 |
| CV05 owner/竞争 | 活锁拒绝、两个 Driver/恢复者竞争、旧归档保护、字节漂移拒绝 | r27 两把锁精确归档，原 queue/attempt 恢复 | PASS（显式值守恢复）；不承诺无人值守抢锁 |
| CV06 断连/重启 | Driver 非正常退出保留基础设施错误、显式 resume | r28/r29 CDP 断开→暂停→重连原 session；r27 活动任务拒绝 Token 重启 | PASS（断连安全暂停范围）；客户端实际重启与 Codex 重启未验/未声明 |
| CV07 原生终态 | 完成/失败/取消/未知分开；不按文件稳定判断完成 | 文件任务 r21/r23；纯回复题正式 collect/report；r28 问卷完成 | PARTIAL；r32 已验工具权限拒绝后完成，r35 已验终态时差；最终错误等剩余真机分支继续对账 |
| CV08 待交互 | 精确会话/问卷页脚；unknown/approval/manual pause 反例 | r30 自动跳过至完成；r32 原生高危卡片自动暂停，人工拒绝后原 session 完成，设置已恢复 | PASS（声明范围）；不提供自动批准白名单 |
| CV09 清理/冻结 | 通用 finalizer、静默窗口、残留/漂移拒绝 | r24 优雅终止与目录外对照；r33 原 CLI 验证持续残留拒绝、迟到写入拒绝、TERM→KILL、迟到子进程和冻结后漂移 | PASS（当前 macOS 收口分支）；本方对照受保护，测试进程已退出。自然残留复现不另设门禁 |
| CV10 串行/并发 | 单 UI 槽、三后台槽、补位、同 attempt 恢复 | 三题单槽；r21 五题原生峰值 3、补位 2；r23 另批峰值 2 | PASS，峰值不足不计能力异常；不外推更高并发 |
| CV11 原始轨迹 | 一致 SQLite 备份、session/cwd/Prompt、缺失/冲突拒绝 | r15/r16 热写故障恢复；r21/r23 正式原始/标准轨迹 | PARTIAL；截断/乱序/孤立结果/子代理混入须逐分支核对覆盖 |
| CV12 指标 | 精确 runtime Profile、逐 request ID 与 turn 终值对账、掩码零不发布 | r22/r23 核心 Token、请求/工具、原生/流程耗时；旧批次 null 保留 | PASS（已声明字段）；可选未知量不补零 |
| CV13 候选与证据 | 通用候选/manifest/hash、越界/链接和漂移拒绝 | r21/r23/r27 正式 freeze + verify-only | PARTIAL；r33 已补目标路径冻结前后写入故障，缺文件/同名不同内容/受限链接等分支继续核对索引 |
| CV14 评分/回传恢复 | 独立 attempt、发布/重复导入/冲突拒绝的公共测试 | 三题 Judge capacity 原 thread 恢复；r20 sol 独立重评分；r21/r23 return/import | PARTIAL；submission 发布窗口中断的本范围证据待核对 |
| CV15 正式闭环 | 七阶段契约与独立发行 | r21 与 r23 各自同发行执行→首次 collect→评分→回传→导入→报告闭环 | PASS；r27/r28 新故障样本按变更影响复验，不改写旧报告 |
| CV16 平台 | 平台显式为 macos-x86-64，Token Profile 精确 runtime | QwenWorkCN 1.2.0 / SDK 1.0.46；r21–r35 | PASS（本平台）；其它平台 NOT_RUN |
| CV17 路径预算 | SDK 纯编码能力确认、实际 getconf 限制、原始/编码后字节预算、目录权限/链接检查 | r31 中文/空格真实路径与原生编码匹配；最长 ID 62 字符预检；五类负例均发送 0 | PASS（macOS 当前编码能力）；未知编码实现仍拒绝，未外推其他平台 |

| General 项 | 当前证据 | 结论/剩余项 |
| --- | --- | --- |
| GV01 准备与阶段边界 | r21/r23/r27 prepare/verify 与独立执行/评分包 | PASS |
| GV02 文件/纯回复 | support_handoff、temperature 与 colleague_leave_reply 正式 collect | PASS |
| GV03 工具轨迹 grader | 五题中的轨迹题与自动规则、原始 call/result 采集 | PARTIAL；缺必需轨迹拒绝需与实际 grader 逐项关联 |
| GV04 Git/二进制/链接与冻结 | 公共 exact-all freeze/链接反例，Qwen verify-only | PARTIAL；本客户端相应材料与故障样本需补索引 |
| GV05 三种评分 | r21/r23 automated、hybrid、llm_judge，固定 sol/high | PASS；本轮只声明 Codex 语义后端 |
| GV06 分母与失败隔离 | 公共异常/缺证据/零分测试，r20 独立重评分、旧评分保留 | PARTIAL；已有公共有效零分/异常/未评分测试，需与 Qwen 正式回传接线和分母对应收口，不要求为补索引重复运行模型 |
| GV07 阶段恢复与报告 | r21/r23 submission、return/import、同源 JSON/Markdown/Excel | PASS |
| GV08 小批/并发 | r21 原生三路五题，r23 五题核心 Token、同机闭环 | PASS（固定五题/本机）；不声明跨机或全量 |

因此仍是“主流程有限可用、加固进行中”，完整接入任务保持 IN_PROGRESS。本轮已补齐 CV17、CV08、CV09 的上述重点；其余 PARTIAL 行按[剩余七项](#qwenwork-剩余生产准入事项)分别补实现、真机负例或公共证据审计，不以本轮三项通过替代全部准入。上述矩阵为人工证据审计，不代表已有自动符合性校验器。

### DoubaoWork 接续范围与验收记录（2026-09-24）

范围：macOS x86_64 / DoubaoWork 2.31.3 / 本地 / 值守。用户在本轮手动从 2.28.12 更新；新进程已重新只读核验。共享源码为 `tools/report/e2e-shared/doubaowork/`，两个 execute Skill 与 General collect 按组件清单装配，Web 与 General 的包校验/正式回执 adapter 独立。当前版本均为工作区开发实现，运行内容以各阶段的 ZIP/content SHA 为准。不得把基线 revision 或下表的自动化测试写成生产 PASS。

C01–C19 全部适用；G01–G07 全部纳入 General 接入；W01–W06 全部纳入后续 Web 接续。未声明 Windows、Apple Silicon、无人值守自动重启/抢锁和自动批准未知交互。UI 槽固定 1；开发队列允许 1–3 个执行槽，默认 1，原生并发须独立验证。General S1 默认模型模式的实际显示值为“自动 高”；底层模型版本未知。S1 仅自动规则，不调用语义 Judge；后续语义配置在批次中冻结为 `gpt-6-sol/high`。

事实与包原件索引见[接续证据](../general-e2e/evidence/doubaowork-macos-general-20260924/README.md)。以下为当前唯一进度，不继承旧 SLOT 或旧 canary。 r30–r37的新故障证据详见同目录的发送恢复、清理/账本、交互/重启与并发索引。r37原包的内部Driver标记仍为0.6.8，r37b只修正为组件目录声明的0.6.9并重建摘要，行为代码无差异；原包/回执保留，不称r37b重新执行通过。

| 验收项 | 当前实现/证据 | 当前结论与接续 |
| --- | --- | --- |
| CV01 包/隔离 | r37 General execute0.11.9/collect0.8.9、Web execute1.17.9独立ZIP；r37b修正内部Driver版本标记为共享目录的0.6.9，19份文件三路同源；完整General候选suite已构建 | PASS（本地装配/独立包）；r37b未发布，版本标记修正不算新执行闭环 |
| CV02 probe | 2.31.3应用/监听者/CDP；r28 foreign/关闭端点拒绝；r34真实第二安装副本连原安装端点，在CDP前拒绝、发送0；r37受控重启后General/Web独立probe通过 | PARTIAL；多安装负例已补；锁屏真机负例仍待齐 |
| CV03 目标/配置/Prompt | 云模式、项目残留、编辑器差异均发送0；r34真实UI在send intent后切换权限，最终发送门禁拒绝、发送0；原生Prompt/project/workspace同身份 | PARTIAL；最终配置漂移已验；同名不同完整目录实际UI负例仍待齐 |
| CV04 发送中断 | r30/r31/r33在intent前、intent后、点击前、点击返回后、接受确认后真实SIGKILL；有发送沿原attempt恢复一次，无发送只读暂停；r33明确零发送重试新attempt并首次collect/finalize/verify | PARTIAL；恢复不补造click_returned_at；r30执行/r31采集属跨版本；点击调用内部中断等未覆盖窗口不外推 |
| CV05 锁/竞争 | 跨General/Web全局UI锁；单题owner写journal、同机PID生命周期验证、两次fresh空闲检查、原inode独占归档、journal字节不变；r31活动原生请求时恢复拒绝 | PARTIAL；仅有owner证明的单题受控恢复；托管队列owner、旧无证明journal和完整跨入口UI竞争仍未准入 |
| CV06 断连/重启 | r31仅断开Driver自己的CDP，先持久化清除旧完成再连接；collector拒绝，重连同attempt且不重发；r37原生前台空闲但仅本测试orphan残留时，精确身份受控重启后前台/后台/pending均0 | PARTIAL；受控重启只作现场清理证据，不算无人值守或活动生产任务重启恢复 |
| CV07 终态 | 正常原生Success映射；r37新增dispatcher.current/pending核验，前台完成但后台交付活动保持NEEDS_ATTENTION；同会话/目录/请求ID匹配的活跃peer才可放行 | PARTIAL；r35真实orphan已阻断新发送与原题完成；原生最终错误/取消Profile仍待验 |
| CV08 待交互 | r34陌生可见弹窗拒绝且保留，不再通用Escape；r35真实文件授权位于CDN iframe，侧栏pending-confirmation及原生10080/scene2/actions1010/1011绑定请求；观察标记持久保留，自动collector拒绝 | PARTIAL；未批准、未写外部标记文件、fixture不计分；真实追问及人工介入正式回执仍待验 |
| CV09 清理/冻结 | r18精确TERM/KILL与对照、r19迟到进程；r33真实ps/lsof配合时序barrier覆盖父进程退出后子进程重挂；目录inode替换拒绝且对照存活；r31真实执行材料finalizer遇cleanup失败拒绝发布，恢复原inode后verify通过 | PARTIAL；不把时序注入称完全无注入；PID复用等未获本范围真机证据的分支仍保留 |
| CV10 串行/并发 | r11三题串行；r28五题原生峰值3与补位；r37新后台门禁下两题各一次发送、原生峰值2，首次collect/finalize/verify均complete | PASS（上述固定样本/本机）；不外推更高槽位、跨机或全量 |
| CV11 原始轨迹 | 显式trajectory、started/settled和uploaded账本对账；r26/r28完整轨迹；r31实际约35分钟延迟后首次collect/finalize/verify，5条记录均在原TTL内首次保存，采集时已超过TTL阈值 | PARTIAL；此次原生Map仍保留5条，未观察真实淘汰；不等于35分钟执行任务；旧partial不改写 |
| CV12 指标 | r28五题任务383s/流程395.3s/工具23次，覆盖5/5；r37两题任务32s/8s、流程35.428s/10.223s、工具6/0均可核验；延迟采集等待未混入执行耗时 | PARTIAL；既有26份轨迹/8380行文本审计未见累计Token，二进制日志未解码；Token/模型请求/重试仍null，窗口占用不换算 |
| CV13 材料/候选 | 通用exact-all、General保留Git；r28候选篡改/原轨迹缺失/越界链接/source迟到写入/receipt漂移拒绝；r31实际cleanup故障不发布候选，r33重试与r37两题首次冻结/verify通过 | PARTIAL；Git/二进制实料及发布窗口仍待齐 |
| CV14 评分恢复/回传 | r28三题独立sol/high自动创建评分任务，verify-score均通过；正式return/import和重复导入幂等已验；公共评分编排19/19 | PARTIAL；发布窗口中断和本范围冲突选择待齐；迁移batch副本的MANIFEST_DRIFT拒绝不算幂等证据 |
| CV15 新发行完整闭环 | r28五题在原suite完成执行→首次采集→automated/hybrid/llm_judge→回传→导入→三种报告；5/5有效，均分96.5 | PASS（r28固定五题/本平台）；report0.5.4单独修正显示舍入，原始分数/分母/资源/lineage不变，旧报告保留；不替代加固或全量准入 |
| CV16 平台 | 当前仅 macOS x86_64 / 2.31.3 | IN_PROGRESS；其他平台 NOT_RUN，不外推 |
| CV17 路径 | r27真实getconf NAME_MAX=255/PATH_MAX=1024，按UTF-8字节及终止NUL检查；中文/空格项目准备阶段真实选择回读发送0，随后S2一次发送并完成首次采集/评分；数据集最长ID62字节预算；6类真实文件系统负例发送0 | PARTIAL；已覆盖已知控制/原生路径，任意未来候选文件仍由collector验证；最长ID实际UI/运行与其余平台未外推 |
| GV01 准备/隔离 | r28固定五题独立execution/scoring包，真实准备/首次采集与私有评分；r29候选构建校验 | PASS（固定范围/本机）；未发布生产分发 |
| GV02 文件/回复 | r28 S1/S2/S3文件产物与S4/S5纯回复均正式收口、独立评分 | PASS（固定五题/本机） |
| GV03 必需工具轨迹 | r12 S2过程grader有效1.0；r26 S3首次完整工具与原规则/语义1.0；r31实际延迟采集仍complete；r37文件/纯回复均首次complete | PARTIAL；真实原生淘汰未发生，混合来源缺顺序仍拒绝或partial |
| GV04 候选类型 | 复用通用冻结，不套 Web 禁止 Git 策略 | IN_PROGRESS；Git/二进制/链接分支待验 |
| GV05 评分类型 | r28同发行automated S1/S2=1.0；hybrid S3=1.0；独立sol/high的llm_judge S4=0.95、S5=0.875，均verify-score | PASS（固定五题/本机）；不等于完整生产准入 |
| GV06 分母 | r19保留全集5题、3有效/2未评分；r28全集5题、5有效/0未评分、均分96.5；资源各自覆盖，未知Token不补零 | PARTIAL；公共真实零/异常测试已验，本范围真实异常组合仍按证据收口 |
| GV07 阶段恢复 | 原attempt只读恢复；r28分两次首次采集后完整回执、三题独立语义、submission/return/import/三种报告，重复导入幂等 | PASS（已验主链路）；发布中断仍在CV14待验 |
| GV08 小批 | r28当前核心五题三槽、原生峰值3与补位；首次collect/verify5/5 complete；三种评分及回传/报告完成 | PASS（固定五题/本机）；不外推完整60题或其他平台 |
| WV01–WV08 | 共享源码三份vendor保持一致；r37 General/shared67/67、Web64/64；r37b Python发行/布局21/21；独立Web包真机只读probe通过，正式receipt/batch路由仍拒绝 | IN_PROGRESS；本轮仅受影响入口回归，Web正式闭环及每项独立验收未完成 |


### 5.5 进度更新规则与接续

新增记录须提供日期、场景/Harness/OS、源码和包身份、task/attempt、真实断言、失败或未验证范围及 evidence 链接。公共同版本回归可引用；客户端 UI、原生身份、终态与清理须有本客户端证据。更新本文的对应状态行，不向技术方案、指标文档或 README 复制第二份待办表。

新任务从本契约的当前进度继续：先核对 Git/源码/发行和本机现场，再做当前未完成项；已通过的五题、Token 与报告不为整理文档重复运行。旧任务卡、SLOT 和 worktree 交接命令只用于历史追溯。用户给出的执行授权与范围继续按当前任务约定，不由历史档案追加确认流程。
