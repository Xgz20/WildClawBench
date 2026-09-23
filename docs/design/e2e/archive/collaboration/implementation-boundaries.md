# 首轮并行实施边界

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

本轮由 COMMON 提供公共入口与协议，平台任务实现原生适配。代码开发和离线测试可以并行；同一 macOS 桌面的目录选择、配置切换、Prompt 发送、重启和真机 smoke 必须由控制任务安排独占时段。

## 公共能力分两批接入

| 批次 | 交付 | 平台可以推进什么 | 尚不能声明什么 |
| --- | --- | --- | --- |
| CB-A：开发接口 | adapter 组件绑定校验、通用 execution-state Schema、旧 AstronStudio 状态兼容、run 状态接收与真实身份/证据校验 | 平台 probe、一次发送/恢复、原生日志解析、规范化输出与 fixtures；使用通过校验的状态登记 execute 阶段 | 不因新状态被接收就宣称正式 collect、评分或完整 E2E 已通过 |
| CB-B：正式收口 | 公共 finalizer、原始 trace 多 artifact、原生会话身份映射、可信资源来源集合、平台进程清理 hook、发行闭包 | 对接正式 collect receipt，随后验证完整评分/回传/报告 | 未验收的 OS/架构/版本和恢复能力不继承其他平台结论 |

CB-A 已随 COMMON-001 发布，CB-B 第一批通用机制随 [COMMON-002](handoffs/COMMON-002.md) 发布。平台按正式接口实现原生 collector 和可信 cleanup hook，不能复制整套 AstronStudio finalizer 或降低校验绕过依赖。未能表达的真实样本和接口缺项交 COMMON 处理。三个平台开发 Driver 已在 [COMMON-003](handoffs/COMMON-003.md) 集成；正式平台 collector 和 Web 公共路由仍按下表归属单独交付。额外五项指标的统一扩展另属 COMMON-CM01，不阻塞现有 11 项资源指标、原始数据和适配开发。

原生字段调研可从 [Web/General 指标盘点与 Harness 可行性分析](../跨场景指标盘点-20260923.md)开始；该文附历史来源哈希，平台任务仍需核对本机实际版本和数据，不能继承历史样本的覆盖状态。

DoubaoWork 下一批采用[Web 等价证据与最小公共接入方案](doubaowork-web-integration.md)。缺少原生 cwd/terminal 保持未知，以归档的 UI/project/workspace/Prompt 与真实 cleanup 证据链验收，不将不存在的字段设为永久前置条件。

当前必须明确的边界：

- 新 Harness 不伪造 AstronStudio 的 thread/turn/session/lifecycle 字段；缺少的原生 ID 明确为空，另用可回溯且哈希绑定的原始证据证明会话与完整 Workspace 的对应。
- 旧 trace-index v1 保留 AstronStudio 兼容边界；新 General 使用 trace-index v2，缺失原生字段可为 null，多个 raw/binding 文件必须有哈希与身份对账。正式 collect 仍需平台真实采集、停止与清理验收。
- 原生轨迹和 usage 解析留在各 Harness adapter；公共层只负责已约定的输出校验、可信来源、冻结与交接，不把 AstronStudio SQL/事件名变成通用 API。
- 新增积分、工具结局和任务异常的原始字段可保存为 adapter 证据；严格 resource-metrics v1 仍按现有 Schema 输出，缺失用 null/coverage，不私增公共指标字段。
- 发行代码只 import 本 Skill 内实现及声明的 vendor 组件，不能依赖另一 Skill 或仓库中的 `eval_general_e2e` 路径恰好存在；构建器负责装配。

## 文件归属

| 任务 | 专属实现与文档范围 | 公共修改通过谁协调 |
| --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | General execute/collect 下 `drivers/workbuddy/`，`eval_general_e2e/adapters/workbuddy/`，WorkBuddy 专属 tests/fixtures、验收记录和本任务卡 | COMMON |
| MAC-QWENWORK-GENERAL | General execute/collect 下 `drivers/qwenwork/`，`eval_general_e2e/adapters/qwenwork/`，QwenWork 专属 tests/fixtures、验收记录和本任务卡 | COMMON |
| MAC-DOUBAOWORK-WEB | Web execute 下 `drivers/doubaowork/`，DoubaoWork 专属 tests/fixtures、验收记录和本任务卡 | COMMON；现有 WorkBuddy batch 被 QwenWork 复用，不由本任务独占 |
| WIN-ASTRONSTUDIO-GENERAL | Windows 原生 launcher/probe/执行入口、Windows 平台 helper/进程清理 hook、Windows tests/fixtures、G5/WIN 记录和本任务卡 | COMMON；不改 macOS 默认行为或公共 Schema 以迁就平台差异 |
| COMMON | adapters/components.py、通用 Schema/状态接收、公共 finalizer、共享组件/指标/构建装配、基线和派发记录 | 本控制任务统一协调，代码先在专属 worktree 实现 |

文档/新目录是归属边界，不是已经实现的入口。专属任务若需要更改清单外文件，先在任务卡列出具体原因和影响；可继续独立工作，不自行跨边界改公共语义。平台细项验收优先建立专属证据记录，集中验收清单的公共顶部总结由 COMMON 合入时更新。

## 桌面与运行现场

初次派发只允许离线开发、fixtures 与不改变应用状态的只读盘点。需要真机发送或重启时，在任务卡写明客户端、任务范围、预计操作、原生活动会话检查与恢复方案，再报告准备就绪；控制任务分配独占时段后执行。任何任务都不能为了 probe 顺便重启客户端、切换项目或发送 Prompt。

这是一条运行调度约束，不是新的用户批准流程：用户已授权的常规操作由控制任务协调放行，无需反复向用户确认。现有工作树内锁尚不能证明跨 worktree 的桌面隔离，台账也不充当实时锁。初始阶段未分配桌面时段，各任务仍应完成所有独立实现、解析与测试，不能只写“等待”。

## 本机工作目录绑定

Git worktree 必须位于主项目 `.agents/` 内，分支为 `feat/<描述>`。若任务创建接口只能选已保存工程而不能绑定这个自定义路径，新任务可归属同一项目，但**所有文件/命令的实际工作目录必须显式为被分配的 worktree**，不得在工程根目录编辑或使用默认 cwd。每个任务首条检查确认实际根目录、分支和 base，并记录到任务卡；创建工作树和任务本身不代表绑定已核验。
