# G3-06 验收证据索引

## 结论

- `score-general-e2e 0.6.0/interface_only` 可从通过 `verify-score` 的终态源 attempt 创建独立重评分 attempt，冻结 lineage 并重建干净 runtime。
- `orchestrate-general-e2e 0.5.0/interface_only` 会在评分前拦截不可信执行或不完整证据，并在终态 submission 中严格区分 `valid`、`evaluation_error` 与 `unscored`。
- 有效 0 分保持 `valid=true / total_score=0.0`；Judge 服务失败保持 `total_score=null`；执行 timeout、取消、基础设施失败或必要证据缺失不进入能力零分。
- API 与 Codex 后端切换只通过新 orchestration 和新 attempt 完成，不是 fallback；源 state、submission、attempt 和 score 不被修改。

## 实现证据

- `score_general_e2e.py prepare-rescore`：校验源终态，复制冻结候选、任务、contract、GT、轨迹和运行时锁，记录源 manifest/score/Judge/候选 SHA，拒绝复用 attempt ID 或覆盖目标。
- `orchestrate_general_e2e.py build-submission`：完整枚举冻结范围，重新执行 `verify-score`，锁定执行/评分 attempt、候选、证据与 score SHA；恢复时重算预期内容。
- `orchestrate_general_e2e.py init-rescore`：要求源 orchestration 终态且已有锁定 submission，显式冻结新的 protocol/model/reasoning/API runtime，并创建独立队列。
- `general-contracts 1.0.0` vendored 到 orchestrate Skill，脱离仓库后仍能校验标准 score/submission 契约。

## 离线验证范围

- 编排聚焦测试覆盖有效 0 分、合法评测异常、执行 timeout、证据不完整、完整范围与顺序、submission 内容漂移/范围缩小、API 失败转 Codex 重评分、源文件哈希不变和目标不可覆盖。
- API Judge 既有离线 fixture 继续覆盖 Anthropic Messages、OpenAI Chat Completions、OpenAI Responses、重试、无凭据失败及终态不重复请求。
- General E2E 106/106、旧 `eval_e2e` 60/60、编排聚焦 10/10、API Judge 聚焦 7/7、layout（7 Skills/6 components/0 errors）、Python 编译与 `git diff --check` 均通过；13 个场景 Skill 继续通过 `quick_validate.py`。
- 独立发行 build、release-root verify 和 suite verify 均通过；开发态 catalog digest 为 `670355d0b7d44a4974499f139708932857a18f7a987d5d22343f8eca5ce6c3f0`，suite SHA-256 为 `89ca7707e4ebddf960c201c806026d0966040429e8c6bca7a2b770035ccfc9ce`。提交后的正式 source revision 与哈希需重新构建，不能把开发态标识当作正式发行。
- 清空 `PYTHONPATH` 后，在解包的独立 score/orchestrate Skill 中完成无凭据 API 失败、`evaluation_error` submission、API → Codex `init-rescore` 和 lineage 断言；解包后的命令执行阶段未读取 checkout 运行时代码。

本项没有再次调用真实 Judge API，也没有启动 Docker。G3-05 的既有真实 API smoke 结论未重复执行；真实 Codex Judge 小批和 Windows 真机仍为 `NOT_RUN`，不由本项 fixture 推断。
