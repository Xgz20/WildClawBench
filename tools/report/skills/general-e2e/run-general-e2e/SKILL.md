---
name: run-general-e2e
description: 按用户明确选择的阶段串联 General E2E 准备、执行、证据、评分、回传和报告，并维护恢复状态；不替代各阶段 Skill 的判断与契约。
---

`0.7.37` 的 `prepare-score` 在两个 CLI 入口及内部调用中支持显式 `--score-slots 1–8`，默认仍为3。例如4并发使用 `--score-slots 4`，该值传给标准编排器并在新编排中冻结；非法值在读取材料或创建编排前拒绝。外置评分包、原评分及历史编排保持原契约，改变槽位必须创建新编排，不能修改既有状态或 digest。

`0.7.36` 正式派发统一采用完全访问基线，须使用带硬门禁的Execute0.15.22及其对应适配器；客户端默认、询问、未知或切换工作区后漂移均不可发送。历史回放和只读导入继续保留原权限，不能以新基线重写旧记录。模式改变后的正式结果须独立完整执行，不选择性补跑失败题。共享版本注册和受跟踪vendor副本同步；不自动启动客户端或提升现有轮次权限。

`0.7.35` 仅将单数judge-observation/node_modules纳入既有裁判运行依赖排除协议；仍须未被冻结输入、评分或正式取证引用，原链接不删除。任意父链接和其他绝对链接继续拒绝，观察文件及原评分全部保留，排除项进入package-exclusions审计。

`0.7.34` 选定attempt研发导出保留合法的evaluation_error空分评分闭包，逐项核对原valid、total与报告身份；有效0分继续保留，未知不补零。沿用离线VERIFY的原有效性/null校验及全部SHA门禁，不更改报告、原评分或历史包。

`0.7.33` Loomy 对精确已完成的 MessageAbortedError 与 finish=other 保留失败、原候选及原生轨迹，跨同一安装的后端更换仍须先证明原会话全部结束。未答问题只接纳原生 aborted/error 完整回执，已答或待答问题不准入；无法确认的人工介入计数保留 null。沿原 Rubric 独立评分，不补答案、不重发、不统一零分；旧冻结发行和数值规则保持。

`0.7.32` Loomy 原生 `finish=length` 仅在消息完成、全部工具和子会话结束及同一后端空闲时保留为执行失败，独立复验原 Prompt、Spark/High、终态和来源 SHA 后交原 Rubric 评分。保留截断前轨迹、原候选与旧发行，不重发、不把缺失终稿视为成功或统一零分；问题工具待处理时停止新派发。

`0.7.31` 选定研发包从规范报告保留标准report回执和运行审计；未由原生报告生成的附加验分索引为可选，存在时仍保留。核心报告成员及逐题score/record/candidate SHA门禁不放宽。

0.7.30 `prepare-score --sdk-final-authorization ABS`显式透传逐题SHA绑定的SDK终稿授权；必须同时显式选择完整任务及执行记录。编排仅为原生前缀/后缀差异题使用授权，普通题保持原准入，外置评分模式和阶段屏障不变。

0.7.29 AStudio 并发执行期间只做观察及只读轨迹/资源归档；整个执行范围终态、原生无活动/待处理/未知会话后才正式 collect/finalize。收口门禁失败保留诊断，不判能力零分、不重发、不重启。Execute 的周期诊断和 Collect 的信号审计来自同一版本化共享组件；历史冻结 Skill 和已发布报告不替换。

`0.7.28` 对同次 AgentCube 原生完成后的控制器断连使用独立恢复来源，复验原始文件、清理证明、身份与唯一发送；原失败和旧发行保持，不能伪造 WGUI RunReport。

`0.7.27` 支持显式 AgentCube 原生资源补充层：独立重验原 Prompt、会话、MCP 调用、终态及清理证明，再按原 last/total 用量复算 Token 和请求数。原执行、资源字节与分数不改，缺失字段不补零；回传、导入和报告须使用支持该 Profile 的冻结发行。

`0.7.26` 整合 Loomy Harness 显示与主线研发副本保护、规范封存恢复；保留既有批次、原ZIP和历史发行，不复用两分支已冻结的0.7.25内容。

`0.7.25` 主线发行：默认研发导出、规范报告成员、宿主报告变体和逐题选择导出共用新副本保护：Office及opaque `.bin` 在落盘后、记录SHA前立即设置macOS user-immutable并复核原字节，不依赖源文件已有保护。新增 `scripts/restore_developer_bundle.py`，只从显式SHA绑定且通过离线核验的研发ZIP恢复新目录；保留文件/目录/链接模式，已有目录必须显式保留为宿主变体且其INTEGRITY与ZIP相同。不执行输入包中的VERIFY.py，不改原ZIP、原清单、旧回执或源文件。

`0.7.25` Loomy 开发发行：新增 Loomy Harness 显示名称，沿用现有通用阶段与冻结批次协议。


`0.7.24` 回传导入与研发导出按原ZIP/清单保留相对符号链接自身模式，不跟随链接或修改源目标；全部成员复制后再由深到浅恢复原目录权限。独立逐题选择导出器使用同一复制约束，防止只读父目录阻断子成员。评分、原件、选取谱系和旧包不改。

`0.7.23` 研发及回传导出支持排除`judge-observations/node_modules`中未被正式输入、评分或取证索引引用的裁判运行依赖，原链接不删除，实际观察文件完整保留。父目录链接、候选/private依赖、被冻结根覆盖或已被证据引用的依赖继续按原严格门禁处理；不放宽任意绝对链接，不改变执行、评分、资源或既有包。

`0.7.22` 新轮次及新修复attempt沿用评分端`evidence-accountability/v1`：评测框架/题源故障先修复再执行受影响阶段；影响题面、输入、派发或实际作答须新执行，保留旧attempt。已受理后的Harness通信报错、中断、未产生日志/产物交原检查点评分，故障记录独立保留，不统一整题0分、不因被测端缺行为证明保留空分。仅评分/采集修复且原作答可恢复时使用原执行独立重评。前述规则仍不能分类时，汇总具体检查点、原件与已核查事实、修复影响和待决选择交用户决定；不自动重发未知请求。

`0.7.21` 研发导出保护新建 Office 及 opaque .bin 副本，按原 SHA 校验后封装。排除宿主目录元数据，并支持对明确自建 staging 复验全部来源 SHA 后恢复封装。研发导出支持 --selected-only。使用与正式报告 JSON SHA 绑定的逐题选择索引，保留每题唯一执行回合及选中的有效评分，支持评分来源跨目录。执行失败与空分继续保留，历史被替换 attempt 排除。候选目录、标准/原生轨迹、评分闭包均按原字节封存，未采到的轨迹只保存现有前缀及缺失说明。旧完整来源包导出入口保持兼容。

`0.7.17` macOS规范报告输入副本在导入回执落盘后封存全部已管理目录，防止宿主新增未列入包的目录元数据；不修改原ZIP、旧缓存变体或SHA。仅本导入器未发布且唯一命名staging的清理可解除自己创建的保护，不触及未知目录或链接目标。规范ZIP独立还原入口保持。


`0.7.14` 研发包保留APFS克隆继承的只读保护，权限已符合冻结成员记录时不重复chmod；不解除源文件保护或改原件。

`0.7.13` 研发包导出兼容报告的packages列表式来源索引，逐题核验source_package_id，并保留原索引字节和SHA。每单元多个来源包须明确布局，不能静默挑第一个。

`0.7.12` 修订后的70题使用独立 `general-custom70-v2` bundle（检索20、Office30、数据分析001—020），
不把其余46题加入本轮。旧60及历史116-v1 bundle继续按原身份消费，禁止用新题源替换历史冻结输入。

`0.7.11` 回传仅排除评分attempt顶层或judge-review命名空间中、未被冻结输入/评分/取证索引引用的node_modules运行依赖，原目录/绝对链接不删除；排除项以scoring/package-exclusions.json显式留证。candidate-original、private及正式执行证据中的同名依赖完整保留；任何冻结证据引用顶层依赖仍失败关闭，其他绝对链接不放宽。

`0.7.10` 的评分与回传校验支持新终态投影对账证明，保留原 state/SDK 字节和相同任务范围。多题正式采集先逐题 finalize，全组回执生成后再统一 verify-only；不要将中间 receipt_path=null 当作失败或手工补回执。

`0.7.9` 支持显式 bound-qwen-native-utf8-redecode/v1 传输补采：原记录、回执、原始快照与 SHA 均保留；原生身份、候选、执行时间、人工介入及资源值不变，只准许字节分块解码造成的 U+FFFD 替换恢复。新回执以显式 --execution-record task=path 选择，评分再次验证原/新闭包；不重发、不重判旧成绩、不修改题目或权重。

`0.7.8` 的 prepare-score 显式透传 --protect-runtime-office-inputs 到同一冻结编排；与 --keep-scoring-external 可同时使用，默认仍为可写 runtime。使用前必须确认冻结规则只读 Office 输入；不改现有编排或评分 attempt，不修改源 Workspace、原件或 SHA。

`0.7.7` 的七阶段链路同时支持 `general-custom60-v1`（旧 60 题、七维）与 `general-custom116-v1`（检索 20、Office 30、数据分析 66，独立五维）。管理员按 [数据集构建说明](../../../../../eval_general_e2e/datasets/README.md) 选择并构建 dataset bundle；独立安装后只消费冻结 ZIP，不依赖此源码链接。随后沿用相同的 prepare → execute → collect-evidence → score → package → import-return → report 流程；所有阶段保留 dataset ID/digest，不替换历史包或旧评分。


# 运行 General E2E 全流程

`0.7.6` 提供`prepare-imported-source --source-batch-root ABS --archive RETURN_ZIP --receipt PACKAGE_RECEIPT --output-root NEW_ROOT [--node ABS]`。它按原身份复制manifest/report-config、严格import/select并生成可移植source/task索引和只读JSON回放argv，不要求历史生产scoring ZIP，不初始化生产run state，不改制品锁或伪造完成状态。接收已有成绩时优先使用此入口；跨来源合并仍须逐条材料兼容与唯一报告单元映射，不能从旧Excel抄分或自动取交集。

经授权重评分的完整范围选择可由orchestrate的compose-rescore-selection生成，再通过本Skill的record-submission/package-return标准入口收口；保留旧submission、评分、回传和报告。该选择目录本身不含伪造的orchestration state。

`0.7.5` 的研发包保留完整报告选择范围，包括 valid、evaluation_error、unscored 和真实零分；未知分数保持 null，不为导出删题。支持实际评分采用的补采执行记录，保留原始回传成员和旧记录，不强制它与初始记录字节相同。

独立 XLSX 已被宿主追加属性时，`build_developer_bundle.py --canonical-report-archive ABS` 可从满足原回执的规范报告 ZIP 导出报告；独立副本作为变体保留，禁止改旧 SHA。规范 ZIP 可由 report `generate/selected_report.py --seal-output-dir ABS` 在生成进程内封存。该选项不放宽评分、来源包、JSON 或选择索引校验。

报告回执登记同样可显式使用 `record-receipt --root BATCH --stage report --receipt ABS --canonical-report-archive ABS`。必须逐字节匹配 ZIP 内的原回执并验证全部封存成员与回执制品 SHA；state 额外冻结该 ZIP 的路径/大小/SHA，恢复时继续核验。此参数只适用于报告，不替代 collect 回执或其他阶段验证；不提供时仍按原规则核验独立文件。

管理员只接收已有成绩时，可在新来源目录保留原 manifest/report-config，直接使用冻结 `import-return/select-import` 生成标准导入回执与选择索引，不必初始化原完整生产 run state。生产 init 会要求 manifest 中所有历史输入包存在；不能删 manifest 的制品锁、伪造评分包或手写完成状态来避开它。跨批次/同 unit_id 的比较仍需单独的派生报告映射，原身份不改。

`0.7.4` 的 prepare-score 新增 --keep-scoring-external：对 install-unit 安装的公开单元，将外置 scoring ZIP 的绝对路径和 SHA 绑定到 round 状态，不复制 ZIP 到 round-root。显式提供 --scoring-package ABS、--report-config ABS；后续调用仍须保留外置模式并重验路径/SHA。评分包实际在 round-root 内（含指向内部的链接）、已安装内部评分包或模式漂移均拒绝。默认缓存行为保持兼容。

此选项只是材料放置方式，不是 OS 隔离或停机屏障。原生分阶段评测必须先完成全部执行、正式采集/不可变校验和被测进程收尾，并保存屏障证明，再准备评分。外置目录在同 UID 下仍可能可读，按实际访问证据披露；prepare-score 不自动停止被测客户端，也不声称已拒绝私有读取。

```text
python -X utf8 /absolute/run-general-e2e/scripts/run_general_e2e.py prepare-score --round-root /absolute/round --harness AstronStudio --orchestration-id score-001 --scoring-package /external/private/scoring.zip --report-config /external/private/report-config.json --keep-scoring-external
```

报告登记后立即核验并封存规范 ZIP，保留原报告 receipt 和成员 SHA。若裸 XLSX 被宿主追加属性，保留变化字节与 OPC 成员差异，以封存 ZIP 内的原成员为字节权威；不得删宿主标记、改旧哈希或将重写文件冒充原件。研发打包可消费从规范 ZIP 安全重建并校验的报告目录；需要跨目录 workspace-root 时仅选择明确来源，不扫描整个用户目录。新增源码版本不替换已完成轮次的冻结 Skill 或规范交接包。

`0.7.3` 支持 execute-general-e2e 0.14.4 的原队列额度恢复；先读取该已安装 Skill 实际根目录的 `references/quota-recovery.md`。控制会话先生成未批准的授权草稿，只有取得人类“额度已恢复且授权重执行指定失败题”的直接指令后才填写确认及授权引用；保留旧 attempt 和完整现场，仅选择一个新 attempt 重执行该题。成功题不重跑、在途题不重发；后续恢复复用已持久化的一次授权，发送一经 armed 就只观察原生 turn。不得借恢复之名重评分、覆盖旧结果或执行已封存轮次。

`0.7.2` 的默认额度故障策略是暂停等待人工：发现原生额度耗尽，立即停止新任务/评分/打包，将当前阶段置为 NEEDS_HUMAN 并报告原生在途会话和恢复入口。不得自动转 UNSCORED 后继续，也不得计能力零分或自动重发。人工恢复额度后，还须明确授权恢复；已经终态失败的用例如需重测、建立新 attempt 或选择替代来源，单独保留授权与审计。历史轮次的一次排除授权不扩展为后续默认豁免。

正式语义评分统一使用独立项目中的独立单题聊天，通过标准 orchestrate-general-e2e 编排；不得由控制会话或协作子代理判分或作为会话失败后的替代。纯自动规则题仍使用受管 Worker。


## 默认工作空间布局

评测根目录未指定时使用控制 Harness 会话项目的当前工作目录；显式 `--round-root` 时采用用户路径。调用本 Skill 的绝对脚本路径，不 cd 到安装目录。新评测不创建顶层 rerun-execution-units、score-attempts、repair-control 等多套工作区。

收到单端 execution ZIP 后使用 `scripts/run_general_e2e.py install-unit --execution-package ABS`；完整冻结批次可用 `init-round --batch-root ABS`。两者均在评测根建立 Harness/execution/tasks 和 Harness/score/tasks，内部状态在 .general-e2e。已有输入 ZIP 和用户说明保留，冲突拒绝覆盖；单端安装无需提前收到私有评分包。

正式采集后运行 `prepare-score --harness AstronStudio --orchestration-id score-001 --scoring-package ABS --report-config ABS`，返回同一 Harness 内的编排根。新轮次评分必须交接标准轨迹、原始日志、trace-index、候选与私有标准，再按 orchestrate-general-e2e 推荐动作调度独立评分。历史失败证据例外显式保留。

需要非默认评分槽位时，在首次 `prepare-score` 显式增加 `--score-slots 4`，并核验生成编排的 `score_slots=4`。该参数控制独立语义评分槽位；UI 发送槽位、执行并发及规则 Worker 的调度仍由各自阶段配置决定。

修复留在对应单元/单题内，使用新 attempt 和显式选择，不自动重建整批。完成后的轮次可用 scripts/archive_round.py 的 import-final/verify/replay 迁移、校验和脱离旧目录复算，再按明确保留清单清理。

组合已实现的单阶段能力，支持单 Prompt 自动链路与人机协作交接，同时保持阶段级恢复和失败关闭。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --json
python -m eval_general_e2e check-layout
```

只执行用户明确选择且对应单阶段 Skill 已具备所需能力的阶段。当前 `0.7.3/operational` 已实现批次/单元两级状态恢复、冻结输入校验、标准回传打包、安全导入、幂等与冲突选择；支持资源覆盖不完整但身份和哈希有效的采集回执贯穿 unit flow，并按 submission 中的完整多级路径只打包目标评分 attempt。G4-03 已完成 AstronStudio macOS 五题执行、默认三槽评分、回传和同源报告闭环；QwenWork macOS 1.0.6 已完成单题 return/import/report 闭环。该状态不外推 Windows、其他 Harness、并发或 60 题全量。

新增 Harness 可按 [通用执行状态接口](references/adapter-execution-state.md) 接入 `record-execution`。该入口验证终态、业务身份、Workspace、原生会话证据与发送状态；公共 CB-B 首批接口已提供，新的 Harness 仍须完成原生采集和真实平台清理 hook 的接入验证，不因状态登记成功而宣称已具备生产准入。

## 已实现入口

最终选择已评分且报告生成后，可用`scripts/build_developer_bundle.py --workspace-root ABS --report-dir ABS --output-root ABS`生成研发数据包。默认读取报告目录中的逐题与来源索引；历史索引可通过`--source-index/--task-index`指定，独立资源补采可用`--resource-root`加入。按来源包和显式选择校验，不扫描整个控制目录；保留原件、相对符号链接、资源补充层及离线VERIFY。ZIP顶层名须与导出包名一致，既有包不覆盖。

已封存的研发ZIP通过原SHA校验，但展开目录被宿主改写时，可安全重建目录；保留原目录及差异记录，不改旧SHA。默认拒绝已有目标；确认要保留已有目录再恢复时，显式使用 `--preserve-existing`：

```text
python -X utf8 /absolute/run-general-e2e/scripts/restore_developer_bundle.py --archive /absolute/developer-bundle.zip --expected-archive-sha256 ORIGINAL_64_HEX_SHA256 --output-root /absolute/restored-output [--preserve-existing]
```

恢复器核验ZIP全部成员、类型、SHA、目录及相对链接模式，并使用当前发行的可信只读校验器验证执行/评分关联；不执行包内脚本。新副本通过目录校验后才发布，恢复回执单独写在包外。失败staging保留供诊断；不会清理来源或未知目录。此操作不重新执行用例、评分或生成新的成绩选择。

先建立显式状态；`--input role=/absolute/file` 会冻结评分包、报告配置等外部输入，恢复时重算 SHA：

```bash
python scripts/run_general_e2e.py init \
  --scope unit --root /absolute/unit-root \
  --stage execute,collect-evidence,score,package \
  --input scoring-package=/absolute/unit-scoring.zip

python scripts/run_general_e2e.py resume --root /absolute/unit-root
```

阶段开始、人工接管或失败使用 `set-stage`；完成不能手工填写，必须用 `record-execution`、`record-receipt`、`record-submission`、`package-return` 或 `import-return` 记录通过身份、终态、契约与哈希校验的产物。详细命令和恢复边界见 [流程状态与离线回传](references/flow-and-return.md)。

单元评分完成后生成确定性回传包：

```bash
python scripts/run_general_e2e.py package-return \
  --unit-root /absolute/unit-root \
  --orchestration-root /absolute/orchestration-root \
  --output-dir /absolute/returns
```

collect receipt 的身份、任务范围、哈希和完整性仍是硬门禁；当客户端不暴露 Token 等资源字段时，合法的 `partial` receipt 也可进入回传，报告端必须保留缺失覆盖，不能补零。

管理员侧导入时会手工解析 ZIP，拒绝越界路径、重复成员、未知类型、哈希漂移和越界符号链接。相同 archive SHA 幂等；同一批次单元的不同内容分别保存在 `returns/<unit-id>/<package-id>/`，并清除当前选择。只有显式 `select-import` 后，冲突单元才能继续报告阶段。

## 阶段与责任

稳定主链路为：`prepare → execute → collect-evidence → score → package → import-return → report`。

- 冻结阶段选择、数据集、Harness、模型、裁判及推理配置；恢复时沿用原配置。
- 每阶段只消费上游有效回执，保留 `NOT_SELECTED / PENDING / RUNNING / NEEDS_HUMAN / NEEDS_ATTENTION / COMPLETED / FAILED` 状态。
- `collect-evidence` 采集执行证据；`import-return` 导入管理员回传，二者不能混称 collect。
- 支持人工执行或离线交接，但不补造自动化证据，不覆盖冲突 attempt。
- 组合器不重写单阶段规则；具体执行、取证、评分和报告由对应 Skill 负责。
- batch scope 只管理 `prepare / import-return / report`；unit scope 只管理 `execute / collect-evidence / score / package`，不能把两类根目录混用。
- 回传包只收录冻结 unit manifest、正式 receipts/evidence、完整 submission、执行记录和评分 attempt；排除评分 `runtime/` 副本、缓存和常见凭据文件。
