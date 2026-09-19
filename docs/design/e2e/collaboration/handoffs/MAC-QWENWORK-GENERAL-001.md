# MAC-QWENWORK-GENERAL-001：只读适配与 CB-B 接口需求

| 字段 | 值 |
| --- | --- |
| 交接 ID / 创建时间 | `MAC-QWENWORK-GENERAL-001` / 2026-09-19 17:26 +08:00 |
| 来源任务 / 唯一负责人 | `MAC-QWENWORK-GENERAL` / 独立 macOS 开发任务 |
| 目标任务 | COMMON |
| 基线 / 实现 SHA / 必需依赖 | 推荐源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a`；实现 `3f4ccbced1e90d71bea66508dfe8cca698bc7bea`；依赖 COMMON-001 / CB-A `abce5da832f16b48cd402ceef04a6abda544a379` |
| 集成分支 / 集成状态与 SHA | `feature/astroncode-eval` / 未集成、未 push；由 COMMON 审查后登记原始→集成 SHA |
| 修改范围 | `eval_general_e2e/adapters/qwenwork/`；General execute 下 `drivers/qwenwork/`；QwenWork 专属 tests/fixtures；P1 证据与本任务卡 |
| 关联任务与验收 ID | COMMON-CB05、COMMON-IN01；MAC P1/P2/P3；C02/C04/C07/C09/C13–C16、CV01/CV02/CV11/CV12、G04/G05 |

## 变化与兼容性

实现提供 QwenWork macOS General 的客户端专属只读基础：动态应用发现、runtime/Profile 身份、SQLite 一致快照、session/cwd/终态映射、失败关闭的会话选择、CB-A 通用状态构造、transcript/tool outcome 规范化和资源原始字段解析。公共 thread/turn 在 QwenWork 没有已证明的等价字段，CB-A 输出保持 `null`；稳定原生 `sub_chats.session_id` 映射公共 `session_id`。

没有修改公共 Schema、run 入口、finalizer、指标公式、组件目录或构建器。新增 `eval_general_e2e/adapters/qwenwork/components.json` 只声明已有 `desktop-runtime 1.0.0`、`desktop-app-discovery 1.1.0`、`resource-metrics 1.0.0`，显式布局检查通过。发行时不能从 Skill 跨目录 import 该 canonical adapter；COMMON 的构建装配须将批准的专属源码与声明组件放入相应 Skill 闭包。

当前安装 QwenWorkCN `1.0.6`、SDK `1.0.28`、transcript `1.1.32` 和 runtime SHA 与历史 macOS 1.0.5 Profile 一致，但客户端版本不同，不能继承归一化证明。私有 observation 保留原生 usage 和 `unverified`；现行 General semantic validator 不允许 `unverified + null`，因此严格 resource v1 发布视图使用 `unavailable + null + coverage 0/N` 并带 `QWEN_TOKEN_SEMANTICS_UNVERIFIED`。COMMON 需决定后续统一语义；本分支没有私改 Schema。

现有 AstronStudio 状态、Schema 和测试均未修改，公共 55 项回归通过。旧 QwenWork Web 或历史 macOS 证据不失效，但也不能覆盖 General/current 1.0.6。合入代码不等于 QwenWork 真机执行、正式 collect 或生产发行通过。

## 已有证据与未验证范围

Git 可取得的脱敏证据：[qwenwork-macos-readonly-20260919](../../../general-e2e/evidence/qwenwork-macos-readonly-20260919/README.md)及 `tests/general_e2e/fixtures/qwenwork/`。原始日志未入仓；本机 probe 报告位于 `/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-e2e/probe-20260919.json`，SHA-256 `fa762864f2d931a57156d6dde3d0ec88ba699e1e4a51efe090de23f5e13f5da9`、大小 3151 bytes。

本机只读证据：QwenWork 主进程 0、CDP 未开放、SQLite `quick_check=ok`、历史会话 21、active/pending 0；21/21 具备 session/conversation/sub-chat/local-project/cwd；终态字段包含 completed/cancelled/interrupted；transcript 版本唯一 `1.1.32`。该结果只证明字段可读和映射可实现，没有复用历史任务作为 General smoke。

验证命令和结果：

```text
python -m unittest discover -s tests/general_e2e -p test_run_general_e2e.py       # 14/14
python -m unittest discover -s tests/general_e2e -p test_shared_components.py     # 8/8
python -m unittest discover -s tests/general_e2e -p test_skill_layout.py           # 6/6
python -m unittest discover -s tests/general_e2e -p test_contracts.py              # 10/10
python -m unittest discover -s tests/general_e2e -p test_e2e_build.py              # 17/17
python -m unittest tests.general_e2e.test_qwenwork_adapter                          # 3/3
node --test tests/general_e2e/qwenwork_adapter.test.mjs tests/general_e2e/qwenwork_probe.test.mjs  # 12/12
git diff --check                                                                     # PASS
```

Python 使用主工程既有 `.venv`；worktree 未创建/安装新虚拟环境。测试覆盖 Profile 漂移、背景 turn 排除、请求/终值对账、null/subtotal/coverage、tool exit status、CB-A null ID、严格 resource contract 和只读操作边界。

未验证：当前模型/权限/UI 控件、启动/CDP 归属、目录选择、一次发送、发送临界恢复、真机终态/追问/授权/超时/停止、纯回复和文件任务、当前 1.0.6 非零 Token 对账、正式 collect/评分/回传/报告、并发、仓库外发行。

## 接收方动作

| 接收任务 | 要求级别 | 下一动作/真实入口与配置 | 通过条件/验收 ID | 失败或缺依赖时 |
| --- | --- | --- | --- | --- |
| COMMON | REQUIRED_BEFORE_EXECUTION | 审查并集成 `3f4ccbced1e90d71bea66508dfe8cca698bc7bea`；运行本交接列出的公共 55 项和 QwenWork 15 项测试；登记原始→集成 SHA | COMMON-IN01；测试全通过；QwenWork binding 仍只引用 canonical 公共组件 | 不改写平台提交；记录具体失败文件/fixture，平台可继续不依赖公共修改的 UI Driver 离线工作 |
| COMMON | REQUIRED_BEFORE_CLAIM | CB-B 支持一个 attempt 的 transcript + 多 segment artifact、状态库绑定 provenance、只有 session ID 的原生身份映射，以及 QwenWork 进程清理 hook | COMMON-CB05、C13/C14/G04/G05；不要求伪造 thread/turn/lifecycle；哈希/size/range/cwd/session 可交叉核验 | 保留私有 evidence，不生成正式 trace-index/collect receipt，不声明评分闭环 |
| COMMON | REQUIRED_BEFORE_CLAIM | 将 QwenWork execute/collect 专属源码和声明的 vendor 组件装配进 Skill/发行闭包；决定未知 Profile 在下一公共格式中的状态表示 | C15/C19/CV01/CV12；仓库外运行不 import Web Skill 或仓库 `eval_general_e2e` 路径；缺失值语义可通过统一 validator | 维持当前私有 `unverified` + 严格 v1 `unavailable/null`；不私改 v1 Schema |
| COMMON | INFORMATIONAL | 为本任务安排 QwenWork 桌面独占时段；不替代运行前 active session/CDP/配置复核 | CV02/CV03/CV04/CV07；一个全新 canary 一次发送，同 attempt 恢复不重发 | 无时段时继续离线 UI locator/journal 测试，不启动或操作客户端 |

## 接续与风险

本任务下一项是在控制任务分配的独占时段完成一个全新 General canary：运行前只读 probe，保持用户当前模型/权限，回读 UI 配置，选择完整 Workspace，新建任务并只发送一次，捕获 session/cwd，按同 attempt 验证恢复。发送边界、会话 ID、未知交互或停止确认任一不明确时进入 `NEEDS_ATTENTION`，不重发、不冻结。

回退可直接停用 QwenWork adapter；未修改公共 wire 或旧 adapter。不得用当前源代码/fixture PASS 代替真机或正式 collect，不得因 SDK/runtime 相同而把 1.0.5 Token Profile 放宽到 1.0.6。
