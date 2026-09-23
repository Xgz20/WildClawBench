# COMMON-003：三个 macOS 开发驱动集成与采样交接

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 时间 | COMMON-003 / 2026-09-19 20:50 +08:00 |
| 来源 / 目标 | COMMON → MAC-WORKBUDDY-GENERAL、MAC-QWENWORK-GENERAL、MAC-DOUBAOWORK-WEB、WIN-ASTRONSTUDIO-GENERAL |
| 必需源码 | `dc5ff64c3d7b91ae0ecc6669583f5bd3d69c13c3` |
| 前序基线 | COMMON-002；源码 `eb23784a7ed25b0f0364db0392783de277b22b96`、台账 `46a23a43572aed34bc2eec457d67423e2bce08af` |
| 同步目标 | GitHub `feature/astroncode-eval`；取得包含本文的完整 SYNC_SHA，再核验源码祖先关系 |
| 支持级别 | 开发入口、解析器、fixture 与发行闭包；三个客户端均未完成正式执行/采集/评分闭环 |

## 已集成范围

| 平台 | 保留的原始交付 | 控制侧审查与集成 |
| --- | --- | --- |
| WorkBuddy General | P2 `e388dfa`、公共组件绑定 `b3ac3da` | merge `8dac427`；取消/中断终态、原生文件快照、路径、单次发送与 owner lock、stale 锁拒绝接管修复；23 项专属 Node 测试 |
| QwenWork General | P2 与后续修复至 `9081df5288d59c83e9e4d34d3bc8b288d96d7568` | merge `c4b1f7b`；会话/UI 停止绑定、Qwen AX 面板归属、恢复 probe 与终态重放修复；32 Node + 3 Python |
| DoubaoWork Web | P2 `47dcaee`、COMMON-002 merge `ca7cc2e`、证据更正 `3a3057c` | merge `b484085`、`769e9b5`；开发 journal/Driver、原生采样、来源/去重、唯一 observation 文件修复；39 项专属 Node 测试 |
| 集成与发行入口 | `db67389`、`dc5ff64` | 新 Driver 装入 execute 包，更新 Skill 开发入口与版本；Qwen CLI 用真实路径识别 main，修复 macOS `/var` 别名下 exit 0 却无执行/帮助输出的问题 |

代码审查通过仅表示可以进入限定的开发 canary，不是生产准入。WorkBuddy 真机输入问题在源码基线中尚未修复；QwenWork 当前 runtime 的 usage profile 仍需本机对账；DoubaoWork 仍缺正式 Web 收口。不能从目录名存在推断公共 run 已支持这些客户端。

## 版本与依赖

本轮升级 `execute-general-e2e` **0.8.0**、`execute-web-e2e` **1.15.0**。COMMON-002 的其他版本保持：desktop-app-discovery / general-contracts 1.2.0；General collect 0.5.0、run 0.5.0、orchestrate 0.9.0、report 0.2.2；Web run 1.4.2、orchestrate 0.3.2。没有改 wire Schema、指标公式或新增五项指标。

WorkBuddy Driver 使用 Node >=22 的原生 WebSocket/CDP；QwenWork 和 DoubaoWork 各自带 `package.json` 与固定 lockfile，按各自说明在独立 Driver 目录执行 `npm ci --ignore-scripts --no-audit --no-fund`。ZIP 包含依赖声明与源码，不包含安装后的 node_modules；Qwen `--help` 不要求先安装 Playwright，实际 CDP 连接需要它。集成验证已安装 Doubao 的固定依赖。不能依赖 Web Skill 的 node_modules 恰好存在来运行 General Driver。

没有发布新生产发行包；测试构建包不是可复用的生产身份。重建时记录新的 source revision、content/ZIP SHA。活动 attempt 保持原输入包、配置与 live 源码，不在观察或恢复期间切换版本。

## 组合验证

控制 worktree 完成 **252 项不重复测试**：General Python 63、Node 128（公共 34、WorkBuddy 23、QwenWork 32、DoubaoWork 39）、Web Python 61，均通过。Qwen CLI 修复后复跑 General Python 63 与 Qwen Node 32；其他组对应相同未变化源码。Python 使用项目 `.venv` 和 `unittest`；该环境没有 pytest，一次 pytest 启动失败不计入测试执行结果。

```text
python -m unittest tests.general_e2e.test_contracts tests.general_e2e.test_e2e_build tests.general_e2e.test_run_general_e2e tests.general_e2e.test_shared_components tests.general_e2e.test_skill_layout tests.general_e2e.test_general_collection tests.general_e2e.test_qwenwork_adapter
node --test tests/general_e2e/general_finalize.test.mjs tests/general_e2e/astronstudio_finalize.test.mjs tests/general_e2e/astronstudio_trace.test.mjs tests/general_e2e/desktop_app_discovery.test.mjs tests/general_e2e/doubaowork_discovery.test.mjs tests/general_e2e/workbuddy_*.test.mjs tests/general_e2e/qwenwork_*.test.mjs tools/report/skills/web-e2e/execute-web-e2e/drivers/doubaowork/test/*.test.mjs
python -m unittest tests.test_prepare_web_e2e_workspaces tests.test_web_e2e_skill_layout tests.test_run_web_e2e tests.test_web_e2e_resource_packaging
```

覆盖 General execute ZIP 脱仓后 WorkBuddy/Qwen 入口、Qwen probe、通用采集与旧 Astron wrapper、多来源与路径/竞态反例、Web 包内 Doubao Driver/lockfile/Swift 文件。不是全仓测试，也不是 Windows 或三平台完整真机通过。

## 当前 live 事实

- **WorkBuddy**：SLOT02 完成启动与 probe；SLOT03 attempt `3e554524-6599-4182-aecc-3257977867c0` 只有 reservation/dispatch_attempt=1，实际发送按钮 click=0、send=0、native candidate session=0。Prompt DOM 回读正确但按钮 disabled，Driver 拒绝点击。同 attempt resume 未重发。原 31 字草稿正文和 HTML 哈希均恢复，私有证据留在本机，SLOT03 已明确释放。平台继续离线修复真实输入事件与发送前 enabled 门禁，此修复不在本基线内。
- **QwenWork**：已审查源码 `9081df5` 获得 SLOT04；真实 prepare/verify-batch 已通过；发送前 project trigger 匹配 2 个候选，Driver 拒绝操作，未建项目/填 Prompt，send=0、无 attempt journal。退出最后由用户手动确认；精确主进程、9250 监听和数据库写者已消失，SLOT04_RELEASED。关闭后的 sidecar-free WAL 数据库触发只读 probe error 14，现有探针恢复未通过；补充 immutable 读取仅在无写者核验后确认 quick_check=ok、active/pending=0。平台离线修 selector/安全只读 DB，用户手动关闭不计为自动恢复通过。CLI 集成修复没有中途替换该批次源码。
- **DoubaoWork**：一次实际发送，UI/native session 唯一绑定，倒计时 HTML 和两张截图存在。先前“只有 .gitkeep”的结论已纠正；完整更正见 [MAC-DOUBAOWORK-WEB-002](MAC-DOUBAOWORK-WEB-002.md)。native terminal/cwd 未确认、HTTP 服务进程有残留、最新回复与截图归档不完整，保持 NEEDS_ATTENTION。prepared input 的 c098... 不是 live Driver 的精确 revision；live 未冻结代码快照，不能用事后 47dcaee 代替。

三个任务的原始候选、数据库、轨迹、截图和草稿留在本机 debug 目录；Git 只含源码、脱敏 fixture 与证据索引。时段是控制调度记录，不是跨进程实时锁。没有配置定时巡检。

## 接收动作

```text
git merge-base --is-ancestor dc5ff64c3d7b91ae0ecc6669583f5bd3d69c13c3 <SYNC_SHA>
git show <SYNC_SHA>:docs/design/e2e/archive/collaboration/handoffs/COMMON-003.md
```

| 目标 | 必需动作 / 通过条件 |
| --- | --- |
| WorkBuddy | 安全提交当前离线修改后采用本基线；完成真实编辑器输入、发送就绪和 journal 顺序修复。原未发送 attempt 保留，不重置计数。新 canary 另建调试 attempt 并等待控制分配桌面。正式 collector/cleanup 独立交付 |
| QwenWork | SLOT04 已释放；提交单独采样交接，再采用基线和 CLI 修复。修可见项目控件唯一定位与无 sidecar 的关闭数据库只读 probe；不靠首个控件或活动库 immutable 绕过。collector 独立审查 |
| DoubaoWork | 采用更正索引与新 execute 版本；继续离线核验可信 terminal/完整 workspace 等价绑定、精确进程清理。公共 Web 接口由 COMMON 明确最小复用方案，不修改其他 Harness 默认行为；不重复原 Prompt 补证据 |
| Windows AstronStudio | REQUIRED_BEFORE_NEXT_RELEASE：处理 COMMON-001/002/003 并回写 SEEN/ADOPTED/VERIFIED、SYNC_SHA/实际 HEAD。无活动批次时采用新基线，按 COMMON-002 的 Windows 基线命令继续 G5-01。已活动的 Windows 批次先保持原版本收口。本轮不改变 Windows wire 或 cleanup 要求，不必等待 Mac canary/指标完成 |

后续共用新增五项指标仍属 COMMON-CM01。macOS/Windows 各自验证，代码推送或 fixture 通过不能替代对方真机结果。
