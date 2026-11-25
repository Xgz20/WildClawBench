# 远程 General 桌面评分运行时排查

## 原始失败

- 环境：`172.31.101.44:9619`，框架发行 `cc11cff84b8ee9411ed6c5bd51c688a39a19c900`。
- 批次：`platform-e2e-254193a3226a4b39aff280589db1a61e`，平台批次 #1、评分 #1。
- 用例：`01_Productivity_Flow_task_001_expense_policy_check`。
- 原执行：`exec-486de2fb47cb438f94d0bbd5147fd142`，执行已完成。
- 原评分：`desk-6b48dd2c10c7f11cc29e8b8d`，`RUNTIME_PYTHON_MISMATCH`，
  `agent_used=false`，评分沙箱已释放。
- 模板绑定：`agentcube-windows/winarena-pc-20261125-a`，WAA `4adaa72571149964ac0d8e44dcfab3228b79a14a`。

Linux 控制端实际为 Python 3.11.9 虚拟环境；同模板 Windows 探针实际为 Python 3.12.10
系统环境，没有 Python 3.11 或 uv。桌面适配器把系统解释器传入规则 Worker，而冻结
评分锁要求 Python 3.11 虚拟环境，因此在派发评分 Agent 前失败。

## 修复与回归

桌面适配器自动准备并校验锁定运行时，以后台进程和原子回执交接，避免同步 Windows
命令接口约 120 秒的时限。读取超时后续查同一启动标记，不重复启动。使用冻结契约的
依赖审计选择是否安装 Chromium；文本规则不依赖浏览器下载。自动规则结束后调用
原 Skill 的 `prepare-semantics`，生成 `not-required` 审计，再 finalize 和 verify-score。
没有修改冻结 Skill、题目、计分公式或候选原件。

30 项针对性测试通过，覆盖依赖范围、摘要损坏、环境复用校验、短请求轮询、启动回执
不明、取消及失败日志归档。使用原执行结果新建独立 Linux 规则尝试，正确完成规则、
无需语义裁判审计、合分及 `verify-score`，`score_valid=true`。

该独立尝试得到 0 分：候选 `reimbursement.json` 以 `EF BB BF` 开头，冻结规则按
`utf-8` 读取后交给 JSON 解析器，因 BOM 进入零分返回分支；使用 `utf-8-sig` 只读解码
可以解析出六条费用。此处只定位格式兼容性，没有修改候选、变更规则或评定其它业务
检查点，也没有把诊断分数回写平台。正式重评前需要单独明确这一兼容口径。

## Windows 探针状态

| 会话 | 结果 |
| --- | --- |
| `b771bf18-2e0d-49d3-a411-619cd5da71c7` | 解释器与工具链探针完成，已确认释放 |
| `2e28d124-0fbf-4762-870a-5c5a72c15e15` | 官方源冷下载停滞，诊断中止，已确认释放 |
| `3be7fcbe-dfd7-4e88-bf97-77071730bef7` | Python 创建后原依赖源较慢，诊断中止，已确认释放 |
| `185e4e27-d6a0-4834-aee2-d6b676a90b94` | 同步命令时限探针，已确认释放 |
| `f086f523-496a-46df-a9ee-8931e17353c8` | 启动请求读取超时，已确认释放 |
| `48661e1d-e27a-42b9-b25b-0cb6c2b4add8` | 后台运行、Python 3.11 和依赖已准备；Chromium 下载未完成，诊断取消并确认释放 |
| 最终按契约准备的探针 | 创建请求 900 秒超时，未返回会话 ID；尚未运行评分，资源创建结果待控制台核对 |

证据保存在服务器 `<WCB_E2E_OUTPUT_ROOT>/diagnostics/20261125-desktop-runtime*`。
最终版本的 Windows 冷启动、规则评分和 Linux 回传校验仍待验收，不能将上述单项结果
表述为完整 Windows 桌面评分验收通过。远程业务服务尚未部署本修复，原评分记录保留。

## 后续 BOM 修复

用户确认修复编码问题后，已在 `score-general-e2e 0.29.5` 登记精确、版本化的 BOM
读取兼容，新尝试冻结修复 Profile；本页记录的原产物与诊断零分保留。
实现及范围见 [JSON BOM 兼容说明](../guides/general-json-bom.md)。
后续实机验收由用户手动执行，本轮不再创建沙箱或运行平台评测。
