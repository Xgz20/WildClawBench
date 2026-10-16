# 记忆场景端到端评测

首版实现了 20 题数据集、两种条件的任务链计划、逐操作发送意图和观察恢复、原生证据交接、检查点评分导入、场景级配对报告，以及复用四端 General 只读探针的预检入口。

**当前分为配置自动化、原生执行和记忆效果三层准入。** 已增加四端原生入口、可恢复的逐操作证据和配置切换／恢复探针；原生执行仍在逐端真机验收，不能由配置开关可用推导记忆已经形成。`advance` 不会调用模拟 Driver 生成真实客户端成绩。操作者可以用 `intent → import-receipt` 交接原生证据，或使用冻结的原生 Profile。

被评测客户端固定为 AStudio（内部 ID 为 `AstronStudio`）、WorkBuddy、QwenWork、DoubaoWork。**Codex 仅作为调研参考，配置操作、Profile 与批次 CLI 均不接受 Codex；不得操作其记忆开关或数据。**

本机首轮证据与剩余准入项见[实施与首轮验证记录](../docs/research/agent-memory/四Harness记忆自动化评测实施与首轮验证记录-20261015.md)。四端配置往返均已通过并恢复；WorkBuddy、千问各完成一组真实 C0/M+，分别观察到存档声明缺少可见写入、daily 保存后目标事实未留存。豆包新版目录复核仍阻断发送，不能将配置通过计为原生记忆链路通过。

**2026-10-16 更新：** AStudio 指定配置已验证专用工具、实际笔记写入和新会话回忆；豆包新版目录复核已解决并完成 C0/M+。v2 格式、共享代码影响、回归基线及恢复记录见[优化实施与三个问题澄清](../docs/research/agent-memory/记忆评测优化实施与三个问题澄清-20261016.md)。上段为首轮历史状态，不覆盖旧失败记录。

默认数据集位于 [memory-mixed20-v1](../tasks/memory-e2e/memory-mixed20-v1/manifest.json)，由带来源追溯的开源样本和自建场景组合；原自建 [diagnostic20](../tasks/memory-e2e/memory-diagnostic20-v1.json) 保留。它使用独立多会话契约，不是旧单 Prompt Markdown 任务。校验入口为 `python3 -m eval_memory_e2e validate-dataset`，不送入 Markdown/frontmatter 校验器。

## 运行环境和快速验证

从当前 checkout/worktree 根运行。编排、数据和报告只需要 Python 3.11 标准库；原生预检另外需要 Node ≥22、现有 General Driver 依赖及受支持的客户端。DoubaoWork Driver 的锁定依赖安装在其目录，未安装时预检保留进程错误，不能当成产品不支持。

```bash
python3 -m eval_memory_e2e validate-dataset
python3 -m unittest tests.memory_e2e.test_memory_e2e -v
python3 -m eval_memory_e2e selftest \
  --root /Users/gzx/debug-workspace/e2e-evaluate/memory-e2e/protocol-selftest-new
```

`selftest` 执行四个场景 MEM-01、10、13、19 × 四端标识 × C0/M+，共 32 条协议模拟任务链。它不连接客户端、不调用模型，输出固定测试值。结果始终为 `FIXTURE_ONLY`；普通 `report` 拒绝把它当正式评测，只有显式 `--include-fixture` 才用于协议 QA。

输出路径必须新建，不能覆盖旧批次、证据、评分或报告。调试输出放仓库外的 debug-workspace；正式发行与分发产物另按项目的 report-workspace 边界管理。本版是仓库入口，未提供七阶段独立 Skill 发行包。

## 当前账号的预检与对照

用户已明确指定使用四个客户端当前登录的账号。配置固定 `account_policy=current_signed_in_account`、`reset_policy=synthetic_test_facts_only`，不要求另建账号，也不允许以评测名义清空日常账号记忆。

`native-profiles` 新生成的 AStudio Profile 要求实际记忆配置开启；配置不满足时停止在 Prompt 发送之前。C0 表示未提供该场景的学习历史，不等于关闭记忆开关。配置开关恢复也不等于清空记忆或清除已有会话上下文。

```bash
python3 -m eval_memory_e2e scan \
  --output /Users/gzx/debug-workspace/e2e-evaluate/memory-e2e/client-scan-new.json
python3 -m eval_memory_e2e native-preflight \
  --output-dir /Users/gzx/debug-workspace/e2e-evaluate/memory-e2e/native-preflight-new
```

`scan` 只读取安装元数据和 loopback CDP 版本。`native-preflight` 复用现有四端 General 只读探针，保留原始 JSON、stdout/stderr、入口源码和原件 SHA。二者都不启动／重启客户端、不发 Prompt、不重置记忆；General `PASS` 不会自动升级成 memory admission。

## 配置切换与恢复

```bash
python3 -m eval_memory_e2e config-probe \
  --roundtrip --preflight-dir /absolute/fresh-native-preflight \
  --output-dir /Users/gzx/debug-workspace/e2e-evaluate/memory-e2e/config-roundtrip-new
```

三端 UI 探针逐项执行原值 → 相反值 → 回读 → 原值恢复，持久化每次意图与最终状态，并保留前后截图。千问关闭意识模式时会移除自动记忆控件，该控件记为暂不可观察，重新开启后再核对原值。失败回执中的 `restored` 必须按原件确认；不能仅因命令退出就假定恢复。

AStudio 没有对应 UI 入口，先验证精确应用进程与原生空闲状态，仅编辑 `~/.acode/config.toml` 及其桌面 overlay 中的记忆 feature；使用安装内核及其 `ACODE_HOME` 参数回读，再按原始字节 SHA 恢复。私有配置备份权限为 0600，不放入候选工作区；有并发编辑时拒绝覆盖。文件与安装内核回读通过，不表示已有运行中聊天已应用新配置。

配置探针不清空记忆、不发送评测提示词；被拒绝目标在访问配置文件和 CDP 之前失败。日常账号仍使用测试事实级清理。

## 原生 Driver 的冒烟条件

```bash
python3 -m eval_memory_e2e native-profiles --output /private/native-profiles.json
```

输出冻结原生 Driver、共用组件、依赖锁定文件和原生文件夹选择器源码。AStudio／WorkBuddy 接入新建与继续会话；千问／豆包当前先验收新会话链，continue 与客户端重启需单独验收。

新 Profile 按本端字面量依赖递归冻结源码，`--harness` 执行只检查本端 Driver；共享源码和 Python 运行时仍严格检查。默认 `run` 按 Harness 轮询，单次控制/UI 调用串行，同端保持原冻结顺序；一端暂停不自动重发，也不阻止其他端继续。多端后台重叠的调度逻辑目前经过离线测试，真机并发须单独验收。

新建原生批次在每条实际发送的 Prompt 中冻结相同操作边界：不访问或改动 Codex 记忆，不让其他客户端代做，不清空日常账号记忆，仅处理本轮合成档案。原始开源样本和私有答案不改写；操作边界属于本项目执行条件。旧批次不就地改题。

原生 Profile 的控制调用预算为 180 秒，覆盖多个 UI 准备步骤；它不是模型做题时限。超时将保存部分 stdout／stderr 和原意图，只允许观察恢复。AStudio 轨迹优先绑定原始 rollout 的 session／turn／cwd／Prompt 摘要，不能把会被回收的桌面事件缓存视作完整模型轨迹。

该入口明确生成 `memory_protocol.purpose=immediate_automation_smoke`、`formal_scoring_allowed=false` 的 Profile。短观察窗只验证自动化与即时跨会话行为，评分模板入口拒绝将它作为正式能力成绩。AStudio 的历史候选与两阶段整理、WorkBuddy 的每晚整理、千问的写入／反思、豆包主动与周期记忆分别记录 formation gate；正式测量需要另行冻结相应学习条件。

UI 输入使用已核验客户端的原生前台激活和精确控件。豆包采集器支持已核验的独立模块及合并模块源码指纹，只读取已缓存模块，不调用初始化、权限或工具接口来制造观察状态；consumer witness 必须与当前源码指纹一致。未知版本继续拒绝准入。

控制器超时保留原意图；观察入口不对千问／豆包已证实零发送的旧操作启动首次发送。已完成请求沿原生身份恢复，不重发。需要恢复共享 UI 锁时，仅在精确 owner、同主机、原 owner 进程已退出、操作属于四端冻结意图时使用：

```bash
python3 -m eval_memory_e2e recover-ui-lock --root /absolute/batch \
  --expected-owner-id EXACT_UUID
```

新 Profile 中，千问/豆包可显式使用 `retry-pre-send --root ABS --episode FULL_ID`，仅恢复已证明没有原生发送意图、reservation、调用或接受的准备失败。它不适用于不确定发送；旧批次未冻结该能力时不会自动升级。配置、学习条件或题目改变须新建批次，不能借 `repair-runtime` 改题。

锁恢复只归档锁并追加证据，不修改旧 journal、不停止客户端任务、不授权再次发送。源码修复通过 `repair-runtime` 留下原／新摘要，题目与 Prompt 保持冻结。

## v2 复杂用例与状态观察

原混合 20 题保留 v1。v2 支持可变题量、更多工作区作用域、自定义 token/整数/literal 事实、带 SHA 的公开材料及显式学习条件。示例与校验：

```bash
python3 -m eval_memory_e2e validate-dataset --dataset tasks/memory-e2e/examples/complex-memory-v2.json
```

`learning.mode` 区分 explicit、automatic、eviction。自动组采用中性边界，不额外指示保存事实；源 Prompt 仍须由用例作者保持为自然业务输入。时间窗只是观察条件，不能代替原生形成事件。当前 `native_event` 原生执行尚未准入；DAG、多账号、多智能体和任意 UI 操作步骤不在本版执行范围。

新原生 Profile 在学习前、观察中、完成后采集已知本地记忆文件的私有快照；相同状态去重。观察不完整、文件不稳定或云端不可见会显式记录，文本命中不自动转成语义分数。定向清理仍标为未验收，不再通过占位 capability 标签宣称支持。

同一客户端内先 C0 后 M+，再进入下一场景；不同重复使用不同事实。每个批次还生成新的 experiment ID，参与合成实体与事实变体生成，避免复用旧批次的事实。四端和两个条件在同一场景、同一重复中使用相同事实与测试问题。种子、experiment ID、全部实体和 Prompt 均在冻结包中保留。

该对照的结论是历史经验增益。C0 的提问本身可能进入账号历史，固定顺序也可能带来时间效应，因此不能声称严格独立状态或记忆模块开关消融。真实记忆作用域由 Driver 的原始证据声明：`verified_namespace` 或 `shared_account_cold_first`，不是由目录名称推定。

记忆渠道使用客户端自身机制并归档可见 Workspace：Agent 自己生成的笔记和文件须在轨迹／阶段快照中可查。开关、模型和专用工具配置变化须单列实验条件，不能把显式开启实验写成出厂默认行为。`mode=native` 仅表示真实客户端执行，不代表已证明独立存储层或排除了所有文件记忆。外部注入统一记忆库需要另建实验条件。

## 准备一个冻结批次

```bash
python3 -m eval_memory_e2e prepare \
  --root /Users/gzx/debug-workspace/e2e-evaluate/memory-e2e/diagnostic20-new \
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
