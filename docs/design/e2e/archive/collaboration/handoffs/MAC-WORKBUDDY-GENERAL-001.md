# MAC-WORKBUDDY-GENERAL-001：只读适配与 CB-B 接口需求

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 创建时间 | `MAC-WORKBUDDY-GENERAL-001` / 2026-09-19 17:37 +08:00 |
| 来源任务 / 唯一负责人 | `MAC-WORKBUDDY-GENERAL` / 独立 macOS 开发任务 |
| 目标任务 | COMMON |
| 基线 / 实现 SHA / 必需依赖 | 创建 base `03c38f280a64ad9bc9308c768f0f5795050355cc`；推荐源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a`；实现 `2112a86450ba2f22fb284d37a20921cd7e65db69`；依赖 COMMON-001 / CB-A `abce5da832f16b48cd402ceef04a6abda544a379` |
| 集成分支 / 集成状态与 SHA | `feature/astroncode-eval` / 未集成、未 push；由 COMMON 审查后登记原始→集成 SHA |
| 修改范围 | `eval_general_e2e/adapters/workbuddy/`；General execute 下 `drivers/workbuddy/`；WorkBuddy 专属 tests/fixtures；P1 证据与本任务卡 |
| 关联任务与验收 ID | COMMON-CB05、COMMON-IN01；Mac P1/P2/P3；C02/C04/C07/C09/C13–C16、CV01/CV02/CV04/CV11/CV12、G04/G05 |

## 变化与兼容性

实现提供 WorkBuddy 5.5.3 macOS General 的客户端专属只读基础：共享应用发现的版本化安装变体、原生 session/cwd/终态映射、CB-A 通用状态构造、Workspace history 定位、conversation/request/message 精确绑定、轨迹/tool outcome 规范化和资源字段解析。WorkBuddy 没有已证明的 AstronStudio thread 等价层级，CB-A 输出 `thread_id=null`；`conversationId` 映射 `session_id`，`requestId` 映射 `turn_id`。

本机 5.5.3 的 `CFBundleExecutable=Electron`，而公共 `WORKBUDDY_APP_PROFILE` 只接受 `WorkBuddy/CodeBuddy`。平台实现没有修改公共 profile，而是在 WorkBuddy 专属 driver 内只放行 `5.5.3 + Electron`；其他未核验 Electron 版本仍失败关闭。COMMON 需决定它是否应成为公共 profile 的正式变体，不能直接去掉版本门禁。

主请求 Token 只来自精确 request 的 `usage`。tool-result 内的关联 usage、缓存字段和 `credit` 单独保留，不并入主请求，避免重复计数或串 scope。`request_count=1` 表示唯一原生 request；底层传输重试不可见，所以 `request_attempt_count=null/unavailable`。未验证 `credit` 保持 `unverified`，不能当作已结算积分。

没有修改公共 Schema、run 入口、finalizer、指标公式、组件目录或构建器。旧 AstronStudio 和 Web WorkBuddy 行为不受影响；合入代码也不等于 WorkBuddy 真机执行、正式 collect 或生产发行通过。

## 已有证据与未验证范围

Git 可取得的脱敏证据：[workbuddy-macos-readonly-20260919](../../../../general-e2e/evidence/workbuddy-macos-readonly-20260919/README.md)及 `tests/general_e2e/fixtures/workbuddy/`。原始历史未入仓；本机 probe 报告位于 `/Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/probe-workbuddy-5.5.3-readonly.json`，SHA-256 `fb37a0969c9b3e200d82f18d3f9e116a15922317d85f693e21a8cde5a2d7b0c9`、大小 4109 bytes。

本机只读证据：WorkBuddy 5.5.3/x86_64 安装身份通过；主进程 0、CDP 未探测；会话索引 1 个 session；原生历史有 10 个 Workspace/10 个 conversation/4 个消息文件。历史样本按 Workspace key + conversation + request 精确绑定，轨迹 4/4 事件完整。主请求 Token 为 `34164/2087/36251`；关联 usage `181061/3774/184835`，缓存 `138496 + 42565 = 181061`；`credit=4.36/unverified`。该结果只证明字段可读和映射可实现，没有复用历史任务作为 General smoke。

验证命令和结果：

```text
python -m unittest discover -s tests/general_e2e -p test_run_general_e2e.py       # 14/14
python -m unittest discover -s tests/general_e2e -p test_shared_components.py     # 8/8
python -m unittest discover -s tests/general_e2e -p test_skill_layout.py           # 6/6
python -m unittest discover -s tests/general_e2e -p test_contracts.py              # 10/10
python -m unittest discover -s tests/general_e2e -p test_e2e_build.py              # 17/17
node --test tests/general_e2e/workbuddy_native_history.test.mjs \
  tests/general_e2e/workbuddy_probe.test.mjs \
  tests/general_e2e/workbuddy_state.test.mjs                                       # 9/9
node --test tests/general_e2e/*.test.mjs                                            # 69/69
node --check <四个新增 mjs>                                                        # PASS
git diff --check                                                                    # PASS
```

Python 使用主工程既有 `.venv`；worktree 未创建/安装新虚拟环境。测试覆盖应用版本门禁、绝对 Workspace 历史键、conversation/request/message 绑定、主请求与关联 usage 分离、缓存等式、null/coverage、tool outcome、CB-A null thread、公共 validator 和失败关闭。

额外的 Python 全量 discover 发现 127 项，结果为 1 个失败、4 个错误：冻结 dataset manifest 与当前任务源不一致，并缺少生成的 `general-custom60-v1.dataset.zip`。WorkBuddy 实现没有修改 dataset 源、锁文件或 report-workspace；该结果作为独立基线/生成物缺口保留，未被包装为全量回归通过，也未跨任务修复。

未验证：当前模型/权限/UI 控件、启动/CDP 归属、目录选择、一次发送、发送临界恢复、真机终态/追问/授权/超时/停止、纯回复和文件任务、正式 collect/评分/回传/报告、并发、仓库外发行。

## 接收方动作

| 接收任务 | 要求级别 | 下一动作/真实入口与配置 | 通过条件/验收 ID | 失败或缺依赖时 |
| --- | --- | --- | --- | --- |
| COMMON | REQUIRED_BEFORE_EXECUTION | 审查并集成 `2112a86450ba2f22fb284d37a20921cd7e65db69`；运行本交接列出的公共 55 项和 WorkBuddy 9 项测试；登记原始→集成 SHA | COMMON-IN01；测试全通过；专属 5.5.3 安装变体不被无证据放宽 | 不改写平台提交；记录具体失败文件/fixture，平台可继续不依赖公共修改的离线 UI Driver 工作 |
| COMMON | REQUIRED_BEFORE_CLAIM | CB-B 支持 workspace/conversation/request/message 多 artifact、会话索引绑定 provenance、WorkBuddy 原生身份映射和 macOS 进程清理 hook | COMMON-CB05、C13/C14/G04/G05；`session_id=conversationId`、`turn_id=requestId`、`thread_id=null`；哈希/size/cwd/ID 可交叉核验 | 保留私有 history observation，不生成正式 trace-index/collect receipt，不声明评分闭环 |
| COMMON | REQUIRED_BEFORE_CLAIM | 将 WorkBuddy execute/collect 专属源码和声明的 vendor 组件装配进 Skill/发行闭包；决定公共 profile 的 Electron 支持边界 | C15/C19/CV01/CV12；仓库外运行不依赖 Web Skill 或仓库 `eval_general_e2e` 路径；未知版本失败关闭 | 维持当前专属 5.5.3 变体，不私改公共 profile 或 v1 Schema |
| COMMON | INFORMATIONAL | 为本任务安排 WorkBuddy 桌面独占时段；不替代运行前 session/CDP/配置复核 | CV02/CV03/CV04/CV07；一个全新 canary 一次发送，同 attempt 恢复不重发 | 无时段时继续离线 UI locator/journal 测试，不启动或操作客户端 |

## 接续与风险

本任务下一项是在控制任务分配的独占时段完成一个全新 General canary：运行前只读 probe，保持用户当前模型/权限，回读 UI 配置，选择完整 Workspace，新建任务并只发送一次，捕获 conversation/request/cwd，按同 attempt 验证恢复。发送边界、原生 ID、未知交互或停止确认任一不明确时进入 `NEEDS_ATTENTION`，不重发、不冻结。

回退可直接停用 WorkBuddy adapter；未修改公共 wire 或旧 adapter。不得用当前源代码、fixture 或历史对账 PASS 代替真机或正式 collect，也不得把 5.5.3 的 `Electron` 变体放宽为所有版本。
