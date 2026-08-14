# DeepSeek Harness 正式集成设计

## 决策摘要

在已验证的独立 Docker 与 transcript/usage 转换 PoC 之上，新增原生
`DeepSeekHarnessAgent(BaseAgent)`，通过
`eval/run_batch.py --agent-backend deepseek-harness` 进入 WildClawBench 的任务解析、
容器执行、评分、usage、异常检测和产物归档生命周期。

正式 backend 默认使用 OpenAI Chat Completions，并允许显式选择 OpenAI Responses。
协议与 endpoint 必须由调用方成对配置；实现不根据 `/v1`、`/v2` 后缀猜测协议。
首轮验收以文本/工具任务的真实评分闭环为准，不把 live DeepSeek Search 或 native
multimodal 纳入本次完成条件。

## 方案选择

采用原生 `BaseAgent` backend，而不是从 `run_batch.py` 包装
`tools/deepseek_harness_poc.py`。PoC runner 会在 DSH 退出后删除容器，不能满足评分器
后续复制 ground truth、读取容器内 transcript 和收集 workspace changes 的要求。

不抽取跨 Harness 的通用 CLI backend 基类。OpenCode、Codex 和 DSH 的 session、usage、
协议及工具行为不同，本次为追求复用而改造其他 backend 会扩大回归面。

## 工作树与分支

实现位于项目根目录的
`.agents/deepseek-harness-integration` worktree，分支为
`feat/deepseek-harness-integration`。该分支从已提交的
`feat/deepseek-harness-poc` 创建，因此直接复用 Dockerfile、`wcb-dsh` 和
`src/agents/deepseek_harness/transcript.py`。

## Backend 结构

新增 `src/agents/deepseek_harness/runner.py`，并由
`src/agents/deepseek_harness/__init__.py` 导出 `DeepSeekHarnessAgent`。

`DeepSeekHarnessAgent` 实现以下 `BaseAgent` 契约：

- `expects_gateway = False`。
- `transcript_container_path` 指向
  `/root/.openclaw/agents/main/sessions/chat.jsonl`，兼容现有评分器。
- `run_task()` 管理常驻容器、workspace、skills、warmup、DSH 执行、session 导出和
  transcript 转换。
- `prepare_grading_transcript()` 返回已回灌容器的归一化 transcript 路径。
- `collect_usage()` 读取转换器产生的 usage，补充 elapsed time，并在缺失时返回零值结构。

runner 复用 `src.utils.docker_utils` 中的资源限制、warmup 和 workspace baseline 工具。
DSH 的 skill 名称约束和调用方式与其他 Harness 不同，因此由
`src.agents.deepseek_harness.skills` 提供专用暂存、安装和 prompt 构造逻辑。

## 容器生命周期

1. 校验模型凭据和 API 类型，并解析 endpoint。
2. 使用 `DOCKER_IMAGE_DEEPSEEK_HARNESS` 指定的镜像启动 detached 容器；默认镜像为
   `wildclawbench-deepseek-harness-ubuntu:v0.0`。
3. 使用 `--entrypoint /bin/bash` 覆盖镜像的任务 entrypoint，以 `tail -f /dev/null`
   保持容器运行，直到 `run_batch.py` 完成评分和产物采集。
4. 将 `<workspace>/exec` 只读挂载到 `/mnt/wildclaw_src`，再复制到可写的
   `/tmp_workspace`。不存在 `exec` 时创建空目录并记录 warning。
5. 使用与 DSH `yaml.parse` core schema 对齐的 YAML 1.2 标量解析读取每个任务 skill 的
   frontmatter：`on/yes` 和日期保持字符串，`true/false`、`0o` 八进制和无小数点指数
   等数字按非字符串处理；重复 mapping key 在 Docker 操作前明确失败。将名称规范化为
   DSH 要求的小写 kebab-case（例如 `03_task2` 转为 `03-task2`）。若多个声明归一到同一
   名称，则在 Docker 操作前明确失败。
6. 将完整 bundle 暂存到宿主临时目录，保留 `references`、`scripts`、`assets` 等资源；
   只修改暂存副本的 `SKILL.md`，按顶层 mapping pair 的词法 token 更新 `name` 值；支持
   带 tag/anchor、alias 和 block scalar 的输入定位，输出规范化的普通字符串 `name`，并
   保留未修改内容的原始换行（包括 CRLF）。同时将 `{baseDir}` 替换为
   `/root/.dsh/skills/<normalized-name>`，再复制到容器同名目录。原始 task skill 不变。
   为兼容其他 backend 的既有行为，声明的 bundle 不存在时记录 warning 并跳过，不为其
   生成调用 gesture；路径越界、YAML 非法、字段类型不符、符号链接 `SKILL.md` 或名称
   冲突仍在 `preparing_skills` 阶段明确失败。
7. 在原任务 prompt 前按声明顺序加入 `/<normalized-name>`。这是 DSH 原生 direct skill
   invocation gesture，会由 `dsh-tool-skill` 注入完整 skill 内容；runner 不拼接正文。
8. 运行任务 warmup，保存 workspace baseline，再执行 DSH。
9. DSH 结束或失败后，在容器仍存活时导出 session、转换 transcript，并把
   `chat.jsonl` 复制回评分器固定路径。
10. `run_batch.py` 在评分、usage、task output 和 anomalies 完成后统一删除容器。

## 模型与协议配置

新增 CLI 参数：

- `--agent-backend deepseek-harness`
- `--dsh-api {openai-completions,openai-responses}`

`--dsh-api` 未提供时依次读取 `DSH_API`，最终默认
`openai-completions`。runner 将选择结果作为 `DSH_API` 传入容器。

模型通过现有 `--model` 指定。WildClawBench 路由形式
`openrouter/xopglm52` 在交给 DSH 前只移除第一个 `openrouter/` 前缀，得到
`xopglm52`；`openrouter/anthropic/model` 对应 `anthropic/model`。不含该前缀的模型 ID
保持原样。

`OPENROUTER_BASE_URL` 原样传入 DSH，不调用 OpenClaw endpoint normalizer：

- 本次已验证 MaaS 的 Chat 配置为 `openai-completions` + `/v2`。
- 本次已验证 MaaS 的 Responses 配置为 `openai-responses` + `/v1`。

URL 后缀不是跨 provider 的协议标识，因此 runner 不自动重写或推断。
未设置 `OPENROUTER_BASE_URL` 时沿用 `wcb-dsh` 的 OpenRouter 默认地址
`https://openrouter.ai/api/v1`。

## 凭据与环境变量

模型调用要求非空 `OPENROUTER_API_KEY`。可选 `DEEPSEEK_API_KEY` 继续供 DSH 原生
DeepSeek Search 使用，但缺少该 Key 不阻止普通文本/工具任务启动。

runner 还传递容器代理变量、任务 frontmatter `env` 和 lobster env。日志只记录环境变量
名称或掩码，不记录完整值。host 侧 `execution_status.json`、runner log、转换 manifest
和 transcript 不写入模型凭据。

## DSH 执行

任务 prompt 先写入容器内临时文件，再由
`/usr/local/bin/wcb-dsh "$(cat <prompt-file>)"` 执行，避免把完整任务文本和 shell
元字符拼入 host 命令。`AgentTaskSpec.thinking` 映射到 `DSH_REASONING`；现有
`wcb-dsh` 会为 hand-declared 模型同步声明相同 `reasoningEfforts`。

runner 捕获 DSH stdout/stderr 到 host `agent.log`，并把退出码、timeout、Harness 版本、
镜像、API 类型和失败阶段写入 `execution_status.json`。timeout 后必须停止容器内 DSH
进程，避免评分期间继续修改 workspace。

## Session、Transcript 与 Usage

原生 session 从 `/root/.dsh/sessions` 复制到
`<output_dir>/dsh_sessions`，不压缩、不修改。复用
`write_conversion()` 生成：

- `<output_dir>/chat.jsonl`
- `<output_dir>/usage.json`
- `<output_dir>/conversion_manifest.json`

`chat.jsonl` 复制到容器内
`/root/.openclaw/agents/main/sessions/chat.jsonl`，供安全类和 LLM judge 评分器读取。

`collect_usage()` 读取 token、cache 和 request count；`elapsed_time` 使用 runner 实测值。
DSH 原生事件没有可信 USD 成本时保持 `cost_usd = 0.0`，本次不根据未知价格编造成本。

## 错误与降级

- 缺少 `OPENROUTER_API_KEY` 或 API 类型非法时，在模型请求前返回明确错误；未设置
  endpoint 时使用 OpenRouter 默认地址。
- 容器启动、workspace、skills、warmup、workspace baseline、DSH 执行和 session export
  分别记录 failure stage；skills、warmup、baseline 分别使用 `preparing_skills`、
  `preparing_warmup`、`snapshotting_workspace`。
- 已知框架/Harness 阶段中的 Docker daemon、容器缺失、只读文件系统、磁盘耗尽和 DNS
  等基础设施错误优先归因 `evaluation_environment` 并要求重跑；没有结构化阶段时不因
  错误文本单独升级归因。
- 声明的 skill bundle 缺失时继续执行以保持既有 backend 兼容性，但同时把声明名写入
  `execution_status.json.missing_skills` 和 `runner.log` 的结构化事件；anomalies 生成
  `DECLARED_SKILL_MISSING`，按确定性的评测依赖缺失判为 validity `FAIL` 并要求修复后重跑。
- DSH 非零退出或 timeout 后仍导出已有 session，并尝试转换 transcript/usage。
- session 转换失败时保留 `dsh_sessions`，记录转换错误，并让 backend 返回 error。
- backend 加入 `grade_on_error` 范围；已有自动检查或 rubric 时，即使 Harness 执行失败也
  尝试评分已产生的 workspace 结果。
- backend 加入 workspace changes 收集范围，确保失败前生成的文件仍进入归档。
- `run_batch.py` 继续在 finally 中负责容器清理，runner 不提前删除容器。

## 工具指标与报告实体

`src.utils.tool_metrics` 注册 `deepseek-harness` classifier。转换器保留 DSH
`tool_result.status`：`completed` 计为成功，`error` 计为失败，`running/pending` 计为
不确定；缺少状态但有结果内容时计为成功。该口径与 DSH 转换产物一致，不借用其他
Harness 名称伪装统计。

`tools/report/data/entities.yaml` 注册：

- ID：`deepseek-harness`
- 展示名：`DeepSeek Harness`
- family：`DeepSeek Harness`

本次保证报告发现、展示和工具指标可用；分档成本估算不在本次范围，usage 中的真实
token 计数继续保留。

## 代码与测试范围

新增或修改：

- `src/agents/deepseek_harness/runner.py`
- `src/agents/deepseek_harness/skills.py`
- `src/agents/deepseek_harness/__init__.py`
- `src/utils/cli_args.py`
- `eval/run_batch.py`
- `src/utils/tool_metrics.py`
- `tools/report/data/entities.yaml`
- `docker/deepseek-harness/README.md`
- `tests/test_deepseek_harness_runner.py`
- `tests/test_deepseek_harness_skills.py`
- `tests/test_deepseek_harness_integration.py`
- `tests/test_tool_metrics.py`
- 相关 CLI、run_batch 和报告实体测试

实现遵循测试驱动：先验证失败测试，再实现最小行为。单元测试覆盖：

- CLI backend 与 API choices。
- 模型 ID 规范化和 base URL 不重写。
- detached 容器命令、环境变量掩码和缺凭据失败。
- workspace、skill 名称规范化、完整 bundle 暂存、原生 gesture、warmup、thinking 与
  prompt 文件传递。
- 正常、非零退出、timeout、转换失败的状态和产物。
- transcript 回灌、usage 与 workspace changes/grade-on-error 注册。
- DSH 工具指标和报告实体。

## 真实验收

首次使用完整 task workspace 的真实评测已经跑通容器、工具调用、session、usage、评分
和归档链路，但 transcript 中没有 skill catalog 或 skill 加载记录。模型最终写入
`results/action_list.md`，评分器因此按既有契约报告 `results.md not found`。DSH 源码确认
`skill-filesystem` 仅接受 `^[a-z0-9]+(?:-[a-z0-9]+)*$`，原始 `name: 03_task2`
会在发现阶段被忽略。上述专用暂存和 `/<name>` gesture 修复了该接入缺陷。

修复后已使用正式镜像、Chat `/v2`、`xopglm52`、`--thinking high` 重新运行：

`tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md`

`eval/run_batch.py` 退出 0，本次单任务真实评测通过以下门槛：

- `execution_status.json` 为 `finished`，记录 DSH `0.1.0-rc.6`、
  `openai-completions`、模型 `xopglm52` 和 Harness exit code 0。
- `score.json` 由真实评分流程生成，`overall_score = 0.6218`、`error = null`。
- `task_output/workspace/results/results.md` 存在且为 11,209 bytes；宿主输入 workspace
  保持只读，不作为输出正确性的依据。
- 原生 `dsh_sessions`、`chat.jsonl`、`conversion_manifest.json` 和 `usage.json` 均存在。
  conversion message count 为 25；转换 transcript 含 11 条 assistant、10 个 tool use 和
  10 个 tool result。
- usage 的 `request_count = 11`、`total_tokens = 134664`。
- 原生 session 含 1 个 skill catalog 和 1 个 direct skill invocation，未调用 `skill`
  tool，证明 `/<name>` gesture 已直接加载完整 skill 内容。
- `anomalies.json` 的 `validity_verdict = PASS`，且无 validity failure。
- scoped validity checker 为 `REVIEW`：error 0、warning 1；唯一
  `SUMMARY_MISSING` 是单任务结果没有 `summary_all_*.json`，不能写成 checker 全 PASS，
  也不是任务 validity failure。
- 对生成产物执行了完整凭据值扫描，未发现配置的模型或 judge 凭据。

Responses `/v1` 的 runner 配置由单元测试覆盖，并保留此前 PoC 的真实 E2E 证据；本轮
无需重复跑正式评分。本次只证明该文本/工具单任务的正式评测闭环；live DeepSeek
Search、native multimodal、全量 benchmark 和分档成本估算作为后续独立验收项。额外的
invocation frontmatter（例如 `disable-model-invocation`、`user-invocable`）校验与
策略组合未在本轮覆盖；当前纳入的任务 skill 未声明这些字段。
