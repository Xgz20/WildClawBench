# 个人用例管理合入验证

集成 worktree 为 `.agents/user-case-management-integration-20261128`，分支为 `feat/user-case-management-integration`。框架工作分支基线 `9ff66259`，个人用例功能分支 `2c355fab`。平台工作分支基线 `9ecfda9`，个人用例功能分支 `0c55d40`。

## 兼容修复

合并框架 `src/cli_scoring.py` 时同时保留评分运行副本、只读原件、容器所有权记录、释放确认和模型端点 DNS 映射。CLI 裁判运行目录同时包含冻结评分请求、个人用例上下文及媒体证据，相关文件以只读挂载提供。个人用例检查脚本继续在独立无凭据容器执行，模型评分进程只读候选与规则结果。

个人用例的 CLI 评分清单、候选复制、证据和验分使用已有的工作区链接校验。真实相对链接保留类型和目标，链接越出工作区或改成普通文件时拒绝评分/验分。仅含普通文件的旧清单继续使用相同字段和摘要规则。E2E 评分副本也使用同一套链接复制与校验。

## 真实 CLI 验收

通过公开 `eval/run_batch.py --case-source` 入口执行一条合成个人用例。DSH CLI 0.1.2-rc.1 / DeepSeek-V4.1-Flash 读取 `[2,3,5]`，写出 `results/answer.json` 的 `total=10`，并创建 `results/latest.json -> answer.json`。

原生执行为 `finished/exit_code=0`。评分封存保留真实链接及私有 GT，执行备份中没有 GT。随后通过 `eval/run_cli_score.py` 调用独立 DSH CLI 裁判，实际运行目录为 `/job/runtime`，评分为 1.0，`verify_score` 为 PASS。模板标识 `MERGE_LINK_ACCEPTANCE_20261128` 出现在冻结上下文和实际投递 Prompt 中，原件清单与字节保持一致，规则和裁判容器释放均已确认。

摘要回执见同目录 `2026-11-28-managed-case-merge.json`。完整本地执行、封存、原生轨迹和评分材料保存在 `~/EvalDebugWorkspace/e2e-platform/control/user-case-merge-20261128/native-link-accepted/`。

## 回归结果

- 框架单元/CLI/报告检查 43 项通过，端到端适配与桌面评分回归 51 项通过，真实 Docker 隔离检查 2 项通过。
- 另有 4 项按显式环境开关跳过，包括未指定的历史调查包回放。
- 平台合并代码在独立 `_test` MySQL 数据库运行 138 项后端测试通过，覆盖个人用例、任务、重评分、统一报告和 OpenAPI。
- 平台前端 12 项定向测试及生产构建通过。构建仍报告既有的大包与动态导入提示。
