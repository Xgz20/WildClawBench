# 记忆场景端到端评测

首版实现了 20 题数据集、两种条件的任务链计划、逐操作发送意图和观察恢复、原生证据交接、检查点评分导入、场景级配对报告，以及复用四端 General 只读探针的预检入口。

**当前分为配置自动化、原生执行和记忆效果三层准入。** 已增加四端原生入口、可恢复的逐操作证据和配置切换／恢复探针；原生执行仍在逐端真机验收，不能由配置开关可用推导记忆已经形成。`advance` 不会调用模拟 Driver 生成真实客户端成绩。操作者可以用 `intent → import-receipt` 交接原生证据，或使用冻结的原生 Profile。

被评测客户端固定为 AStudio（内部 ID 为 `AstronStudio`）、WorkBuddy、QwenWork、DoubaoWork。**Codex 仅作为调研参考，配置操作、Profile 与批次 CLI 均不接受 Codex；不得操作其记忆开关或数据。**

**2026-10-21 AStudio默认周期追加：** 同一合成单元自然闲置超过6小时后，默认Stage1实际形成1份非空输出、
另1项JSON解析失败；Stage2消费有效输出后自然完成，经典bash4/4 exit0，130份策略保留原生SBPL且仅追加deny。
已用新维护视图/租约保留同一case×repetition状态，没有重发旧UI请求、复制运行历史或改变时间戳。
后续修复已存在会话的工作区绑定并完成自动产物UI读回：3次read、2次glob、0写入，
准确从生成的rollout summary取回合成编号，未读取原手工笔记正文。原零点击失败保留，实例正常退出。
Stage1的两个来源仍有JSON解析错误；不能将本轮执行/读回通过扩展成全部自动记忆输入或正式评分准入。
原件、失败和后续接续见[默认门槛下自动抽取与整理](../docs/research/agent-memory/AStudio默认空闲门槛下自动抽取与整理实测-20261021.md)。

**2026-10-21 WorkBuddy 真实桌面追加：** 已接入签名客户端的私有数据目录、五条原生RPC管道和OS文件边界，
真实后端/原生工作进程的合成访问检查通过，并复用当前账号的MaaS自定义 `custom-local:xopglm52` 与high思考配置。
内置GLM-5.2没有被当作该自定义路由的替代。新批次r4七步链已完成7/7；学习后回忆通过，
遗忘后两次回复仍泄漏旧编号，工作区笔记和日志均有残留。渠道为实际文件工具写入的工作区Markdown，
不推导原生自动记忆形成。随后A1→B1→A2共9次UI请求的跨用例/跨重复隔离实测通过，
15项旧单元文件操作均EPERM，旧笔记保留；验收限于已观察工作区文件渠道和OS边界，正式20题未启动。
启动观察失败、同实例恢复、权限条件和剩余Profile/Driver绑定见
[真实桌面接入记录](../docs/research/agent-memory/WorkBuddy真实桌面OS隔离接入与MaaS模型复用-20261021.md)。
批次绑定、Unix IPC/PTY修复、七步结果和正常退出见
[批次门禁与真机记录](../docs/research/agent-memory/WorkBuddy批次门禁接入与Sidecar兼容修复-20261021.md)。
三单元固定查询、完整证据复算、限制及退出恢复见
[跨用例与跨重复隔离验收](../docs/research/agent-memory/WorkBuddy跨用例与跨重复记忆隔离验收-20261021.md)。

本机首轮证据与剩余准入项见[实施与首轮验证记录](../docs/research/agent-memory/四Harness记忆自动化评测实施与首轮验证记录-20261015.md)。四端配置往返均已通过并恢复；WorkBuddy、千问各完成一组真实 C0/M+，分别观察到存档声明缺少可见写入、daily 保存后目标事实未留存。豆包新版目录复核仍阻断发送，不能将配置通过计为原生记忆链路通过。

**2026-10-16 更新：** AStudio 指定配置已验证专用工具、实际笔记写入和新会话回忆；豆包新版目录复核已解决并完成 C0/M+。v2 格式、共享代码影响、回归基线及恢复记录见[优化实施与三个问题澄清](../docs/research/agent-memory/记忆评测优化实施与三个问题澄清-20261016.md)。上段为首轮历史状态，不覆盖旧失败记录。

**同日后续：** 定向遗忘 canary 的三端行为复查完成，WorkBuddy 另发现工作区日志残留；AStudio 原生 turn 中断，未进入学习／遗忘阶段。完整环境重置与周期后无再生成均未验收，正式 20 题未启动。渠道区分、75 项 Python／34 项 Node 回归及配置恢复见[定向遗忘与重置准入验证](../docs/research/agent-memory/记忆定向遗忘与重置准入验证-20261016.md)。

**2026-10-18 更新：** 新增 opt-in v3，普通 `run` 已支持清理前精确回忆和证据绑定的渠道审核门禁；报告分别展示行为、已知文件残留、旧来源、真实周期和环境重置。新增 [v3 canary](../tasks/memory-e2e/canaries/scoped-forgetting-v3.json) 的 C0 为一次查询，M+ 六次，共七次；v1/v2、正式20题与旧批次均保持原范围。实测与限制见[准入门禁与渠道分层实施](../docs/research/agent-memory/记忆评测准入门禁与渠道分层实施-20261018.md)。

**同日真机追加：** WorkBuddy 实际回忆正确但带说明文字，旧 v3 门禁按格式暂停；新 [v3.1 canary](../tasks/memory-e2e/canaries/scoped-forgetting-v3.1.json) 显式允许一个完整 JSON 对象，旧批次不重解释。千问1.3.1改用单一全局读写开关，并增加 SDK SQLite 原生证据来源；豆包2.32.4的新调度器尚未准入。该阶段实测范围见实施记录第7节；后续完整串行结果见下面追加。

**同日完整串行追加：** WorkBuddy→QwenWork各完成v3.1七次Prompt、回忆与渠道两道门禁，共14次请求。两端的遗忘后两次回复均泄漏旧值：WorkBuddy操作记录与日志仍有残留；千问已知Markdown文件无目标，但原生memory_search仍返回旧片段，首次JSON填“未知”也未避免说明文字泄漏。千问一次UI身份暂停经同操作观察恢复，没有重发。结果与分母见[实施记录第8—10节](../docs/research/agent-memory/记忆评测准入门禁与渠道分层实施-20261018.md)，均为未正式评分的单链canary，正式20题仍未启动；两端收口后没有继续派发AStudio或豆包。

**2026-10-19准入加固：** AStudio模型显示名通过账号范围内的网关目录映射到原生slug核验，并增加已加载客户端传输状态的发送前门禁；真机connecting状态已实现零点击拦截。三个独立记忆关闭控制批次的完成数分别为1/3、0/3、1/3，不能拼成稳定运行证明，尚未开启记忆。豆包安装版本更新为2.32.12，缓存调度模块仍未适配，未派发题目。修复、观察恢复、控制失败和测试边界见[实施记录第11节](../docs/research/agent-memory/记忆评测准入门禁与渠道分层实施-20261018.md)。General/Web共享源码未改动。

AStudio传输状态读取只准入已核验的renderer源码指纹，客户端资源变化须重新核验。open仅是发送前提，原生session、turn、Prompt、模型目录和权限校验仍保留；未知点击继续只观察，不自动重发。

默认数据集位于 [memory-mixed20-v1](../tasks/memory-e2e/memory-mixed20-v1/manifest.json)，由带来源追溯的开源样本和自建场景组合；原自建 [diagnostic20](../tasks/memory-e2e/memory-diagnostic20-v1.json) 保留。它使用独立多会话契约，不是旧单 Prompt Markdown 任务。校验入口为 `python3 -m eval_memory_e2e validate-dataset`，不送入 Markdown/frontmatter 校验器。

**2026-10-19 观察与准备加固：** 已发送且点击回执完整的AStudio原操作可只读沿原生库／rollout恢复观察，保留发送前账号依据并明确标记当前账号未重查；新派发仍走完整桌面UI。新Profile冻结30秒发送前RPC恢复预算和120秒原生接受观察窗，旧Profile不升级。新增Memory专用项目导航恢复、刷新后只读等待、CDP准备诊断与被动DOM发送事件取证；General/Web共享源码没有修改。旧成功C0只读重观察与一个新C0均已完成；完整三步控制仍未通过，一次点击后原生接受未确认，后续暂停。具体结果与豆包队列采集缺口见[实施记录第12节](../docs/research/agent-memory/记忆评测准入门禁与渠道分层实施-20261018.md#12-2026-10-19astudio-观察传输与项目准备加固)。

**同日焦点恢复：** 用户确认采用核验后清理测试草稿、保留旧失败并新建独立项目重跑。已完成精确草稿清理，增加发送前的前台PID／页面焦点等待和按下前即时检查；新AStudio Profile冻结60秒焦点等待、30秒CDP读取和300秒Driver控制预算。焦点等待不主动激活应用，首次连接准备的激活在UI锁内进行。独立三步基础控制已完成3/3，回复391、391、437；每条仅一次发送且DOM与原生证据齐全。期间一次namespace只读核验异常沿原操作恢复，未重发Prompt；用户配合保前台，仍不作为无人值守或记忆成绩。实测状态与限制见[实施记录第13节](../docs/research/agent-memory/记忆评测准入门禁与渠道分层实施-20261018.md#13-2026-10-19桌面焦点门禁与清草稿后独立重跑)。

**同日记忆开启canary：** AStudio独立v3.1批次完成2/7步：C0两项均未知，M+通过原生add_ad_hoc_note写入两条合成事实并回读。第3条新会话查询真实触发一次click／submit，但未找到原生接受记录，后4步未派发；跨会话回忆与遗忘不可评，渠道审核尚未导入，报告保持UNSCORED。两份配置的受控记忆字段已恢复原值、总开关回读为false；未验证已有会话热加载，合成笔记仍保留。同期应用层准入与派发证据仍需补齐，不能归因为焦点、额度或空编辑器。原件、分母和恢复边界见[实施记录第14节](../docs/research/agent-memory/记忆评测准入门禁与渠道分层实施-20261018.md#14-2026-10-19astudio-原生记忆写入成立新会话查询提交后阻断)。本轮仅更新文档，未改General/Web源码，正式20题未启动。

**迁移接续：** [M芯片Mac迁移与接续Prompt](../docs/research/agent-memory/M芯片Mac迁移与接续Prompt-20261019.md)提供双远程分支拉取、项目内worktree、已知home／Python／x64内核路径适配项和可复制的新会话指令。新机须重新核验架构、客户端版本、账号和原生执行，不恢复旧机未知提交，不将专用机器等同于已解决全部发送阻断。

## Apple Silicon 迁移

**当前发送门禁：** 上轮AStudio曾自行尝试搜索Codex记忆目录，原失败保留。默认新Profile仍在非目标记忆访问隔离未核验时阻断。AStudio现可通过 `--astudio-boundary-lease` 绑定已完成合成拒绝测试、实际进程OS检查的 `macos-seatbelt-astudio-backend/v1` 租约；控制器在Prompt INTENT前、原生Driver入口及按下发送前检查真实生效状态。手填verified或布尔标记不能代替这些检查，已有操作只读观察仍保留。

额外OS限制覆盖AStudio安装包后端、内核及工具子进程的直接文件访问；UI保留产品原有Chromium沙箱，不声称整机／所有外部代理隔离。合成验收未访问Codex真实记忆。新七步canary已完成7/7，但追加撤销笔记后旧值仍在最后查询泄漏，保持UNSCORED；正式20题未启动。实现、失败尝试、52项合成文件操作、实际进程证明、105项Python／82项Node回归及配置恢复见 [OS隔离验收记录](../docs/research/agent-memory/AStudio-OS非目标记忆隔离验收-20261019.md)。其他三端尚无该适配器，默认仍阻断。

**2026-10-20 跨用例与跨重复隔离：** 新增同账号AStudio记忆单元（一个用例×一次重复），单元内C0/M+多会话保留记忆，跨单元切换整套本地存储与源会话，OS拒绝普通home及其他单元/旧证据。A/r01→B/r01→A/r02完成9/9真实UI Prompt，使用相同项目和问题；三单元均能回忆自己的新值，后续单元完整轨迹及本地扫描无先前值。旧笔记保留且15项实际跨单元访问拒绝、24项实际进程OS查询通过；三个单元的156项基础合成操作、Python110项、Node87项通过。新Profile拒绝多用例/重复共享同一单元，采集临时副本也进入受保护控制目录。

该验收仅覆盖本机现有 **AStudio3.5.0 / ACode1.0.5-rc.3** 的显式记忆条件。自动整理实际遇到嵌套`sandbox-exec`失败；`generate_memories=false`只限制新线程抽取资格，仍有全局整理作业，不能称为完全关闭后台或自动记忆准入。三个通过单元等待后台自然结束再退出；早先失败诊断单元的异常行和证据保留。原配置、登录和普通状态库未变，临时端口关闭；所有报告UNSCORED，正式20题及一键多单元外层调度未启动/未验收。完整边界、失败恢复与证据见 [跨用例与跨重复隔离验收](../docs/research/agent-memory/AStudio跨用例与跨重复记忆隔离验收-20261020.md)。

2026-10-20继续定位：原生路径权限词法求交在规范化显式符号链接授权时出现4次合成越界读取，执行服务代理因此仅保留为诊断原型，禁止应用接入。完整保留原生SBPL、仅追加外层显式deny并安装一次的原理通过76项合成检查；当前安装内核仍缺少已准入的生成后组合入口，真实自动整理继续阻断。清空记忆或新建单元可以处理已验证范围的跨轮污染，不能修复二次沙箱安装错误。见 [嵌套沙箱定位与组合验证](../docs/research/agent-memory/AStudio自动整理嵌套沙箱定位与组合验证-20261020.md)。

本机适配、3/3基础控制、7/7七步canary、旧值再现、边界违规和恢复原件见 [M芯片Mac迁移适配与实测记录](../docs/research/agent-memory/M芯片Mac迁移适配与实测记录-20261019.md)。七步完成不等于合规准入或遗忘通过。

2026-10-19 起，memory 专用层按操作系统当前账号解析 home、AStudio 两个 home、千问数据库／轨迹、WorkBuddy 存储及统一 UI 锁；不读取 Codex 记忆目录，也不接受外部 home 覆盖。AStudio 配置读回从安装包选择架构匹配的 arm64／x64 或 universal 内核，并保留路径、版本及 SHA。

新 `native-profiles` 冻结本机、架构、路径、Python、Node 和可用的 AStudio 内核身份；准备与加载批次均检查漂移。跨机器应新建 Profile 和批次，不迁移旧机未知操作。旧 Profile 不回写；此次修复仅涉及 memory 层、其测试与独立 canary，未修改 General/Web 共享源码。

先选择本机实际 Python 3.11+；Node 单独运行测试／驱动时设置 `MEMORY_E2E_PYTHON` 为该解释器。`run` 自动传递控制器的 Python。默认系统 Python 版本不足会在访问客户端数据之前被拒绝。

`tasks/memory-e2e/canaries/runtime-control-v1.json` 是三次 UI 运行控制：C0 一次，M+ 两次，预期391、391、437；须使用 `requires_enabled_memory=false` 的独立控制 Profile。该控制不测记忆，不能计入正式20题成绩。

使用已经选择的本机Python3.11+，在新目录执行以下准入。`launch` 不会退出或重启已有客户端；先只读确认原生任务及相关后台作业状态，接受未知的旧操作只观察，再从客户端正常退出。租约只可启动一次；本次验收后已恢复普通启动，旧租约不能复用。

```bash
"$MEMORY_E2E_PYTHON" -m eval_memory_e2e.os_boundary selftest \
  --lease-dir "$HOME/debug-workspace/e2e-evaluate/memory-e2e/os-admission-new/lease"
# 核验空闲并正常退出AStudio后再launch；不强退任务。
"$MEMORY_E2E_PYTHON" -m eval_memory_e2e.os_boundary launch \
  --lease-dir "$HOME/debug-workspace/e2e-evaluate/memory-e2e/os-admission-new/lease"
"$MEMORY_E2E_PYTHON" -m eval_memory_e2e.os_boundary attest \
  --lease-dir "$HOME/debug-workspace/e2e-evaluate/memory-e2e/os-admission-new/lease"
"$MEMORY_E2E_PYTHON" -m eval_memory_e2e native-profiles \
  --astudio-boundary-lease "$HOME/debug-workspace/e2e-evaluate/memory-e2e/os-admission-new/lease/lease.json" \
  --output "$HOME/debug-workspace/e2e-evaluate/memory-e2e/os-admission-new/profiles.json"
```

## 运行环境和快速验证

从当前 checkout/worktree 根运行。编排、数据和报告只需要 Python 3.11 标准库；原生预检另外需要 Node ≥22、现有 General Driver 依赖及受支持的客户端。DoubaoWork Driver 的锁定依赖安装在其目录，未安装时预检保留进程错误，不能当成产品不支持。

```bash
python3 -m eval_memory_e2e validate-dataset
python3 -m unittest discover -s tests/memory_e2e -p 'test_*.py'
node --test tests/memory_e2e/*.test.mjs
python3 -m eval_memory_e2e selftest \
  --root $HOME/debug-workspace/e2e-evaluate/memory-e2e/protocol-selftest-new
```

`selftest` 执行四个场景 MEM-01、10、13、19 × 四端标识 × C0/M+，共 32 条协议模拟任务链。它不连接客户端、不调用模型，输出固定测试值。结果始终为 `FIXTURE_ONLY`；普通 `report` 拒绝把它当正式评测，只有显式 `--include-fixture` 才用于协议 QA。

输出路径必须新建，不能覆盖旧批次、证据、评分或报告。调试输出放仓库外的 debug-workspace；正式发行与分发产物另按项目的 report-workspace 边界管理。本版是仓库入口，未提供七阶段独立 Skill 发行包。

## 当前账号的预检与对照

用户已明确指定使用四个客户端当前登录的账号。配置固定 `account_policy=current_signed_in_account`、`reset_policy=synthetic_test_facts_only`，不要求另建账号，也不允许以评测名义清空日常账号记忆。

`native-profiles` 新生成的 AStudio Profile 要求实际记忆配置开启；配置不满足时停止在 Prompt 发送之前。C0 表示未提供该场景的学习历史，不等于关闭记忆开关。配置开关恢复也不等于清空记忆或清除已有会话上下文。

```bash
python3 -m eval_memory_e2e scan \
  --output $HOME/debug-workspace/e2e-evaluate/memory-e2e/client-scan-new.json
python3 -m eval_memory_e2e native-preflight \
  --output-dir $HOME/debug-workspace/e2e-evaluate/memory-e2e/native-preflight-new
```

`scan` 只读取安装元数据和 loopback CDP 版本。`native-preflight` 复用现有四端 General 只读探针，保留原始 JSON、stdout/stderr、入口源码和原件 SHA。二者都不启动／重启客户端、不发 Prompt、不重置记忆；General `PASS` 不会自动升级成 memory admission。

## 配置切换与恢复

```bash
python3 -m eval_memory_e2e config-probe \
  --roundtrip --preflight-dir /absolute/fresh-native-preflight \
  --output-dir $HOME/debug-workspace/e2e-evaluate/memory-e2e/config-roundtrip-new
```

三端 UI 探针逐项执行原值 → 相反值 → 回读 → 原值恢复，持久化每次意图与最终状态，并保留前后截图。千问关闭意识模式时会移除自动记忆控件，该控件记为暂不可观察，重新开启后再核对原值。失败回执中的 `restored` 必须按原件确认；不能仅因命令退出就假定恢复。

AStudio 没有对应 UI 入口，先验证精确应用进程与原生空闲状态，仅编辑 `~/.acode/config.toml` 及其桌面 overlay 中的记忆 feature；使用安装内核及其 `ACODE_HOME` 参数回读，再按原始字节 SHA 恢复。私有配置备份权限为 0600，不放入候选工作区；有并发编辑时拒绝覆盖。文件与安装内核回读通过，不表示已有运行中聊天已应用新配置。

配置探针不清空记忆、不发送评测提示词；被拒绝目标在访问配置文件和 CDP 之前失败。日常账号仍使用测试事实级清理。

千问记忆设置使用已核验 renderer 的意识页路由，避免误选模型菜单中的“设置”；读取前拒绝仍处于加载禁用状态的开关。WorkBuddy 原生执行仅允许关闭明确属于记忆设置的遮挡弹窗，遇到其他设置弹窗仍停止。

## 原生 Driver 的冒烟条件

```bash
python3 -m eval_memory_e2e native-profiles --output /private/native-profiles.json
```

输出冻结原生 Driver、共用组件、依赖锁定文件和原生文件夹选择器源码。AStudio／WorkBuddy 接入新建与继续会话；千问／豆包当前先验收新会话链，continue 与客户端重启需单独验收。

新 Profile 按本端字面量依赖递归冻结源码，`--harness` 执行只检查本端 Driver；共享源码和 Python 运行时仍严格检查。`run` 按 `strict_harness_serial` 完整执行一个 Harness 的全部计划，再进入下一端，同端保持原冻结顺序。待处理、基础设施异常、未知发送或准入暂停都会停止整批，其他端保持待执行；不跨客户端轮询派发或让其模型后台重叠。先前交替调试记录保留为历史，不作为生产串行条件的验证结果。

新批次同时冻结 `failure_policy=stop_batch` 和调度策略。旧 manifest 不回写；新执行日志明确记录实际串行策略。共享 UI 锁是互斥保护，不能代替 Harness 级完整串行。

新建原生批次在每条实际发送的 Prompt 中冻结相同操作边界：不访问或改动 Codex 记忆，不让其他客户端代做，不清空日常账号记忆，仅处理本轮合成档案。原始开源样本和私有答案不改写；操作边界属于本项目执行条件。旧批次不就地改题。

原生 Profile 的控制调用预算通常为180秒；本轮新增AStudio Profile为300秒，以覆盖UI准备与焦点等待。它不是模型做题时限。超时将保存部分 stdout／stderr 和原意图，只允许观察恢复。AStudio 轨迹优先绑定原始 rollout 的 session／turn／cwd／Prompt 摘要，不能把会被回收的桌面事件缓存视作完整模型轨迹。

该入口明确生成 `memory_protocol.purpose=immediate_automation_smoke`、`formal_scoring_allowed=false` 的 Profile。短观察窗只验证自动化与即时跨会话行为，评分模板入口拒绝将它作为正式能力成绩。AStudio 的历史候选与两阶段整理、WorkBuddy 的每晚整理、千问的写入／反思、豆包主动与周期记忆分别记录 formation gate；正式测量需要另行冻结相应学习条件。

UI 输入使用已核验客户端的原生前台激活和精确控件。豆包采集器支持已核验的独立模块及合并模块源码指纹，只读取已缓存模块，不调用初始化、权限或工具接口来制造观察状态；consumer witness 必须与当前源码指纹一致。未知版本继续拒绝准入。

控制器超时保留原意图；观察入口不对千问／豆包已证实零发送的旧操作启动首次发送。已完成请求沿原生身份恢复，不重发。需要恢复共享 UI 锁时，仅在精确 owner、同主机、原 owner 进程已退出、操作属于四端冻结意图时使用：

```bash
python3 -m eval_memory_e2e recover-ui-lock --root /absolute/batch \
  --expected-owner-id EXACT_UUID
```

新 Profile 中，千问/豆包可显式使用 `retry-pre-send --root ABS --episode FULL_ID`，仅恢复已证明没有原生发送意图、reservation、调用或接受的准备失败。它不适用于不确定发送；旧批次未冻结该能力时不会自动升级。配置、学习条件或题目改变须新建批次，不能借 `repair-runtime` 改题。

`run` 对同一已绑定原生 session/turn、处于 `OBSERVE_ONLY` 的操作，在控制传输异常后最多追加三次观察重试，并写入 journal。它不重派 Prompt；未绑定、新派发及原生明确异常终态保留暂停。这个控制重试预算不是模型任务截止时间。

锁恢复只归档锁并追加证据，不修改旧 journal、不停止客户端任务、不授权再次发送。源码修复通过 `repair-runtime` 留下原／新摘要，题目与 Prompt 保持冻结。

新 Profile 冻结统一的 `ui_lock_path`，不同父目录的批次也互斥；旧 Profile 未声明时保留原锁位置。`advance/intent` 在登记新发送意图前检查占用，不能把锁冲突留下的新意图误当已发送。千问控制调用超时若遗留内部 General-step attempt 锁，可用 `recover-qwen-step-lock --root ABS --episode FULL_ID --operation OP_ID --expected-owner-id UUID --probe FRESH_JSON`；它仅归档同一Memory意图的精确已退出owner，核对原配置、fresh空闲probe与journal摘要，不发送、不改journal。恢复源码与回执一并私有归档。

## v2 复杂用例与状态观察

原混合 20 题保留 v1。v2 支持可变题量、更多工作区作用域、自定义 token/整数/literal 事实、带 SHA 的公开材料及显式学习条件。示例与校验：

[v2 定向遗忘调试用例](../tasks/memory-e2e/canaries/scoped-forgetting-v2.json)是独立自建 canary，不计入正式 20 题。它包含写入、清理前查询、定向遗忘、清理后查询、中性会话及再次查询。16 日的形成门禁由外部调试控制器执行；v2 本身仍不带执行门禁。18 日新增的 v3 将门禁纳入普通 `run`，见下文。60 秒观察窗不能证明每晚／周期整理后的无再生成，也不等于全账号重置。

```bash
python3 -m eval_memory_e2e validate-dataset --dataset tasks/memory-e2e/examples/complex-memory-v2.json
```

`learning.mode` 区分 explicit、automatic、eviction。自动组采用中性边界，不额外指示保存事实；源 Prompt 仍须由用例作者保持为自然业务输入。时间窗只是观察条件，不能代替原生形成事件。当前 `native_event` 原生执行尚未准入；DAG、多账号、多智能体和任意 UI 操作步骤不在本版执行范围。

新原生 Profile 在学习前、观察中、完成后采集已知本地记忆文件的私有快照；相同状态去重。观察不完整、文件不稳定或云端不可见会显式记录，文本命中不自动转成语义分数。定向清理仍标为未验收，不再通过占位 capability 标签宣称支持。

同一客户端内先 C0 后 M+，再进入下一场景；不同重复使用不同事实。每个批次还生成新的 experiment ID，参与合成实体与事实变体生成，避免复用旧批次的事实。四端和两个条件在同一场景、同一重复中使用相同事实与测试问题。种子、experiment ID、全部实体和 Prompt 均在冻结包中保留。

该对照的结论是历史经验增益。C0 的提问本身可能进入账号历史，固定顺序也可能带来时间效应，因此不能声称严格独立状态或记忆模块开关消融。真实记忆作用域由 Driver 的原始证据声明：`verified_namespace` 或 `shared_account_cold_first`，不是由目录名称推定。

记忆渠道使用客户端自身机制并归档可见 Workspace：Agent 自己生成的笔记和文件须在轨迹／阶段快照中可查。开关、模型和专用工具配置变化须单列实验条件，不能把显式开启实验写成出厂默认行为。`mode=native` 仅表示真实客户端执行，不代表已证明独立存储层或排除了所有文件记忆。外部注入统一记忆库需要另建实验条件。

### v3：条件范围、形成前提与渠道审核

v3 是显式选择的新版本，仍为线性多会话。`conditions.C0.probe_steps` 可按原顺序选取冷启动查询；标注 `experience_gain=true` 的题必须保留全部相同 probe/checkpoint 范围，避免用不同考点做差值。评分模板只包含本条件计划内的检查点，M+ 范围不因此缩小。

`gates` 在 `before_step` 发送前生效，目前只支持 M+。`response_json_exact` 从冻结的 `source_step` 最终回复中解析两项或更多字符串字段；必须完整 JSON、键集合与预设字段值全部准确。可接受单个 json 代码块；包含答案子串、额外字段、重复键、猜测或解析失败均不通过。该检查适合合成符号事实，只证明已观察回忆，不能代替自然语言语义裁判或后台形成事件。

新用例可显式指定 `answer_format=single_json_object`，从完整回复中解析唯一完整 JSON 对象，允许外层说明文字及未闭合的 Markdown 代码块；多对象、数组、重复键和非有限数仍拒绝，字段集合和值仍精确比较。`cleanup.answer_format` 同样需要在准备时冻结。不指定时仍使用旧 `raw_json` 规则，运行时修复不会改变旧输入。

`channel_review` 要求独立审核账号画像、原生本地记忆、工作区文件或外部注入渠道。审核同时提交存储位置、写入主体、读取机制和控制开关的依据；每个判断必须引用该来源步骤的冻结原件与原文片段。本地／工作区渠道必须有相应位置的文件原件，不能仅凭回答声明。工作区文件不能单独证明账号画像。代码校验身份、引用与准入条件，审核者仍负责判断引用是否支持机制解释。

```bash
python3 -m eval_memory_e2e channel-template --root /absolute/batch \
  --episode WorkBuddy__MEM-cleanup-001__r01__experienced --gate memory-channel \
  --output /private/channel-review.json
# 独立上下文查阅 available_evidence 后填写 decision、机制字段及 evidence；不交给候选端。
python3 -m eval_memory_e2e import-channel-review --root /absolute/batch --review /private/channel-review.json
python3 -m eval_memory_e2e run --root /absolute/batch --harness WorkBuddy
```

未满足前提为 `PREREQUISITE_FAILED`，缺渠道审核为 `AWAITING_CHANNEL_REVIEW`。`run`、`advance` 和手工 `intent` 均阻止下一步发送，保留计划与空分数。审核入库后只继续尚未发送的下一步；不能重发已发送请求。有效审核不允许覆盖，错误输入另存审计记录。配置、题目或渠道条件变化须新建批次。

v3 `cleanup` 定义目标、保留项与前后 probe。报告的 `cleanup_layers` 分开记录清理前回忆、后续行为、已知文件命中、旧来源检查、周期再生成和环境重置。WorkBuddy 的工作区 `.workbuddy/memory` 与已知全局文件分别采集，位置标签不推断写入／读取机制。即使行为通过且可见文件无目标，旧会话、缓存、索引与真实周期仍保持未验证，完整环境重置不会自动准入。正式记忆评分仍受 Profile 的 `formal_scoring_allowed` 门禁控制。

## 准备一个冻结批次

```bash
python3 -m eval_memory_e2e prepare \
  --root $HOME/debug-workspace/e2e-evaluate/memory-e2e/diagnostic20-new \
  --batch-id diagnostic20-new --seed diagnostic20-new --repeats 3
```

默认生成 20 场景 × 四端 × C0/M+ × 三次重复，即 480 条计划；这只准备材料，不执行客户端、不产生分数。`--scenario MEM-01`、`--harness WorkBuddy` 可重复指定，用于另建固定范围的小批；不能修改已有 manifest 缩题。

准备结果包含：

```text
manifest.json + manifest.sha256       实验身份、模式、范围、配置、源码与输入摘要
public/<episode>/steps.json           公开阶段 Prompt，C0 只有探测阶段
public/<episode>/materials/           合法工具和业务输入，不包含评分要求
private/scenarios.json               事实变体、完整步骤、私有检查点
candidate/<episode>/<scope>/         只给被测端的业务 Workspace；v1 为 A/B，v2 按声明生成
events.jsonl                         加链式摘要的追加日志
evidence/blobs/<sha256>               冻结原件和阶段候选文件
```

公开目录与评分目录的分离用于避免误投；它不是 OS 安全沙箱。不得把整个控制根或私有评分目录作为客户端项目。准备时冻结自身实现代码；后续源码、输入、Profile 配置或证据变化会拒绝恢复。需要沿旧源码继续时，保留原 worktree 与环境。

正式语义评分须在 prepare 时用 `--judge-model` 和 `--judge-reasoning` 指定本轮实际裁判。未配置裁判的准备批次可以查看计划，但不能导入有效语义分；不能拿控制会话默认模型冒充已冻结的裁判。

## Driver 和原生证据交接

Profile 模板见 [profiles.example.json](profiles.example.json)。原生 Driver 使用 argv 数组，通过 stdin 接收 JSON、stdout 返回 JSON，不接受 shell 字符串。配置非空 Driver 时必须提供 `driver_sources`，将实际 Driver 源码路径映射到 SHA-256；恢复时核对摘要。模板保留空 Driver，直到逐端适配通过。

```bash
python3 -m eval_memory_e2e next --root /absolute/batch \
  --episode WorkBuddy__MEM-01__r01__cold
python3 -m eval_memory_e2e intent --root /absolute/batch \
  --episode WorkBuddy__MEM-01__r01__cold
```

`next` 只读。`intent` 先落盘一个唯一操作及 Prompt SHA，返回交接请求；操作者或 Driver 之后才能按该请求操作原生客户端。首先是 `prepare_namespace`，确认该合成范围的前置状态与可用能力；其后才有 `execute_step`。每个请求携带 experiment、episode、arm、scope、step、execution attempt、唯一 operation ID、完整 cwd、前序原生身份和配置。

Driver 的 `transport_action=dispatch` 只能执行一次。控制器超时、断线、异常退出或收不到接受结果时，已有意图的下一次 `advance` 只调用 `observe`，不重新发送。已知基础设施失败或产品不支持时停止该 Harness 的后续派发；原错误和所有未执行计划保留，不删除锁或篡改 journal 绕过它。

本版 execution attempt 为固定的 `a01`，不自动重试。评分也不自动覆盖旧结果。重跑需要新批次与新的实验身份；同批次多 attempt 的选择与资源累计是后续扩展，不宣称已具备 General 的全部恢复功能。

原生 Driver 回复的交换形状见 [driver-reply Schema](contracts/driver-reply-v1.schema.json)。`runner.py` 还校验跨字段语义：

- 实验、operation、profile、namespace、step 和 Prompt SHA 必须原样绑定。
- 执行完成须有新 turn、精确 cwd 与完整响应、raw trace、JSON binding evidence；new/restart_new 不能复用已见 session，continue 必须延续原 session。
- 原始 binding evidence 必须声明 native/general 来源，包含同一操作、profile、namespace、Prompt SHA 和实际配置；执行时还须与规范化 native identity 一致。不能只把模拟记录的 mode 改成 native。
- 实际版本、模型显示值、权限和非敏感账号指纹必须完整；账号指纹来自原生稳定账号身份的哈希，不保存登录凭证。底层自动路由模型可以 null，但不能把显示值当成已确认的固定模型。一个单元的实际配置和账号不得漂移。
- 重启需要独立进程生命周期证据。已有活动任务、归属未知或授权不清时转关注，不由控制器代答或取消日常工作。
- 已知后台记忆未结束时不能收口。后台不可观测时，可记录固定观察窗后行为，`background_settled=null`，`memory_observation={status: unobservable, wait_seconds: 实测值}`；等待值须满足准备阶段固定的 `memory_wait_seconds`，默认10秒。这不等价于证明记忆已写入。

外部控制器保存上述真实原件后，可以把回复 JSON 交接回来：

```bash
python3 -m eval_memory_e2e import-receipt --root /absolute/batch \
  --episode WorkBuddy__MEM-01__r01__cold --receipt /private/native-reply.json
```

每个阶段的响应、轨迹、binding、可观测记忆状态和候选文件按内容 SHA 冻结。后续候选发生业务变化不会改写前一阶段原件；控制器也不在下一轮修复 Agent 改过的工具或笔记。单阶段证据单件上限100 MiB、候选快照上限2,000项／100 MiB；超出属于采集基础设施关注，不补能力零分、不截断冒充完整证据。

## 评分与报告

```bash
python3 -m eval_memory_e2e review-template --root /absolute/batch \
  --episode WorkBuddy__MEM-01__r01__cold --output /private/review.json
python3 -m eval_memory_e2e import-review --root /absolute/batch --review /private/review.json
python3 -m eval_memory_e2e report --root /absolute/batch --output /private/new-report
```

评分模板包含私有要求，只交给独立评分上下文。每个检查点提交 `value: 0或1`、理由、被评 step ID、原件类型、SHA 和原件中的原文片段。当前评分入口校验证据与冻结裁判身份，不会自己调用 LLM。缺检查点、捏造引用、引用其他阶段、复用候选上下文或未配置裁判均拒绝导入。失败评分输入仍按 SHA 归档并登记独立 scoring attempt，报告保留 evaluation_error；修正后的有效输入不抹去旧错误，也不能覆盖已有有效分数。

高者优指标的 value=1 表示达标；旧值误用、越界和无关干扰等低者优指标的 value=1 表示事件发生，得分会反向归一化。所有必要检查点通过才算任务成功，正常候选零分仍为 valid。

每个重复先平均检查点，每个场景再平均计划内的全部重复，最后跨场景平均。缺任一次评分的场景不进入“完整场景”均值，仍展示已观测结果。经验增益只对预先标注的正向场景、完整 C0/M+ 配对计算，保留负值，bootstrap 按独立场景抽样。四端共同可评集合另列，避免各端不同缺题形成伪排名。

报告保留 valid、evaluation_error、unsupported_product、unscored 及有效/计划数量。产品明确不支持的场景不静默删除，也不与基础设施错误混为能力零分；本版主要展示覆盖与条件能力分，未提供额外业务权重的完整需求总分。内部检索 Recall@k、后台记忆资源和全周期成本尚未完整接入，保留 null/unavailable。

## 后续真机验收

复用现有 [execute-general-e2e](../tools/report/skills/general-e2e/execute-general-e2e/SKILL.md) 的原生身份、UI互斥和未知发送恢复规则，但不复用其单 Prompt journal 作为整个记忆 episode。四端多轮 Driver 必须另外验证项目/会话转换、状态形成、合成事实的定向清理和真实证据来源，然后才能进入 4 个调试场景与正式20题。

证据包括确定性测试、明确标记的模拟闭环，以及逐端真实请求与配置回执；验收范围以实施记录为准。跨重启持久性、完整清除重置与四端正式 20 题成绩尚未验收，不能由配置通过或单次真实请求推导。
