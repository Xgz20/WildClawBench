# COMMON-001：首轮开发基线与平台接入

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 时间 | COMMON-001 / 2026-09-19 16:47 +08:00 |
| 来源 / 负责人 | COMMON，本 macOS 控制任务 |
| 目标任务 | MAC-WORKBUDDY-GENERAL、MAC-QWENWORK-GENERAL、MAC-DOUBAOWORK-WEB、WIN-ASTRONSTUDIO-GENERAL |
| 必需源码 | `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a` |
| 实现与集成映射 | `abce5da832f16b48cd402ceef04a6abda544a379` 原提交保留在上述 merge 历史中 |
| 发布 | 推荐源码已 push 至 GitHub `feature/astroncode-eval` 并核验远端 SHA；本交接随后续台账提交发布 |
| 关联项 | COMMON-CB02/03/04；Mac P1/P2；Windows G5-01、WIN-01/02；C01/C03/C08/C14/C19、CV01/02/04 |

## 变化与兼容性

新增 [通用执行状态接口](../../../../../../tools/report/skills/general-e2e/run-general-e2e/references/adapter-execution-state.md)。canonical 为 `eval_general_e2e/contracts/execution_state.py` 与 `schemas/general-execution-state-v1.schema.json`；新 General adapter 输出 `wildclawbench.general-e2e-execution-state/v1`。run 的 record-execution 校验业务身份、完整 Workspace、Prompt SHA、原生绑定证据、单次发送与可信终态。不能确认发送/停止时保留待核对；不存在的 native ID 用 null，不伪造 AstronStudio 层级。

旧状态仅兼容 AstronStudio macOS；新 Windows 实现使用通用状态。组件检查支持 `inspect_shared_component_layout(root, adapter="workbuddy")` 等显式 binding，默认仍严格校验 AstronStudio。公共入口由 COMMON 维护，平台自行维护其 adapter 子目录。

版本为 `run-general-e2e@0.4.0`、`general-contracts@1.1.0`。构建器从 canonical 装配，禁止手改 vendor 或跨 Skill import。新发行必须重建并记录新源码/content/ZIP/组件身份；本次没有新生产包，不中断既有批次换 Skill，先按原 attempt/版本收口。

CB-A 支持开发接入；**正式 collect 依赖 COMMON-CB05（CB-B）**：公共 finalizer、多原始 trace、原生身份映射、可信 provenance、平台进程清理与发行闭包。新 General adapter 不复制 AstronStudio finalizer。DoubaoWork 采用 Web 协议，不能用 General 状态冒充 Web 执行证明。

trace-index/resource-metrics wire 未改；新增五项指标仍属 COMMON-CM01。客户端先保留原始字段和对账 fixture，不向严格 v1 添加私有字段；缺失为 null、known subtotal、coverage。

## 验证与证据边界

在集成源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a`，使用主工程已有 `.venv/bin/python` 运行五组：run 14、shared 8、layout 6、contracts 10、build 17，合计 **55 tests，退出码 0**，未安装新依赖。

复现时在自己的开发 worktree 运行，python 替换为核验后的解释器：

```text
python -m unittest discover -s tests/general_e2e -p test_run_general_e2e.py
python -m unittest discover -s tests/general_e2e -p test_shared_components.py
python -m unittest discover -s tests/general_e2e -p test_skill_layout.py
python -m unittest discover -s tests/general_e2e -p test_contracts.py
python -m unittest discover -s tests/general_e2e -p test_e2e_build.py
```

fixture 覆盖 WorkBuddy/QwenWork macOS、AstronStudio Windows 声明字段，以及错配、发送不确定、路径/证据/hash、停止未确认和状态快照 hash。Windows 字段 fixture 不证明 Windows OS 运行。脱仓测试从 ZIP 提取后以 python -I/空 PATH 登记 Qwen fixture，核对包内 Schema/校验器字节及版本；测试 revision 不作为生产发行身份。

原 [macOS smoke](../../../../general-e2e/evidence/macos-current-smoke-20260919/README.md)沿用其源码 `457e355...` 和声明范围，不能扩大为新接口、新 Harness、Windows 或未知恢复场景的真机证明。源码、脱敏 tests、证据索引随 Git 获取；完整轨迹/产物留在本机。

## 接收动作

先检查活动现场和未提交内容，核对同步仓库，fetch 集成分支并固定完整 SYNC_SHA。确认它包含推荐源码和本交接：

```text
git merge-base --is-ancestor ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a <SYNC_SHA>
git show <SYNC_SHA>:docs/design/e2e/archive/collaboration/handoffs/COMMON-001.md
```

新 worktree 从 SYNC_SHA 创建；已有 worktree 在独立改动提交、无活动批次后 merge，保留本任务卡现有内容。不只 checkout 较早源码而漏掉交接。接收方自行记录 SEEN、ADOPTED、相关验证的 VERIFIED，分别保存推荐源码/SYNC_SHA/实际 HEAD。

| 接收任务 | 要求级别 | 有序下一步 | 通过条件 / 缺口 |
| --- | --- | --- | --- |
| MAC-WORKBUDDY-GENERAL | REQUIRED_BEFORE_EXECUTION | 采用基线；读接口；做原生绑定/日志映射与 fixture；按真实 ID 输出状态 | 状态/布局测试通过后实现客户端；正式 collect 缺口交 CB-B |
| MAC-QWENWORK-GENERAL | REQUIRED_BEFORE_EXECUTION | 采用基线；核对本机 runtime/token profile 和 session/cwd；实现执行/恢复与 fixture | 不继承历史同号版本 profile；正式收口依赖单列 |
| MAC-DOUBAOWORK-WEB | REQUIRED_BEFORE_EXECUTION | 采用契约/边界；保留旧 probe；实现本地电脑→新建项目的 Web Driver 和 fixtures | 按 Web 协议验收；General Schema 影响审阅后可记不适用 |
| WIN-ASTRONSTUDIO-GENERAL | REQUIRED_BEFORE_EXECUTION | 核验本机 remote/运行器；创建指定 worktree；按启动包先跑基线检查和 G5-01 只读盘点，再实现平台层 | 回写三个 SHA、命令结果、安装/CDP/原生日志；环境缺口与回归分开 |
| 全部四项 | REQUIRED_BEFORE_CLAIM | 目标平台闭环、恢复/并发/发行验收；新 General 正式 collect 等 CB-B | 没有真机证据不得提升声明；不等待五项新增指标全部实现 |

Windows 首次基线检查：

```powershell
python -m eval_general_e2e skills --json
python -m eval_general_e2e check-layout
python -m unittest discover -s tests/general_e2e -p test_run_general_e2e.py
python -m unittest discover -s tests/general_e2e -p test_shared_components.py
node --test tests/general_e2e/desktop_app_discovery.test.mjs
```

Python/Node 实际路径和依赖按本机/锁文件核验。Windows launcher 尚待实现，不提供虚构执行命令。详细清单及 Prompt 见 [Windows 启动包](../../general/AstronStudio-Windows后续实施清单.md)。Windows→Mac 评分需实际接收方；未安排时先完成本机链路，不能自导入冒充跨机。

## 接续与现场

三个 Mac 任务已启动，见[派发记录](../dispatch.md)。目前仅独立开发与只读盘点，尚无桌面时段；操作客户端前将应用/任务范围、活动会话检查和恢复方案交 COMMON 排期，不向用户重复索要已有授权。

COMMON 下一项为结合平台原生样本/需求实施 CB-B，再推进新增指标与 AstronStudio 对账。公共缺口不阻塞客户端独立工作，也不允许私自分叉协议。旧源码参考 `03c38f2`；新状态不能交给旧 run，保留所有版本和原件，不覆盖降级。
