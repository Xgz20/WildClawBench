# COMMON-004：WorkBuddy 输入修复与下一轮平台加固

| 字段 | 值 |
| --- | --- |
| 来源 / 目标 | COMMON → MAC-WORKBUDDY-GENERAL、MAC-QWENWORK-GENERAL、MAC-DOUBAOWORK-WEB、WIN-ASTRONSTUDIO-GENERAL |
| 日期 / 前序交接 | 2026-09-19 / COMMON-001、002、003 |
| 必需源码 | `2023b4d5d1d703c81ff8ed15e0d5ada29cd0dca4` |
| 同步 | GitHub `feature/astroncode-eval`；固定包含本交接的完整 SYNC_SHA，核验必需源码为其祖先 |
| 版本 | General execute **0.8.1**；其余 COMMON-003 版本保持；无 wire/指标公式修改 |

## 本批已集成

WorkBuddy `5bea7621e4c90222d3f2e0000ab1ca6093af6e0b` 使用 `Input.insertText`，要求唯一空编辑器获得焦点，完整 Prompt 回读一致且发送按钮唯一、enabled 后才 armed。保护已有草稿；disabled 在发送前失败，attempt reservation 保持 0。已 armed 的不确定发送仍只能恢复观察，不能重发。

新增交接 [MAC-WORKBUDDY-GENERAL-002](MAC-WORKBUDDY-GENERAL-002.md) 与 [MAC-QWENWORK-GENERAL-003](MAC-QWENWORK-GENERAL-003.md) 已集成，保留旧交接。WorkBuddy 原 SLOT03 reservation=1、实际 click/send=0，草稿已恢复；Qwen SLOT04 send=0、无 attempt，最后依赖用户确认退出，关闭库 probe error 14 未修复。控制任务核对 Qwen 提交的 7 份本地证据，大小/哈希全部匹配。后续 live 结果另行交付，不扩大这些旧证据。

控制 worktree 在本批代码完成完整 **254/254** 组合回归：General Python 63、Node 130（公共 34、WorkBuddy 25、Qwen 32、Doubao 39）、Web Python 61，均通过。新增 WorkBuddy 输入 fixture 另用 VM 执行真实 DOM 表达式验证 7 项保护分支；不是浏览器或真实 React 输入证明。

```text
node --test tests/general_e2e/workbuddy_*.test.mjs
python -m unittest tests.general_e2e.test_e2e_build tests.general_e2e.test_skill_layout tests.general_e2e.test_run_general_e2e tests.general_e2e.test_shared_components
```

## 接入决策与未合入项

[Doubao Web 接入边界](../doubaowork-web-integration.md)明确采用现有 Web v1 正式记录/回执。原生 cwd/terminal 缺失保持未知，允许以归档的 conversation/project/完整 workspace/Prompt、正向 UI 终态和真实 cleanup 形成等价证据链。每次观察必须匹配绑定会话。COMMON 只做必要的路由、指标注册和专属严格 gate，不引入第二套 Web 收口协议。

Doubao 新 cleanup 提交 `0f6d2c6` **未合入、不得用于真实目标清理**。独立内存反例发现 reparent 后漏跟踪子进程、PID 复用后仍发信号、信号前归属过期、合法 `..cache` 子目录遗漏及 workspace 实体替换问题，已交回平台修复。既有 46 项测试通过不能覆盖这些动态缺陷。真实 canary 残留未因此被操作。

Qwen selector/关闭库 probe 修复及两平台正式 collector 均尚未作为本批源码发布。WorkBuddy SLOT05 已获准验证输入修复，需保持本次冻结源码/包身份、私有草稿保护和一次发送；其进行中状态见[控制记录](../control-progress.md)，不能从本交接推断已发送或已完成。

## 接收动作

| 目标 | 要求 |
| --- | --- |
| WorkBuddy | REQUIRED_BEFORE_NEXT_RELEASE：当前 SLOT05 按已冻结版本安全收口并明确释放，之后采用 0.8.1。不要为了更新版本中途重建 attempt；原 SLOT03 永不重发或重置。继续专属 collector/cleanup |
| QwenWork | REQUIRED_BEFORE_NEXT_RELEASE：先完成当前离线 selector/只读 DB 修复，提交后空闲合入。采用修复后的 main guard 和新 execute 版本；新真机时段需审查后分配 |
| DoubaoWork | REQUIRED_BEFORE_CLAIM：按等价证据方案补平台链路，优先修 cleanup 动态反例，再交 COMMON 复核/接线。原始轨迹字段不能伪造，旧 canary 不追溯升级为正式回执 |
| Windows | REQUIRED_BEFORE_NEXT_RELEASE：本批只影响 General execute 包身份与 WorkBuddy 输入实现；Windows Schema/cleanup 要求不变。当前本机工作可继续，下一发行前采用固定 SYNC_SHA 并跑相应布局/打包回归，无需等待 Mac 验收 |

所有任务先安全提交独立工作，核验固定 SYNC_SHA 和源码祖先，再合并；不 reset/stash、不覆盖活动批次。记录 SEEN/ADOPTED/VERIFIED 的实际范围，fixture 通过不能代表目标平台完整闭环。
