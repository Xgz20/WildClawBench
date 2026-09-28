# 四端 round1 框架修复归并

本记录对应 macOS 四个客户端的 round1。归并对象是执行、证据、评分、报告和交付工具的修复。既有执行、候选、评分、原始轨迹、截图、回传包和发行保持冻结，运行数据不进入源码仓库。

## 版本与来源

主工作区基线为 `cf53a74`。评测分支的12个差异提交已合入，覆盖发送确认、URL片段回读、流租约、项目导航、日志轮转、评分路径和规则异常。名单缺失ID修复已有等价提交 `c064bd2`，未重复引入。

后续本地运行时修复落入下列正式版本：

| Skill / 组件 | 版本 |
| --- | --- |
| prepare-general-e2e-workspaces | 0.3.0 |
| execute-general-e2e | 0.12.0 |
| collect-general-e2e | 0.9.0 |
| score-general-e2e | 0.9.0 |
| orchestrate-general-e2e | 0.10.0 |
| report-general-e2e | 0.6.0 |
| run-general-e2e | 0.6.0 |
| doubaowork 共享适配 | 0.8.0 |
| general-contracts | 1.3.0 |
| general-resource-supplements | 1.0.0 |

共享实现从 canonical source 打包；开发用 vendor 副本同步相同实现。报告和采集包都带资源复算组件，脱仓运行不读取本轮控制目录。

## 问题与落点

路径相对仓库根。表中“原生”表示被评客户端提供的记录，不代表其内部模型服务或计费系统暴露了全部信息。

| 范围 | 本轮暴露的问题 | 正式修复与边界 |
| --- | --- | --- |
| AstronStudio 发送 | 点击返回、UI路由和原生身份出现存在时间差 | `execute-general-e2e/scripts/execute_astronstudio_macos.mjs` 与 `scripts/lib/astronstudio-cdp.mjs` 保留一次发送意图、原生身份确认和同attempt只观察恢复；未知发送不自动重发。 |
| AstronStudio Prompt | URL在编辑器中成为链接片段，普通innerText回读失真 | 校验语义文本和链接目标，仍要求冻结Prompt摘要一致。 |
| AstronStudio 流 | 未取得目标thread租约就发题；日志轮转漏掉已授予租约 | `astronstudio-stream.mjs`读取当前及轮转日志，要求目标thread的正证据。未支持的预建项目旧租约不冒充新鲜发送证据；发送仍单UI槽、后台一槽。 |
| AstronStudio 项目 | 新项目导航、延迟路径渲染、项目菜单未关闭、悬浮预览遮挡 | 定向绑定project/cwd，等待菜单与路径；发送意图落盘前确认按钮无遮挡。 |
| 项目显示名 | basename统一显示为workspace | `rename_astronstudio_projects.mjs`是参数化入口；只在正式收口且客户端空闲时改本地别名为task_id，不改Workspace或Prompt。 |
| 准备/评分 | `/tmp_workspace`映射成`./workspace`造成结果多套一层 | 新执行包映射到`.`。评分保留旧冻结映射兼容，仅旧Prompt和候选共同证明唯一嵌套结果时调整逻辑根，双根结果拒绝。新Prompt下错误嵌套不会被自动纠正。 |
| AstronStudio 失败 | 原生turn失败被归成基础设施错误，无法正常处理产物分 | 已唯一绑定的原生失败归`candidate_error`。Collector冻结失败证明；裁判仅按审核过的输出契约评分，不在采集器中直接赋0分。 |
| AstronStudio 轨迹 | `dynamicToolCall`未标准化，失败时把中间助手消息标作最终回复 | 原生动态调用进入标准轨迹；非成功turn不制造最终回复。 |
| AstronStudio 大轨迹 | 原生事件数大导致整表装入内存、64MiB收口上限、快照复制开销 | `general-resource-supplements`组件逐行归档及哈希，忽略用于指标计算的文本增量但保留完整原件和原行号；收口流式校验/复制，macOS优先COW复制。 |
| AstronStudio 指标 | 过程轨迹partial导致独立可证的Token和耗时一并丢弃 | 按字段核验。用量增量与累计值对账并去重，失败turn的原生起止时间也可统计；HTTP尝试和未暴露字段仍不可用。 |
| WorkBuddy 规则 | 缺失recipient_id触发规则排序异常；规则失败重复排队 | 修复规则，并对旧冻结规则保留精确源SHA修正回执。规则Worker失败形成评测异常终态，不计能力零分，不循环重做。 |
| QwenWork 路径 | 工具执行子目录被当成Workspace根漂移 | `metadata-gate.mjs`区分执行目录与原生根目录，仍拒绝越界和身份不匹配。 |
| QwenWork 发送 | 已有精确草稿重复填充；零派发回读失败无法恢复 | 保持草稿摘要一致，精确草稿不重复输入；只有尚未预留派发的边界才恢复准备。 |
| QwenWork UI | 无aria/title的停止图标、UI与数据库流状态短暂不同步 | 精确识别已观察到的停止SVG，仅用于只读状态识别；同一绑定session采用有限观察窗口，不由UI缺失推断完成。 |
| QwenWork 文件选择 | 应用/文件选择面板焦点未稳定 | 原生helper等待正确应用前台并提升其唯一AX Sheet，键盘操作仍定向到该PID。 |
| QwenWork 保护确认 | 敏感输出确认阻断，缺少受控继续与人工介入审计 | 默认人工处理。只有明确的单任务授权文件、SHA和冻结策略允许“允许原文提供”；记录实际操作次数和身份，归档授权原件。未知弹窗不自动确认。 |
| QwenWork 终态 | 数据库failed与日志end_turn并存 | `terminal-gate.mjs`对精确PostToolUse保护停止、工具ID、主turn和新鲜数据库快照做一致性校验；保护阻断不自动改成能力0分。 |
| QwenWork 模型 | keep-current的UI值没有进入正式报告，显示未知 | 归档dispatch journal，将明确回读的UI模型选项连同证据SHA带入正式记录。它是客户端选项，不推断未暴露的后台模型ID；旧记录可用带理由的报告显示配置。 |
| DoubaoWork 项目/路由 | 侧栏分页找不到预建项目，发送后新会话路由迟到 | 唯一分页按钮有界展开并检查进展；原60秒窗口内等待唯一会话/项目回读，不再次点击发送。 |
| DoubaoWork 消息 | 旧本地助手影子与正式成功消息并存 | 2.31.6精确形态下允许时间更早、同会话/回复/消息ID的影子；其他情况仍拒绝。 |
| DoubaoWork 生命周期 | 辅助计时观察器误绑其他request | 仅在明确歧义且无计时样本时保留冲突并将辅助计时降级；不改原始request ID，不用它否定独立主消息及工具证据。 |
| DoubaoWork 工具证据 | Read/Glob/Grep/TaskOutput包装差异、工具事件时钟未验证 | `trajectory-merge.mjs`按精确包装和内容对账；`bound-evidence.mjs`限定已验证原生时钟Profile。未知版本不能借用该Profile。 |
| DoubaoWork 计数 | 缺远端工具轨迹内容，被误认为调用总数也不可用 | `tool-counts.mjs`分别按本地call ID、远端原生block ID去重。计数完整不表示参数、结果及顺序完整；不补造provider call ID或调用内容。报告端重新复算。 |
| 评分准入 | 输出型rubric因非必需工具轨迹缺口而未评分 | `reviewed-evidence-policy.json`按精确契约SHA声明证据需求，核验Prompt、会话、原始trajectory、最终回复和候选；未知契约、缺必需证据和哈希漂移仍拒绝。 |
| 失败评分 | 临时补评代码写死某次执行记录SHA | `failure_evidence.py`改为校验来源记录、状态、Prompt、候选和证明文件的绑定。契约政策仍明确审核；没有按失败状态一律给0分。 |
| 评分编排 | Codex项目目录选择窗口抢焦点 | `orchestrate-general-e2e/drivers/codex-desktop/select-folder.swift`按唯一窗口及有界回读完成选择；评分槽位仍需verify-score后释放。 |
| 控制恢复 | 更换修复运行时需要手改队列、易丢旧attempt | QwenWork/DoubaoWork的`--source-repair-manifest`绑定原队列SHA、原/新源码SHA和范围，保留旧状态/修复历史及全部attempt；不允许顺便改并发、题序、Prompt或身份。 |
| 报告 | 部分字段使总览整项空白、覆盖口径不清、表头/翻译/题数缺失 | 同源逐字段覆盖与小计；未知不补0；工具按单元独立表头及空行；分类中文和唯一用例数；秒级Excel名。 |
| 领导版 | 目标单元被当作唯一展示单元，摘要固定四端/60题 | `leader_report.py`保留全部参评单元，以指定目标作总结；处理单单元、不同样本数、未知指标和无参照分数。数值从Excel核对提取。 |
| 资源补采 | 临时覆盖报告值，不能脱离控制目录复算 | `supplement_resources.mjs create/verify`生成不可变补充层。报告验证原执行/资源SHA及全部补采原件，并复算后采用。保留旧记录、评分和修正谱系。 |
| 多来源报告 | 有效attempt分散，旧失败与替代轮次易混入 | `selected_report.py`按显式来源/逐题索引验证包成员、执行与评分身份和SHA，支持混合来源但保留原批次身份，不伪造单一完整collect receipt。 |
| 研发交付 | 数据散落、ZIP顶层目录误命名 | `build_developer_bundle.py`根据报告与显式索引打包，保留相对链接、原件和补充层，提供离线VERIFY；ZIP顶层名必须等于导出包名。 |

## 不能混淆的边界

- `candidate_error`是有原生证据的被评端失败；分数仍由规则和独立Judge决定。`evaluation_error`及`unscored`不自动变0。
- “字段覆盖完整”指该客户端原生统计口径已核验，不等于服务商计费、HTTP重试或内部所有消耗可观测。Token、模型响应/用量推进数、HTTP尝试数、工具次数分开。
- 任务耗时为原生任务/请求开始至终态，包含工具与客户端内部重试；流程耗时另含发送及控制器观察等待。失败的真实耗时不能因数值大而删除。
- QwenWork保护确认按当前任务授权处理。未授权、未知弹窗、身份歧义和未知发送仍暂停；没有新增全局自动放行策略。
- 每个客户端的UI派发单槽。WorkBuddy、QwenWork、DoubaoWork有三后台槽的既有验证；AstronStudio仍以其流租约实证支持的一槽运行，不把其他客户端的并发结论外推过去。
- 本轮未实际使用“无原生记录按0”的填充：原先缺失的AstronStudio第32题轨迹实际存在。框架默认保留不可观测字段为null，不能将采集遗漏或未暴露字段当成真实0。

## 验证方式

1. `python -m eval_general_e2e check-layout --json`核对七Skill和共享组件锁。
2. `node --test tests/general_e2e/*.test.mjs`覆盖四端驱动、队列、采集、归档、指标与恢复边界。
3. `python -m unittest discover -s tests/general_e2e -p 'test_*.py'`覆盖规则、准入、编排、报告、合约和独立发行。
4. 新回归包含：大于64MiB的原始事件、失败turn计时、动态工具、补采漂移拒绝、旧本地影子、远端block去重、辅助生命周期冲突、分页、任务授权、零分/符号链接与ZIP根目录名。
5. 对既有240条选择做只读复算：执行/评分身份、全部资源值/状态/覆盖及工具分组与既有v8一致。此项是历史原件复算，不是重新发送四端任务，也不替代新版本客户端的现场预检。

本次归并检查结果：General Node回归358项通过；Python回归185项通过（包含独立发行、布局、规则和报告检查）；共享DoubaoWork的Web回归76项通过；两个Swift目录选择helper类型检查通过。上述计数分属各检查入口，Python包装检查可能再次调用Node，不合并为不重复的测试总数。

现场恢复、重跑授权、逐题选择文件和原始证据属于运行数据，留在评测控制工作空间。源码中保留算法、显式参数入口、校验与合成回归，不包含实际会话和候选。
