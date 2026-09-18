# General E2E 评分 core 接口

`score-general-e2e` 0.5.0 装配 `grading-core` 0.1.1。core 只负责规则依赖审计、结果校验、证据索引、语义结果校验和合分，不拥有评分工作空间、本地进程运行时、模型调用或任务调度。

发行包内模块位于 `vendor/e2e-shared/wildclawbench_grading_core/`。调用方把其父目录加入 Python 模块搜索路径后导入 `wildclawbench_grading_core`。core 仅依赖 Python 标准库；任务规则所需的 PyYAML、Playwright 和 Chromium 属于 G3-02 专用评分虚拟环境，不安装到控制 Harness 使用的 Python 环境。

## 公开 API

### `run_rules()`

输入任务 `automated_checks`、受管 `executor`、本地 runtime 副本的真实 `workspace_path`、可选标准轨迹和预期 criterion key。core 先校验 AST、唯一同步 `grade()` 入口及静态 import，再调用注入的 executor，严格校验返回 key、`overall_score`、有限数值和 `[0,1]` 范围。

非空规则必须提供受管 executor。不要在控制 Harness 或评分编排进程中使用 `exec()`，也不要用任意宿主临时目录绕过评分目录门禁。G3-02 应让 executor 通过结构化 IPC 调用专用虚拟环境中的独立 Python Worker，把一次性 runtime 副本的真实绝对路径作为 `workspace_path` 传给 `grade()`，并返回 JSON 对象。

### `build_evidence_index()`

输入证据引用、可选证据根目录和已知 transcript event ID。相对路径必须是 POSIX 安全路径；提供根目录时会验证普通文件和 SHA-256，提供事件集合时会验证每个 event ID。返回确定性索引和 canonical JSON digest。

### `evaluate_semantics()`

输入 rubric criteria、注入的语义 evaluator、冻结证据索引和协议。支持 `codex-agent-judge-v1`、`api-judge-v1`；没有语义 criterion 时使用 `not-required`。evaluator 的每个已判定 criterion 必须使用允许分值并引用冻结索引中的证据。未判定 criterion 返回 `evaluation_error` 和 `score=null`，不能补零。

这个 API 校验 backend 结果，但不创建 Codex 评分任务、不发送 API 请求，也不实现重试或 backend 切换。

### `finalize_score()`

输入 `automated`、`hybrid` 或 `llm_judge` 类型、原始权重以及规则和语义组件。它校验必需组件状态、权重和 criterion 唯一性；组件缺失或评测异常时返回 `valid=false`、`total_score=null`。有效结果按冻结权重合分。

## 稳定错误

契约或执行失败抛出 `GradingCoreError`，其 `code`、`message`、`details` 可序列化为 `as_dict()`。调用方按责任域处理以下稳定 code：

- 规则与依赖：`RULE_SOURCE_INVALID`、`RULE_ENTRYPOINT_INVALID`、`RULE_CONTEXT_INVALID`、`RULE_CONTRACT_INVALID`、`RULE_EXECUTOR_REQUIRED`、`RULE_EXECUTION_FAILED`、`RULE_RESULT_INVALID`、`RULE_RESULT_KEYS_MISMATCH`、`RULE_RELATIVE_IMPORT_UNSUPPORTED`、`RULE_DYNAMIC_IMPORT_UNSUPPORTED`、`RULE_DEPENDENCY_UNDECLARED`、`DEPENDENCY_CATALOG_INVALID`。
- 证据：`EVIDENCE_ROOT_INVALID`、`EVIDENCE_PATH_INVALID`、`EVIDENCE_FILE_MISSING`、`EVIDENCE_DIGEST_MISMATCH`、`EVIDENCE_EVENT_MISSING`、`EVIDENCE_REFERENCE_INVALID`、`EVIDENCE_REFERENCE_DUPLICATE`、`EVIDENCE_INDEX_INVALID`。
- 语义：`SEMANTIC_CONTRACT_INVALID`、`SEMANTIC_PROTOCOL_INVALID`、`SEMANTIC_EVALUATOR_REQUIRED`、`SEMANTIC_BACKEND_FAILED`、`SEMANTIC_RESULT_INVALID`、`SEMANTIC_RESULT_KEYS_MISMATCH`、`SEMANTIC_SCORE_NOT_ALLOWED`、`SEMANTIC_EVIDENCE_REQUIRED`、`SEMANTIC_EVIDENCE_UNKNOWN`。
- 合分与公共校验：`SCORE_VALUE_INVALID`、`SCORE_COMPONENT_INVALID`、`CRITERION_KEY_INVALID`、`GRADING_TYPE_INVALID`、`GRADING_WEIGHTS_INVALID`、`FINAL_CRITERIA_INVALID`。

`SEMANTIC_CRITERIA_UNRESOLVED` 和 `SEMANTIC_NO_JUDGED_CRITERIA` 是结构化 semantic component 中的 `error.code`；它们返回 `evaluation_error / score=null`，不抛出异常。

backend 可恢复失败与契约失败应在外围评分 attempt 中分别记录，不要吞掉错误后生成有效 `score.json`。

## 运行时与后续边界

私有 scoring 包合入、候选只读副本、GT 后置、真实本机路径映射以及本地 Worker 由 G3-02 的 `scripts/score_general_e2e.py` 实现，不进入 core。具体操作和平台状态见[本地受管规则运行时](local-rule-runtime.md)。

G3-04 已在外围评分 attempt 中接入 Codex 评分会话，G3-05 又接入 API Judge transport、输入裁剪、重试和独立审计；两者都只向 core 提供已验证的 backend 结果，不改变 transport-neutral 边界。submission、回传包、真实 Codex 小批和 API Judge 生产准入仍未交付，因此 Skill 继续保持 `interface_only`。

专用虚拟环境和独立进程只提供依赖复现、故障收口与进程隔离，不是针对恶意 grader 的安全沙箱。General E2E 的规则代码来自冻结且受信任的数据集；其中启动的候选子进程仍必须在凭据清空、无额外网络授权、超时和进程树清理约束下运行。
