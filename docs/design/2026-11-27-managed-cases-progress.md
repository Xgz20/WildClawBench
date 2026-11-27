# 个人用例管理实施状态（持续更新，不代表完成）

用户已批准完整方案，要求在独立 worktree 实现，不默认合并、推送、部署或派发付费评测。
两仓 worktree `.agents/user-case-management-20261127`，分支 `feat/user-case-management`。
平台起点 `1e965a48`，框架起点 `a2217ad3`。

已落地：
- 框架 `src/managed_cases/contracts.py`：静态解析/编辑保留扩展字段、素材路径验证、评分模板变量白名单、声明式规则。
- `bundle.py`：SHA 校验外部 ZIP，源码外构建最小任务素材树，复用标准冻结 General bundle。
- CLI/E2E 外部来源入口、CLI managed task parser、规则容器执行器与统一评分上下文初版。
- 平台文档/不可变修订/素材/快照/导入表和迁移 `f27a1c9e503b`，MySQL + 私有 MinIO。
- CRUD/删除恢复/发布下架/包导入导出/复制/校验接口、共享选题目录接入。
- 请求级 ORM 私有来源过滤、任务与批次继承、部分报告继承。
- 前端系统/我的/租户/设置入口，完整编辑页、素材、评分、历史、导入预览、快照及调试入口。

检查：框架 managed tests 6 项通过；case reruns 10 项通过。
平台首轮 managed tests 4 项通过；既有相关后端 62 项通过；前端构建通过。
测试启动器 `/private/tmp/wcb-user-case-tests-20261127.py` 指向本 worktree，独立库
`astronclaw_eval_user_cases_20261127_test`。它配置框架环境仍指向框架主目录，
新增测试 fixture authoring 会自行切换到 managed worktree。
依赖：平台 worktree .venv/node_modules 链接原平台安装目录，框架可用
`/private/tmp/wcb-merge-framework-20261127/bin/python`（yaml/requests/openpyxl/dotenv）。

必须继续完成及核验（不可仅凭当前状态宣称完成）：
- 评分新模板选择 UI 与 API/E2E transport 接线，冻结模板/重评版本、历史模板注入。
- E2E managed scoring 与 headless/desktop CLI handler 已接初版 score_batch，必须写实际合成测试。
- API 对二进制证据目前明确拒绝，需要实现可验证渲染/提取，不能静默丢证据。
- Web/PPT currently 内部映射 General，必须补实际契约取证兼容与能力门禁，不能冒称旧 Web Skill。
- 系统用例复制及同协议跨来源组合尚缺；不得通过普通导出扩大系统 GT 权限。
- 未引用附件 GC/回收站清理缺实现；完整文档和限制设置待补。
- 任务/结果/报告/导出的私有性需要扩展真实 API 租户/用户回归（当前仅 tasks list 最小检查）。
- 外部来源预检与 actual snapshot 稳定、运行时图、GT 不进执行容器、缓存损坏与并发需更多测试。
- 前端目前只有静态 build；需 ESLint、组件测试、独立假元数据/真实存储服务页面验收，未启动正式本地开发后端。
- 自定义脚本只有新 managed-score 路径隔离，旧冻结用例评分不执行用户脚本覆盖。

临时当前代码注意：平台 ScoringSettings 已新增 transport/judge_template_revision_id，API profile 初版。
credential() 尚要按 API 的实际协议（非 Codex-only）核验；runtime_config 对 rule_image_id 返回冻结完整非密钥字段。
框架 API transport 可调用 Chat/Responses/Anthropic，但当前二进制明确异常。
`score_batch()` 生成显式 `managed-e2e-score/v1`，不能冒称已完成原 Skill verify-score；需来源独立复验和报告适配回归。
