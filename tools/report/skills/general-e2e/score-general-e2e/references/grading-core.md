# General E2E 评分 core 接口

`score-general-e2e` 0.8.1 装配 `grading-core` 0.2.0。core 只负责规则依赖审计、结果校验、证据索引、语义结果校验和合分，不拥有评分工作空间、本地进程运行时、模型调用或任务调度。

自score-general-e2e 0.11.0起装配core 0.3.0，新增`extract_native_text()`和`is_native_text_format()`：DOCX/XLSX使用标准库，PDF按需导入评分环境中的pypdf。提取只做离线文本/单元格投影，保留原文件及投影SHA、记录位置、公式缓存状态和未解释内容；不执行宏、外链或公式计算。`NativeTextError`提供独立code/message，缺PDF依赖不能转为候选零分。详见[原生文件文本证据](native-text-evidence.md)。

score-general-e2e 0.12.0装配core 0.4.0，增加`create_office_lock(executable)`、`validate_office_lock(lock)`和`recalculate_xlsx(source, lock, output_dir)`。重算调用锁定的外部LibreOffice，不是Python公式模拟器；`OfficeRuntimeError`保留独立code/message。`validate_office_lock(..., require_executable=False)`仅用于归档时核验完整锁结构，不能作为运行前检查。详见[可信Office重算](office-recalculation.md)。

score-general-e2e 0.13.0装配core 0.5.0，`extract_native_text()`与`is_native_text_format()`增加PPTX。该格式的`engine.version`为`wildclawbench.pptx-text/v1`，外层schema仍为`wildclawbench.native-artifact-text/v1`。幻灯片顺序、文本/表格/备注、图表缓存与嵌入XLSX分别保留位置和适用边界；不渲染、不重算、不解析图像，也不跟随外部关系。既有三种格式的投影不改写。详见[原生文件文本证据](native-text-evidence.md)。

score-general-e2e 0.14.0装配core 0.6.0，新增`create_office_render_lock()`、`validate_office_render_lock()`、`office_render_lock_digest()`及`render_pptx_pdf()`。独立渲染锁在原Office程序锁外绑定字体文件及目录成员，原XLSX锁保持兼容；PPTX转PDF使用原字节一次性副本和明确导出选项，派生回执由外围评分工作空间核验。详见[可信PPTX渲染](office-rendering.md)。

score-general-e2e 0.15.0装配core 0.7.0，新增`read_embedded_xlsx()`、`extract_embedded_xlsx()`，建立冻结PPTX→原始内嵌XLSX→可信重算XLSX的来源链，归档复核不要求引擎存在。规则目录允许可选`pdfplumber`、`pypdf`，但Worker实际锁未声明的模块会在执行前报`RUNTIME_DEPENDENCY_UNDECLARED`，不能仅凭允许目录推断已安装。详见[内嵌表格重算](office-recalculation.md#内嵌表格重算)。

发行包内模块位于 `vendor/e2e-shared/wildclawbench_grading_core/`。调用方把其父目录加入 Python 模块搜索路径后导入 `wildclawbench_grading_core`。规则/索引/结果校验及合分、DOCX/XLSX/PPTX文本投影只使用Python标准库，PDF投影按需使用评分CLI解释器中的pypdf。任务规则所需的PyYAML、Playwright和Chromium属于G3-02专用评分虚拟环境，不因原生证据提取而安装到被测项目。

## 公开 API

score-general-e2e 0.16.0装配core 0.8.0，新增`read_image_evidence()`、`is_image_evidence_format()`及`ImageEvidenceError`。Pillow只在实际图片解码时按需导入，普通文本评分和归档附件字节核验不增加该依赖；返回原始图片字节及来源SHA，不执行OCR或转换。详见[冻结图片证据](image-evidence.md)。

### `run_rules()`

输入任务 `automated_checks`、受管 `executor`、本地 runtime 副本的真实 `workspace_path`、可选标准轨迹和预期 criterion key。core 先校验 AST、唯一同步 `grade()` 入口及静态 import，再调用注入的 executor，严格校验返回 key、`overall_score`、有限数值和 `[0,1]` 范围。

返回的规则组件 schema 为 `wildclawbench.general-e2e-rule-component/v2`。每个 criterion 都包含中文 `reason`、`decision.anchor`、观察分数、满分/零分锚点、原始 `result_key` 和待运行时物化的证据定位。`full_score`、`zero_score`、`partial_score` 只解释冻结规则已返回的数值，不新增业务语义，也不允许模型改判。

非空规则必须提供受管 executor。不要在控制 Harness 或评分编排进程中使用 `exec()`，也不要用任意宿主临时目录绕过评分目录门禁。G3-02 应让 executor 通过结构化 IPC 调用专用虚拟环境中的独立 Python Worker，把一次性 runtime 副本的真实绝对路径作为 `workspace_path` 传给 `grade()`，并返回 JSON 对象。

### `build_evidence_index()`

输入证据引用、可选证据根目录和已知 transcript event ID。相对路径必须是 POSIX 安全路径；提供根目录时会验证普通文件和 SHA-256，提供事件集合时会验证每个 event ID。返回确定性索引和 canonical JSON digest。

### `evaluate_semantics()`

输入 rubric criteria、注入的语义 evaluator、冻结证据索引和协议。支持 `codex-agent-judge-v1`、`api-judge-v1`；没有语义 criterion 时使用 `not-required`。evaluator 的每个已判定 criterion 必须使用允许分值、引用冻结索引中的证据，并以中文解释为何采用该分值锚点。未判定 criterion 也必须用中文说明证据缺口，返回 `evaluation_error` 和 `score=null`，不能补零。

这个 API 校验 backend 结果，但不创建 Codex 评分任务、不发送 API 请求，也不实现重试或 backend 切换。

### `finalize_score()`

输入 `automated`、`hybrid` 或 `llm_judge` 类型、原始权重以及规则和语义组件。它校验必需组件状态、权重和 criterion 唯一性；组件缺失或评测异常时返回 `valid=false`、`total_score=null`。有效结果按冻结权重合分。

## 稳定错误

契约或执行失败抛出 `GradingCoreError`，其 `code`、`message`、`details` 可序列化为 `as_dict()`。调用方按责任域处理以下稳定 code：

- 规则与依赖：`RULE_SOURCE_INVALID`、`RULE_ENTRYPOINT_INVALID`、`RULE_CONTEXT_INVALID`、`RULE_CONTRACT_INVALID`、`RULE_EXECUTOR_REQUIRED`、`RULE_EXECUTION_FAILED`、`RULE_RESULT_INVALID`、`RULE_RESULT_KEYS_MISMATCH`、`RULE_RELATIVE_IMPORT_UNSUPPORTED`、`RULE_DYNAMIC_IMPORT_UNSUPPORTED`、`RULE_DEPENDENCY_UNDECLARED`、`DEPENDENCY_CATALOG_INVALID`。
- 证据：`EVIDENCE_ROOT_INVALID`、`EVIDENCE_PATH_INVALID`、`EVIDENCE_FILE_MISSING`、`EVIDENCE_DIGEST_MISMATCH`、`EVIDENCE_EVENT_MISSING`、`EVIDENCE_REFERENCE_INVALID`、`EVIDENCE_REFERENCE_DUPLICATE`、`EVIDENCE_INDEX_INVALID`。
- 语义：`SEMANTIC_CONTRACT_INVALID`、`SEMANTIC_PROTOCOL_INVALID`、`SEMANTIC_EVALUATOR_REQUIRED`、`SEMANTIC_BACKEND_FAILED`、`SEMANTIC_RESULT_INVALID`、`SEMANTIC_RESULT_KEYS_MISMATCH`、`SEMANTIC_SCORE_NOT_ALLOWED`、`SEMANTIC_EVIDENCE_REQUIRED`、`SEMANTIC_EVIDENCE_UNKNOWN`、`SEMANTIC_REASON_LANGUAGE_INVALID`。
- 合分与公共校验：`SCORE_VALUE_INVALID`、`SCORE_COMPONENT_INVALID`、`CRITERION_KEY_INVALID`、`GRADING_TYPE_INVALID`、`GRADING_WEIGHTS_INVALID`、`FINAL_CRITERIA_INVALID`。

`SEMANTIC_CRITERIA_UNRESOLVED` 和 `SEMANTIC_NO_JUDGED_CRITERIA` 是结构化 semantic component 中的 `error.code`；它们返回 `evaluation_error / score=null`，不抛出异常。

backend 可恢复失败与契约失败应在外围评分 attempt 中分别记录，不要吞掉错误后生成有效 `score.json`。

## 运行时与后续边界

私有 scoring 包合入、候选只读副本、GT 后置、真实本机路径映射以及本地 Worker 由 G3-02 的 `scripts/score_general_e2e.py` 实现，不进入 core。具体操作和平台状态见[本地受管规则运行时](local-rule-runtime.md)。

G3-04 已在外围评分 attempt 中接入 Codex 评分会话，G3-05 又接入 API Judge transport、输入裁剪、重试和独立审计；两者都只向 core 提供已验证的 backend 结果，不改变 transport-neutral 边界。G4-03 已完成真实 Codex 五题闭环、submission、回传和报告；Skill 现为 `operational`。Windows、60 题全量和裁判校准仍需独立验收。

专用虚拟环境和独立进程只提供依赖复现、故障收口与进程隔离，不是针对恶意 grader 的安全沙箱。General E2E 的规则代码来自冻结且受信任的数据集；其中启动的候选子进程仍必须在凭据清空、无额外网络授权、超时和进程树清理约束下运行。
