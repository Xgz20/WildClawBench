# COMMON-002：通用采集接口与共享发现组件

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 时间 | COMMON-002 / 2026-09-19 19:30 +08:00 |
| 来源 / 目标 | COMMON → MAC-WORKBUDDY-GENERAL、MAC-QWENWORK-GENERAL、MAC-DOUBAOWORK-WEB、WIN-ASTRONSTUDIO-GENERAL |
| 必需源码 | `eb23784a7ed25b0f0364db0392783de277b22b96` |
| 前序基线 / 依赖 | `0dd42824cb8eb510ab126fd74553f93312c9f201`；仍须接收 COMMON-001 |
| 实现映射 | CB-B `eb23784`、Doubao discovery `de8b23d`、Web 版本 `5b03659`，原提交均保留 |
| 同步目标 | GitHub `feature/astroncode-eval`；取得包含本文的完整 SYNC_SHA 后采用 |
| 关联项 | COMMON-CB05；C08/C14/C19、CV02/CV04；平台 P2/P3、Windows G5/WIN |

## 接口与版本

[通用正式收口接口](../../../../../../tools/report/skills/general-e2e/collect-general-e2e/references/general-finalization.md)给出可直接接入的 API、文件布局、来源对账和平台 hook 要求。

- CB-A execution-state v1 保留；新增独立 trace-index v2，多个 `raw/...` 和 `bindings/...` artifact、nullable 原生 ID、严格 cwd/身份与来源哈希匹配。旧 trace-index v1 不放宽。
- `finalizeGeneralExecution(options, { processCleanup })` 使用唯一 `lib/general-finalizer.mjs`；旧 AstronStudio 入口为兼容 wrapper。平台实现真实 cleanup hook；缺少 hook、unsupported、残留或不实 quiet 证据均拒绝冻结。不能复制核心或用 fixture 成功值替代平台实现。
- Python 校验器随 Skill 装配。输入锁绑定同一批 state/prompt/transcript/raw/resource 字节，候选复制与清理后、发布前再次核对，状态复活或输入变化会拒绝。
- resource-metrics、execution-record、receipt wire 仍为 v1；新增五项指标仍属 COMMON-CM01。未知保持 null、known subtotal、coverage，不向 v1 填私有字段。
- discovery 新增 DoubaoWork **macOS 原生应用** Profile，核验 Bundle ID、主程序与 Browser helper，不要求 Electron app.asar；没有新增 Windows Doubao 支持。

受组件内容影响的版本全部更新，避免同版本内容哈希改变：

| 类别 | 版本 |
| --- | --- |
| 共享组件 | desktop-app-discovery 1.2.0；general-contracts 1.2.0 |
| General | execute 0.7.0；collect 0.5.0；run 0.5.0；orchestrate 0.9.0；report 0.2.2 |
| Web | execute 1.14.0；run 1.4.2；orchestrate 0.3.2 |

prepare/score 未升级。平台精确 `components.json` binding 按声明更新；vendor 必须由构建器同步。所有新发行重新构建并记录 source revision/content/ZIP SHA，活动旧 attempt 先按原版本收口。当前没有新生产包。

## 集成验证与证据边界

在上述必需源码的控制 worktree 完成 **155 项测试**，均退出 0：General Python 60、Node 34、Web Python 61。Python 使用主项目既有 `.venv/bin/python`，Node 使用本机既有运行时。

```text
python -m unittest discover -s tests/general_e2e -p test_contracts.py
python -m unittest discover -s tests/general_e2e -p test_e2e_build.py
python -m unittest discover -s tests/general_e2e -p test_run_general_e2e.py
python -m unittest discover -s tests/general_e2e -p test_shared_components.py
python -m unittest discover -s tests/general_e2e -p test_skill_layout.py
python -m unittest discover -s tests/general_e2e -p test_general_collection.py
node --test tests/general_e2e/general_finalize.test.mjs tests/general_e2e/astronstudio_finalize.test.mjs tests/general_e2e/astronstudio_trace.test.mjs tests/general_e2e/desktop_app_discovery.test.mjs tests/general_e2e/doubaowork_discovery.test.mjs
python -m unittest discover -s tests -p test_prepare_web_e2e_workspaces.py
python -m unittest discover -s tests -p test_web_e2e_skill_layout.py
python -m unittest discover -s tests -p test_run_web_e2e.py
python -m unittest discover -s tests -p test_web_e2e_resource_packaging.py
```

覆盖旧 Astron wrapper、WorkBuddy/Qwen 脱敏 v2 fixtures、空 PATH 下 ZIP 提取后正式 fixture receipt、来源哈希/路径反例、prompt/transcript 变化与 cleanup 期间状态复活。macOS 清理单测只终止自建测试进程；不等于任一新客户端真实进程覆盖已通过。Doubao 应用发现另有实际安装只读核验（2.28.12 x86_64）；不等于本轮 Web 执行通过。

尚未证明：新 Harness 正式 collect/评分闭环、Windows runtime、平台恢复/并发与生产准入。既有 Astron macOS smoke 仍只对应原 execution revision `457e355...`，不扩大为本次接口真机证据。

## 接收与下一项

先按台账检查未提交内容和活动 attempt，fetch 后固定完整 SYNC_SHA，确认包含此源码与本交接：

```text
git merge-base --is-ancestor eb23784a7ed25b0f0364db0392783de277b22b96 <SYNC_SHA>
git show <SYNC_SHA>:docs/design/e2e/archive/collaboration/handoffs/COMMON-002.md
```

| 接收任务 | 要求级别 | 有序动作与通过条件 |
| --- | --- | --- |
| MAC-WORKBUDDY-GENERAL / MAC-QWENWORK-GENERAL | REQUIRED_BEFORE_EXECUTION | 安全提交独立改动、merge SYNC_SHA、更新精确组件绑定并跑布局/本适配器测试。接入 trace v2 原生 collector 与真实平台 cleanup hook；先离线/脱仓，再按 COMMON 时段做单题。P2 journal 与 owner-lock 验证仍需完成 |
| MAC-DOUBAOWORK-WEB | REQUIRED_BEFORE_EXECUTION（新发行） | 采用 discovery 1.2.0 与 Web Skill 版本，验证真实安装/依赖和专属 Driver。General trace/finalizer wire 对 Web 不适用；Web journal、终态、资源与公共入口分别验收。已冻结 canary 按其原 revision 收口，不能中途换版本 |
| WIN-ASTRONSTUDIO-GENERAL | REQUIRED_BEFORE_EXECUTION | 接收 COMMON-001/002；在 Windows 开发 worktree 跑下述基线命令，再继续 G5-01。Windows 实现使用 CB-A + trace v2 + 自己的真实 win32 cleanup hook，不能调用 macOS wrapper 冒充支持 |
| 全部四项 | REQUIRED_BEFORE_CLAIM | 更新本平台任务卡 SEEN/ADOPTED/VERIFIED 与三个 SHA；只有目标平台实际闭环、恢复和脱仓验证通过才提升声明 |

Windows 本机建议先跑以下已有入口；测试中的 OS 专属 fixture/skip 如实记录，不代替目标机行为：

```powershell
python -m eval_general_e2e check-layout
python -m unittest discover -s tests/general_e2e -p test_contracts.py
python -m unittest discover -s tests/general_e2e -p test_run_general_e2e.py
python -m unittest discover -s tests/general_e2e -p test_shared_components.py
node --test tests/general_e2e/desktop_app_discovery.test.mjs
```

接着执行 [Windows 启动包](../../general/AstronStudio-Windows后续实施清单.md) G5-01 的只读环境/CDP/状态库盘点，再实现单题与采集。缺少 Windows hook 只阻塞正式冻结，不阻塞 probe、执行适配与 fixture。无需等待三个 Mac Harness 或新增五项指标全部完成。Windows 实际任务归属和验证结果由本机接收方填写，COMMON 不代填。

完整原始轨迹与 canary 产物留在来源机器调试目录；Git 只交付源码、脱敏 fixture 与证据索引。桌面时段当前分配与未释放现场见[控制推进记录](../control-progress.md)，不是分布式互斥锁。
