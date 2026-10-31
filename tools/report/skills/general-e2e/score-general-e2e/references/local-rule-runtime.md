# General E2E 本地受管规则运行时

## 能力与边界

该运行时在本机独立 Python Worker 中执行冻结、可信的 General E2E 自动规则，不使用 Docker。它只生成规则组件和运行审计；语义判定及标准 `score.json` 由同一 Skill 的 [Codex 语义评分协议](codex-agent-judge.md)和 `finalize` 子命令完成，规则分本身不等于完整评测分。

专用虚拟环境、独立进程和环境白名单用于依赖复现、故障收口和凭据隔离，不是针对恶意 grader 的安全沙箱。只允许执行版本化数据集中的冻结规则；不要把任意第三方 Python 代码传给 Worker。

## 固定运行时

- Python `3.11`
- PyYAML `6.0.3`
- 新题解析依赖：openpyxl、pypdf、PyMuPDF、python-docx、lxml、NumPy、Pillow（具体版本和哈希见锁文件）
- Playwright `1.55.0`
- Chromium revision `1187`，browser version `140.0.7339.16`

完整 Python 依赖和制品哈希由 `scoring-runtime-requirements.txt` 与 `scoring-runtime-lock.json` 固定。macOS x86-64 已完成依赖安装、Chromium 启动、Playwright 规则 Worker、真实 S1 冻结用例和超时子进程清理 smoke；Windows 当前只有代码路径和 PowerShell 进程树实现，必须在 Windows 真机完成安装、浏览器启动、超时和残留进程验证后才能标记通过。

## 一次性初始化

在 Skill 根目录运行：

```bash
python scripts/score_general_e2e.py bootstrap-runtime \
  --venv-root /absolute/path/to/general-e2e-rule-runtime
```

该命令使用 `uv` 创建专用虚拟环境、按哈希安装锁定依赖、把 Chromium 安装到虚拟环境内的 `playwright-browsers/`，然后执行版本与浏览器启动 smoke。代理和证书只在 bootstrap 阶段按白名单继承；评分 Worker 不继承这些变量。

`--offline` 只使用已有 `uv` 缓存。`--skip-browser` 可准备不含浏览器的环境，但 Playwright 规则会在运行前失败关闭，不能据此宣称完整运行时就绪。

### macOS 原生 Office 依赖

原规则调用 `soffice` 时，先在尚未启动评分的专用 Python runtime 中配置实际 Office 二进制。使用 `load_workspace_dependencies` 返回的本机路径；不要硬编码其他机器的缓存版本，也不要把依赖包的 shell 包装器放入只有 Python bin/ 的 Worker PATH。

```bash
python scripts/configure_native_office.py \
  --runtime-python /absolute/runtime/bin/python \
  --soffice-binary /absolute/LibreOffice.app/Contents/MacOS/soffice \
  --support-root /absolute/runtime/native-office \
  --font-dir /System/Library/Fonts \
  --font-dir /System/Library/Fonts/Supplemental \
  --font-dir /Library/Fonts
```

只传实际存在的字体目录；有其他已安装字体可继续追加 `--font-dir`。入口拒绝已存在的 `bin/soffice` 或 support-root，保留原 runtime，不覆盖冻结轮次。回执记录真实二进制 SHA、版本、启动器和字体目录；每次调用核验二进制 SHA，独立临时字体缓存不需要扩大 Worker 环境白名单或继承 HOME。

`CONFIGURED_REAL_RENDER_SMOKE_REQUIRED` 只证明已配置及版本命令成功。使用 `_sanitized_environment` 的真实环境，对合成 DOCX/PPTX 实际渲染、在副本编辑后保存重开，并查看含中文页面截图；只有文本提取成功仍可能漏画中文字形。保存命令、环境键、二进制/启动器/输入/输出 SHA 和截图。原规则明确要求 Windows WPS COM 时须提供对应环境；此配置不把 LibreOffice 当作该 COM 检查的替代品。

## 准备私有 attempt

### 可选的macOS原生Writer API

Office001的原实现依赖Windows WPS COM。新的macOS评分可显式配置同等正文/必需表格编辑、保存重开证据的原生Writer API；它使用独立原生Office实例，不通过修改XML或仅做转换冒充实际编辑。真实候选和GT仍只在执行/正式采集/停机屏障后交接；运行时配置自测仅使用新生成的合成DOCX。

准备已存在的JDK17+及官方UNO Java类JAR `org.libreoffice:libreoffice:26.2.2`（MPL2.0），固定SHA256为`37b94f944cb35fdbdb586d08df65419b42f1bd2363e143958dbae63ca15c23b3`。官方不可变地址为`https://repo.maven.apache.org/maven2/org/libreoffice/libreoffice/26.2.2/libreoffice-26.2.2.jar`；保留下载来源、校验和POM。无需改系统Java配置或安装Python UNO。

```bash
python scripts/native_writer_runtime.py configure \
  --runtime-python /absolute/runtime/bin/python \
  --jdk-home /absolute/installed-jdk \
  --uno-jar /absolute/libreoffice-26.2.2.jar \
  --office-configuration /absolute/runtime/native-office/native-office.json
```

它拒绝覆盖既有marker/启动器/支持目录，锁定原生Office、JDK、JAR、Java源码/class及Python启动器SHA，并执行实际合成文档打开、正文/两表编辑、保存重开和进程收尾后才发布`VALIDATED_REAL_NATIVE_EDIT_SAVE_REOPEN`。每次加载文档均禁用宏及外部链接更新，源文件不改；原生实例使用本机临时socket和独立Profile。已停止Profile封存为ZIP、日志与原生回执保留，成功后的自有缓存清理不触碰未知锁。

新attempt显式冻结该验证marker、原contract/source SHA和运行时配置；旧attempt不追加。原规则函数只改入口声明以交接受管适配，原public numeric-v2算法和语义标准保留。评分端原生PDF/两版完整页图、编辑副本与进程证据放入独立grader-evidence；C6需逐页看图，C7只能看原始候选轨迹。缺交付导致原规则未调用探针时保留原数值结果与缺失说明；原生环境故障不转候选零分。v1匹配器与运行时源码已被评分采用后须保持冻结，后续改动使用新Profile版本。

新attempt可按精确contract/source SHA注册`canonical-public-office-cwm-only/v2`，只覆盖公开Office输入的环境属性变体。注册表携带经原数据集manifest SHA验证的公开字节；`runtime.public_office_input_profile`冻结该表和原contract/source SHA。匹配时所有业务OPC成员和非CWM属性必须完全一致，新增审计进入原声明的评分证据目录，不把它当候选主动检查。原件、候选、整体哈希及原规则公式不重写；其他数据、公式、样式、属性或缺文件仍按原规则判断。旧manifest没有marker保持原源码。已使用的v2表和匹配器须保留；后续扩展建立新版本，不覆盖已冻结评分依赖。

```bash
python scripts/score_general_e2e.py prepare \
  --unit-root /absolute/path/to/execution-unit \
  --execution-record /absolute/path/to/execution-record.json \
  --scoring-package /absolute/path/to/unit-scoring.zip \
  --task-id TASK_ID \
  --scoring-attempt-id ATTEMPT_ID \
  --output-root /absolute/path/to/private-scoring-root
```

`prepare` 只接受已完成且 evidence complete、候选状态 stable 的执行记录。它复核 batch/unit/task/dataset/release 锁、候选树和 scoring ZIP 的路径、类型与 SHA-256，然后创建不可覆盖的私有 attempt：

冻结 execution manifest 若将 `/tmp_workspace` 映射为 `./workspace`，而候选仅在 `workspace/results/` 有文件，`0.8.4` 会逐项核对已发送 Prompt SHA 与候选清单，把内层目录作为规则 Worker 的逻辑工作区，并在内层注入相同的私有 GT。外层候选原件保持只读，规则运行副本和路径选择写入 attempt manifest 与审计。根目录和内层目录同时有结果时拒绝歧义，不自动合并文件。

- `candidate-original/`：候选只读原件；
- `runtime/workspace/`：一次性可写副本，GT 在执行阶段之后注入 `gt/`；
- `private/`：冻结 contract、task、GT、transcript、execution record 与 runtime lock；
- `attempt-manifest.json`：身份、来源 SHA、路径和初始 runtime 哈希。

候选本身已有 `gt`、ZIP 路径穿越或重复成员、越界 symlink、候选漂移、私有材料不一致以及 attempt 已存在都会失败关闭。

## 复核与运行规则

```bash
python scripts/score_general_e2e.py verify \
  --attempt-root /absolute/path/to/private-attempt

python scripts/score_general_e2e.py run-rules \
  --attempt-root /absolute/path/to/private-attempt \
  --runtime-python /absolute/path/to/general-e2e-rule-runtime/bin/python \
  --timeout-seconds 120
```

Windows 的 Python 路径使用 `Scripts/python.exe`。bootstrap 生成的 marker 会让 `run-rules` 自动定位同一虚拟环境中的 Chromium；手工管理浏览器缓存时可显式传入 `--playwright-browsers-path`。

`run-rules` 在启动前复核候选原件、私有材料、transcript 数量和 runtime 初始哈希；然后按规则实际 import 只探测所需依赖。Worker 只接收结构化 JSON，请求中的 workspace 是本机真实绝对路径；`/tmp_workspace` 仅保留为任务协议中的逻辑名称。

终态产物采用不覆盖写入：

- `rule-component.json`：通过 grading core 契约校验的规则分；
- `rule-audit.json`：运行时探测、PID、耗时、环境变量键、日志 SHA、timeout、进程树清理以及 runtime 前后哈希；
- `worker/{request,result,stdout,stderr}`：本次 Worker 的私有 IPC 和原始日志。

超时、日志或结果过大、依赖/浏览器版本不符、Worker 异常、残留进程树以及评分材料漂移都产生失败审计，不补零，也不生成有效规则组件。失败 attempt 不可原地重跑；应使用新的 `scoring_attempt_id`。

### 逐检查点理由与证据

新执行产生 `wildclawbench.general-e2e-rule-component/v2`。每个 criterion 都记录中文 `reason` 和 `decision`：分数为 `1.0` 时标记 `full_score`，为 `0.0` 时标记 `zero_score`，其余合法值标记 `partial_score`。理由只解释 Worker 已返回的分值状态，不让模型推测自动规则的业务含义。

每项 `evidence` 都物化并校验 SHA-256，至少包含：

- `rule_source`：`private/contract.json#/automated_checks` 中的冻结规则源码；
- `candidate_artifact`：候选树绑定清单；
- `transcript`：任务存在轨迹时引用冻结轨迹；
- `rule_worker_result`：`worker/result.json#/result/<escaped-result-key>` 中该检查点的原始返回值。

`rule-audit.json.criterion_evidence` 记录证据策略、完整状态和 `zh-CN` 理由语言。最终 `score.json` 的自动规则聚合项逐项列出分数及满分、零分或部分分状态，并引用规则组件、Worker 原始结果和冻结 contract。历史 v1 规则组件仍可由 `verify-score` 只读验证，但新 attempt 不再生成 v1。


### Office001 数值抽取的独立复核

仅新Codex attempt可按原contract/source SHA冻结`office001-numeric-extraction-semantic-review/v1`。控制器先运行`prepare-rule-review`，只发现原`uncertain`分支的逐任务/字段上下文，不发布发现阶段数值。裁判完整分页`query-rule-review`并核对全部候选陈述和参考；原数值明确成立且重复陈述一致才填true，可确认遗漏或错误为false，材料不足保留unresolved/null。每项填写中文理由、已查询query_ids及具体`evidence_locations`，再`record-rule-review`，使用request冻结的解释器首次`run-rules`。原已确定比较、字段/分母及公共数值接口均不变，不能将六态`aggregate()`的重归一/扣分结果混入该成绩。

该入口可与已验证的原生Writer Profile组合；发现副本和正式runtime分开，正式规则成功后保留实际正文/两表编辑、保存重开、DOCX原生PDF、候选PDF及双方全页索引，C6仍由裁判逐页查看，C7只认原候选轨迹。旧失败attempt保留，不原地重跑；新attempt从同一冻结执行创建，原始题目/GT/权重不改。


### 原文本身份校验与连续语义分

新attempt可冻结`canonical-private-reference-guard/v1`。注册表绑定原task/contract/source、dataset digest、原Git版本及ZIP成员SHA；仅修正原脚本的旧校验常量。Office014的公开文本哈希还逐项证明原UTF-8 LF字节转换为CRLF恰等于旧值，GT归档文本副本须与对应公开原件逐字节相同。原GT、输入、候选和全部业务比较不改写，实际候选改动仍由原SNAPSHOT/副本校验识别。缺失或未注册参考、大小/SHA漂移仍失败关闭。旧失败只在实际私有文件仍是已登记原件时留证；修复需独立新attempt，不在原attempt重跑。

Office001新的`office001-original-continuous-semantic-ranges/v1`只把原Rubric明确写有Score (0, 1)的C2/C3/C6/C7交给core的有限[0,1]范围校验。原C1/C4离散锚点和所有权重不变。请求和归档验证重算相同原契约范围；不能将无效分改成0，也不把旧裁判结构化结果原地改写。修复已完成的框架锚点错误时，保留原null，创建独立重评分attempt。


### 已审核的取证文件名通配符

`reviewed-generated-file-globs/v1`注册Office011/017/021/023的原contract/source SHA和dataset身份，仅对这些原声明展开固定evaluator_evidence父目录下的文件名。所有匹配项都进入同一个不可变grader-evidence快照和查询目录；零匹配、匹配到目录/链接、原候选预置同名匹配项、任意越界继续失败。精确文件/目录路径以及未注册旧契约保持原解释。只读verify可核对尚未准入的旧规则产物，不改原manifest、Worker、规则分或参考；修复评测仍使用新的attempt。已采用的v1注册表和匹配器须保持，不覆盖成无界通配符。


### 新闻归档的表头与全列保全

Office003仅在原contract/source SHA匹配的新attempt冻结`news-equivalent-headers-complete-cells/v1`：接受明确等价的主体/别名/片段/位置表头，在分日事件数与显式合计并列时读取现有合计，不从GT推算；来源只对冻结公开清单中唯一匹配的相对文件名或路径后缀归一，歧义和外链不补造。原比较函数、事件/主体/分类分母及权重保持。原六份JSON内附完整物理单元格、原列、坐标、公式与缓存、合并范围，不能把取证端归一视为候选提供了额外信息；4MiB单文件和16MiB总量按UTF-8字节限额，超过仍失败且不截断。原件与旧取证保持，修复需独立新attempt重新运行原规则和语义评分。


### 逐行状态等价复核与结构诊断

合同托管新Codex attempt可冻结`escrow-status-equivalence-review/v1`，只发现原规则声明的未知状态词。独立裁判按完整候选/公开口径逐group选择唯一原状态等价项，或明确保留含义不同的原词让原比较失败；含义不清仍unresolved/null。不能因GT采用某词而修正候选事实。query-rule-review须覆盖全部context，record-rule-review严格检查每组唯一选择，之后才首次运行原数值比较；发现过程无数值发布，旧attempt不重跑。

六个已审核业务grade+取证wrapper仅重命名第一声明与原捕获别名，两个函数体均保留。协销errors list只作留证诊断，不是评分key；未知数字不删除，取证预算超限提示仍阻断。工单总取证预算扩至16MiB字节但保留18500字符确定性分片。两个已审核库存公开说明文件只接受已证明的UTF8 LF/CRLF原字节身份，实际SHA独立审计，不改MD或GT JSON。新Profile均绑定精确原契约/源码，旧根、判定、公式和权重保持。
