# General E2E 无头评分兼容修复验收

2026-11-27，在 44 服务器批次 11 / 评分作业 46 的三个异常题原件上完成离线回放。修复范围是评分框架和 General Skill 校验器；未重发题目、调用模型、修改原批次/评分记录或切换生产部署。模型 ID 配置错误导致的另外 39 个异常由模型管理修正，本页只记录三个兼容问题。

| 题目 | 原始异常 | 修复及实测 |
|---|---|---|
| `06_Safety_Alignment_task_007_bounded_cleanup` | `UNSUPPORTED_ARTIFACT_TYPE`，相对符号链接被默认清单拒绝 | 评分上下文清单接纳现有相对链接契约，摘要包含链接目标；越界目标仍拒绝。原件副本保留 3 个链接，规则评分完成，`verify-score=PASS`、`score_valid=true`，未启动模型 |
| `05_Creative_Synthesis_task_008_accessible_timeline_microsite` | `JUDGE_BROWSER_DIRECTORY_INVALID: /opt/scoring-browsers` | 无头 Worker 将可信镜像配置的浏览器别名解析为真实目录，再执行冻结 Skill 的完整预检。以原执行结果新建独立诊断评分尝试后，`offline-inline-html-observation/v1` 预检通过，候选输入未变 |
| `04_Search_Retrieval_task_010_node_statfs_release_trace` | `AGENTCUBE_TOOL_COVERAGE_MISMATCH` | 采集器独立回放 client `tool_search_call` / `tool_search_output`，以及同轮相邻的解析错误。原件用旧校验器仍失败，用修复版通过，核验 52 次普通调用 + 1 次搜索调用，共 53 次；新材料交接与原冻结 Score Skill 的规则/语义准备均通过，停在 `READY_FOR_JUDGE`，未调用裁判 |

## 代码与版本

- `src/e2e/headless.py`：仅评分上下文的创建、恢复及完成重读清单允许相对符号链接，沿用链接类型、目标和摘要验证；Skill 目录仍禁止符号链接。无链接上下文的摘要格式不变。
- `src/e2e/headless_worker.py`：浏览器配置在调用冻结编排器前解析成真实目录，不放宽 `_regular_directory()` 对候选、Skill 和证据路径的约束。
- `tools/report/e2e-shared/general-resource-supplements/agentcube-native-binding.mjs`：补齐搜索调用/目录结果的独立核验、调用 ID 唯一性和参数/结果一致性；空调用 ID 只允许绑定同一 turn 中紧邻搜索调用的明确解析错误。原生轨迹字节保持不变，不靠删事件或减少数量通过。
- 上述共享代码同步到 collect、score、report 三个 Skill 的 vendor 副本。共享组件升级为 `general-resource-supplements 1.3.22`；Skill 版本分别为 `collect-general-e2e 0.12.40`、`score-general-e2e 0.29.9`、`report-general-e2e 0.10.8`，旧格式轨迹继续通过回归。
- 新镜像配方直接使用 `/opt/scoring-runtime/playwright-browsers`，离线镜像验收增加真实目录校验，防止“浏览器能启动但冻结 Skill 拒绝目录别名”的验收遗漏。默认新标签为 `wildclawbench-e2e-scorer:codex-0.171.0-office-v2`，保留旧标签；本次未构建或发布 v2 镜像。

## 原镜像与旧批次兼容

所有服务器离线回放均使用原绑定镜像：

`sha256:62c60be80a30093c10f2b770a1db1a141d0c2d9d2406df5ba6b3e17182ea5f5d`

诊断容器无网络、无模型凭据，使用独立输出目录。原输入与 Skills 以只读挂载提供。目录清理题和微站题在诊断后分别比较源材料与副本，context 和 Skills 的清单摘要一致；评分 #46 仍为 18 个有效、42 个异常。所有诊断容器均已自动释放。诊断评分结果没有导入平台或参与业务报告。

Node statfs 题额外验证了实际交接路径：将修复版独立采集器作为补充校验器，对同一原始执行导出新的评分上下文，保留原批次绑定；交接 `verification.status=PASS`，随后沿用冻结的 `score-general-e2e 0.29.8` 完成规则和语义准备。这里没有要求重建题目工作区或重跑 Harness，也未隐式替换旧评分尝试的 Skill。

发布时需要让新评分任务绑定修复后的框架读取器；已有评分记录继续使用其冻结配置和发行，不会自动升级。当前案例已实测可继续使用原评分镜像，新镜像 v2 是后续构建的独立版本。编辑原模型记录并保存后，新建评分任务会冻结修改后的模型配置，无需另建模型记录。

## 校验范围与复现

61 项针对性测试通过：35 项无头评分、路由、轨迹与镜像构建测试，10 项共享组件、并发与原生资源补充测试，16 项 Node 独立校验测试。新增反例覆盖链接目标漂移/越界、失效浏览器别名、搜索目录篡改/重复、缺失工具事件，以及空 ID 跨事件/跨 turn 冒认。三个新 Skill ZIP 均通过依赖闭包与内容摘要验证，Skill 元数据校验通过。

```bash
.venv/bin/python -m unittest tests.e2e.test_headless tests.e2e.test_headless_skill_routing tests.e2e.test_trace tests.general_e2e.test_headless_scorer_build
.venv/bin/python -m unittest tests.general_e2e.test_shared_components tests.e2e.test_headless_concurrency tests.e2e.test_agentcube_resource_supplement
node --test tests/general_e2e/agentcube_native_verification.test.mjs
```

原件回放材料位于独立诊断工作区 `server44-compat-fixes-20261127-155211`：`source-receipt.json` 绑定三题及执行身份，`native_old-result.json` / `native_fixed-result.json` 对照旧/新校验器，`browser-result.json`、`links-result.json`、`fresh-native-context-result.json`、`native-preparation-result.json` 和 `original-preservation-result.json` 保存各步回执。`compat-validation-summary.json` 汇总状态及回执摘要。本页不将模型尚未参与的语义准备记作已完成语义评分，也不宣称 60 题已重新验收。
