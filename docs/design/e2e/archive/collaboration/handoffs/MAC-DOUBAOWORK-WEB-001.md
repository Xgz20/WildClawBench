# MAC-DOUBAOWORK-WEB-001：DoubaoWork Web 公共接入需求

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 创建时间 | MAC-DOUBAOWORK-WEB-001 / 2026-09-19 17:23 +08:00 |
| 来源任务 / 唯一负责人 | MAC-DOUBAOWORK-WEB / 独立 Codex 开发任务 |
| 目标任务 | COMMON |
| 基线 / 实现 SHA / 必需依赖 | 固定 `SYNC_SHA=0dd42824cb8eb510ab126fd74553f93312c9f201`；COMMON 推荐源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a`；P1 `f168f2e4c7e5e447249cfb7e96b0d195b99e3e60`；P2 `d183e28f2224aed40fd14ae43d8f7ab9ce6cbb0b` |
| 集成分支 / 集成状态与 SHA | 公共基线已在本任务 merge `6cd5aac76055503380af6380cd203196515de642`；本任务实现 LOCAL_ONLY，未 push、未集成 |
| 修改范围 | `tools/report/skills/web-e2e/execute-web-e2e/drivers/doubaowork/` 与 `docs/design/web-e2e/evidence/doubaowork-macos-web-e2e/` |
| 关联任务与验收 ID | COMMON-CB05（CB-B）；MAC-DOUBAOWORK-WEB P2/P3/P5/P6；Web C/W、CV/WV |

## 变化与兼容性

DoubaoWork 2.28.12 / macOS x86_64 的客户端专属适配现已具备只读应用/CDP probe、显式原生 session/trajectory 旁路解析、目录选择 helper、脱敏 fixtures，以及不触碰客户端的发送 journal/恢复决策。P2 journal 在 `READY_TO_SEND` 保存 Prompt SHA，在任何 UI click 前原子登记唯一 dispatch attempt；恢复时只有发送前 UI conversation 与原生 session 目录两组基线各自恰好出现一个新 ID 且相等，才允许 tentative binding。原生不存在的 turn/cwd 保持 null，未知发送状态禁止自动重发。

本实现继续使用 `wildclawbench.web-e2e-automation-state/v1` 名称作为客户端控制 journal，但不生成正式 `execution_record.json` 或 execution receipt。COMMON-001 的 General Schema 对 DoubaoWork Web 不适用；接收方不能创建 General adapter 或把本私有状态当成 Web 正式证明。旧 smoke、P1 只读实测和 P2 fixture 均不因本次实现升级为生产证据。

COMMON 的 Web CB-B 需要吸收以下公共契约，平台分支不自行修改 canonical/vendor：

1. 在 `tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/{capture,collect,parsers}.mjs` 注册 DoubaoWork，保留 Token/request/duration 的 null、工具调用 known subtotal 与 `coverage.denominator=null`；未绑定的 agent/browser 日志不得混入。
2. Web finalizer/automation state 接收 `conversation_id`、`session_directory_id`，并允许原生不存在的 `turn_id/native_cwd=null`；tooltip 路径、Prompt SHA、单次发送、session 证据、可信终态和清理未共同满足时不得生成 `integrity.valid=true`。
3. trace/provenance 支持同一 attempt 的多 artifact：规范化 transcript、UI 最终回复、原生 trajectory source index；分别记录相对路径、SHA-256、大小、来源与 completeness。
4. 进程清理 hook 首先允许 DoubaoWork `supported=false`，并阻断正式完整收口；不得按 DoubaoWork、Node 或浏览器进程名宽泛终止。
5. 在 canonical `tools/report/e2e-shared/desktop-app-discovery/profiles.mjs`、`tools/report/e2e-shared/components.json` 和确定性构建/vendor 装配中新增 DoubaoWork macOS app、Bundle ID 与 CDP 端点 Profile，禁止手改 vendored 副本。
6. `tools/report/skills/web-e2e/prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py`、execute 入口、run-web-e2e macOS application 路由与发行清单纳入 `harness=doubaowork`；初始固定 `ui_slots=1/run_slots=1`，在单题、串行、隔离和恢复真机验证前不继承其他 Harness 的三槽声明。

## 已有证据与未验证范围

P1 只读实测确认 `/Applications/DoubaoWork.app` 2.28.12、Bundle ID `com.work.pc.doubao`、loopback CDP `127.0.0.1:9260`、Chrome 147 / Protocol 1.3 与唯一 chat page。仓库外原件：`/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/p1-readonly-20260919-v2/probe.json`，SHA-256 `ae37247eff8b9ee022ee4d7424857aafe33cb157d0ad54d193d7dc9440ed635c`；旁路 native evidence SHA-256 `bb37bb9fb5913303c11a6d5d6e99dff73a102d289eab439f54e6c10fd188b483`。原始 trajectory 留在本机受限目录，不进入 Git 或发行包。

P2 revision 上的 focused checks：DoubaoWork Node 23/23；`state.mjs`、`lib.mjs`、`platform.mjs`、`native-evidence.mjs`、`probe.mjs` 均通过 `node --check`；`swiftc -typecheck select-folder.swift` 和 `git diff --check` 通过。P2 没有启动/重启客户端、选择目录、切换模型/权限或发送 Prompt；因此没有真机发送、恢复、可信终态、进程清理、正式 collect、评分、报告或脱仓发行证据。

## 接收方动作

| 接收任务 | 要求级别 | 下一动作/真实入口与配置 | 通过条件/验收 ID | 失败或缺依赖时 |
| --- | --- | --- | --- | --- |
| COMMON | REQUIRED_BEFORE_CLAIM | 在 Web metrics canonical 中注册 DoubaoWork adapter，使用显式 conversation/session 绑定的 trajectory；覆盖 null、known subtotal、unknown denominator | parser/collector fixtures 证明缺失值不写零、partial 不升级为完整总量 | 保留 P1 adapter 私有输出，禁止回填正式资源指标 |
| COMMON | REQUIRED_BEFORE_CLAIM | 在 Web CB-B finalizer 与 trace/provenance 中实现 nullable native identity 和多 artifact 来源 | 缺 turn/cwd 可校验但不伪造；没有可信终态或清理时不能完整收口 | 平台任务继续停在 `NEEDS_ATTENTION/unverified`，不分叉公共 Schema |
| COMMON | REQUIRED_BEFORE_CLAIM | 为 DoubaoWork 接入清理 hook、canonical discovery Profile、components/build/vendor 装配与 prepare/run/发行路由；默认 1/1 槽 | layout/build/脱仓测试通过；发行身份可追溯；公共路由不把 General adapter 当 Web Driver | 保留 LOCAL_ONLY；不得声明正式执行或发行可用 |
| COMMON | INFORMATIONAL | 分配单一独占桌面时段，范围限一个全新 L1；保持当前非空模型和当前权限 | 客户端专属 P2 观察材料返回 COMMON，未知状态失败关闭 | 未分配时继续离线开发，不启动或改变 DoubaoWork |

COMMON 在自己的任务卡记录 SEEN、ADOPTED、VERIFIED 或 BLOCKED；本任务不代填公共实现与验证结果。

## 接续与风险

独占桌面时段获配后，本任务仅验证“本地电脑→新建项目”、目录 tooltip 完整路径、保持并回读模型/权限、一次发送和新 session 捕获。当前没有可信 native 终态/cwd/进程清理，首次时段目标是采样与失败关闭，不承诺正式 execution receipt。发送临界区、conversation/session 候选或终态任一不明确时进入 `NEEDS_ATTENTION`，不重发、不代答。旧批次不存在；代码未 push、未合主分支。
