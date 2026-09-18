# G3-05 API Judge 验收证据

2026-09-18 在 macOS 开发机完成 `api-judge-v1` 的三种 transport、独立审计和真实 API smoke。`score-general-e2e` 升级为 `0.5.0/interface_only`，`orchestrate-general-e2e` 升级为 `0.4.0/interface_only`。General E2E 评分仍不依赖 Docker。

## 已实现边界

- `anthropic-messages`：`<base_url>/v1/messages`，支持 system/user prompt、requested/returned model、stop reason、input/output/cache usage。
- `openai-chat-completions`：`<base_url>/chat/completions`，支持 JSON object response、reasoning effort、finish reason、input/output/cache/reasoning usage。
- `openai-responses`：`<base_url>/responses`，使用 Responses `input`、`text.format`、`max_output_tokens` 和 `reasoning.effort`，解析 message/output_text 与 Responses usage。
- API runtime 冻结 provider、endpoint 与 SHA、模型、reasoning 参数方式、输入/单项证据预算、输出上限、timeout、max attempts 和凭据环境变量名；凭据值不进入 attempt、审计、文档或报告。
- 候选和轨迹只作为证据；每项保留 complete/truncated/omitted 元数据。judged criterion 只能引用实际包含内容的 evidence ID，并必须声明支持证据与反例均已检查。
- 每次尝试分别保存无凭据请求、provider 响应、解析结果和 digest。HTTP 及结构错误只按冻结策略重试，不切换 provider/model/protocol，不回退 Codex。
- API 最终失败生成 `evaluation_error / total_score=null`；恢复复用已有终态。若请求已写入但响应终态不确定，以 `API_JUDGE_ATTEMPT_OUTCOME_UNKNOWN` 失败关闭，避免无法证明安全时双重调用。
- 编排器使用 `API_READY / API_RUNNING / SCORE_VERIFICATION_PENDING / SCORE_RECORDED`，外调前先持久化状态；API 分支没有 Codex Prompt、project 或 thread。

## 真实 API 样本

主准入样本使用显式的 `anthropic-messages + anthropic/claude-opus-5` 纯 Judge 真实 smoke：

- attempt count 1，retry count 0；
- returned model `claude-opus-5`，与去除 transport 前缀后的 requested model 一致；
- input/output tokens 为 2530/636；
- `evaluation_status=completed`、`score_valid=true`、`total_score=0.6`；
- score SHA-256 `c12c34780332f12d359380e59d0ed2420b5edfba3b3c38bf6a25bf3e7d8efe10`；
- endpoint SHA-256 `c25ebfb04201c445d305a6ab5697a7b7a8c5e4651b6cb9948d8061fb1a68d593`；
- `fallback_used=false`、`docker_used=false`。

OpenAI-compatible 补充样本使用 `openai-chat-completions + xopglm52`，同样单次完成：input/output 2573/255，requested/returned model 均为 `xopglm52`，`score_valid=true`、`total_score=0.7`，fallback/docker 均为 false。OpenAI Responses 因真实 API 已完成准入且用户明确要求不重复调用，只做冻结请求形状、响应解析、usage 和合分 fixture；不把 fixture 冒充第二次真实 API 证据。

本机旧 Anthropic token 的 401 和在 MaaS endpoint 请求无路由 Claude 模型的 400 都只调用一次，未重试，并形成合法评测异常。这些负样本用于证明非 retryable 状态和无 fallback，不是能力分。

所有真实调用均在临时目录中执行；密钥只注入调用进程，临时 attempt 随进程退出删除。仓库只保留本脱敏证据索引，不保存原始 provider body 或凭据。

## 自动化与发行门禁

- `tests/general_e2e/test_general_api_judge.py`：三种 API transport、hybrid/纯 Judge、输入截断、解析重试、凭据缺失、重试耗尽、终态复用、usage/cache/reasoning token 和 endpoint 失败关闭。
- `tests/general_e2e/test_general_scoring_orchestration.py`：API 队列与 Codex project/thread 分支隔离，凭据只按冻结环境变量名传递。
- Codex G3-04 路径继续运行原语义评分回归，API 接入不改变 response template、query log 或 `record-semantics`。
- General E2E 102/102、旧 `eval_e2e` 60/60、Web 6 + General 7 共 13 个 Skill `quick_validate.py`、layout（7 Skills/5 components/0 errors）、Python 编译及 `git diff --check` 均 PASS。
- 独立 General release 的 build、release-root verify 与 suite verify 均 PASS；catalog digest 为 `8a75d212f621d36fa88632c8ea5bc388aae2d4dadf8c2d4290b0aaf29e2d137d`，suite SHA-256 为 `cf9caf3a08099d2f7ed1833e3193936b5a6c23e7c969300547a7d81e141e2d6e`。
- 在清空 `PYTHONPATH` 的脱仓目录中，score/orchestrate API 命令入口均可运行；`openai-responses` 无凭据样本形成 `evaluation_error / total_score=null`，随后由脱仓 `verify-score` 验证为合法的无效评分终态，没有发起网络请求。
- 提交前凭据痕迹扫描 PASS；仓库变更不包含 API key、原始 provider body 或其他真实调用秘密。

## 未覆盖边界

- Windows 真实 API 评分与崩溃恢复仍转入 G5 真机验收。
- 本项不完成 submission、跨 attempt 重新评分契约、报告聚合或真实 Codex Judge 小批，因此两个 Skill 继续保持 `interface_only`。
