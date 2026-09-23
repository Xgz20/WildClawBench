# QwenWork macOS General E2E SLOT04 canary 证据

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

日期：2026-09-19（Asia/Shanghai）。任务：`MAC-QWENWORK-GENERAL`。桌面时段：`SLOT-MAC-20260919-04`。Driver 源码：`9081df5288d59c83e9e4d34d3bc8b288d96d7568`。

## 结论

SLOT04 在发送 Prompt 前按门禁失败关闭：当前视图内的 project trigger 经过权限按钮排除后仍有两个可见候选，Driver 返回 `QWENWORK_UI_CONTROL_COUNT: project-trigger:2`。本轮 `PROMPT_SENT=0`，没有选择目录、创建 Workspace project、填写 Prompt、创建 attempt journal 或进入 resume。

这不是模型失败、任务失败或一次 General 执行失败；它是 UI 控件唯一性前置检查失败。不得把本轮计入模型能力结果，也不得用 `nth()`、`first()` 或固定索引绕过歧义。SLOT04 已释放，重新执行必须先完成 selector 离线修复、反例测试和审查，再申请新桌面时段。

脱敏的结构化摘要见 [verification-summary.json](verification-summary.json)。原始本机报告保留在 debug workspace，不复制含本机绝对路径的文件入仓。

## 发行与 prepare 身份

| 项目 | 结果 |
| --- | --- |
| release | `qwenwork-p2-9081df5`，source revision `9081df5...7568` |
| suite ZIP | SHA-256 `a43eae29182e073aafadb378c63cb245c05f55758df48edd05853a34e2ff5ed6` |
| execute Skill | `0.7.0`，content SHA `d35bef...5b2b`，ZIP SHA `7caa33...496` |
| collect Skill | `0.5.0`，content SHA `9b15b1...a2d`，ZIP SHA `2e1e5f...a7ea` |
| dataset | `general-custom60-v1`，bundle SHA `69562a...9f8`，digest `119568...d0a` |
| batch / unit | `qwenwork-macos-p2-9081df5-social-20260919-202600` / `qwenwork-macos-x86-64-slot04` |
| task | `03_Social_Interaction_task_003_colleague_leave_reply` |
| verify-batch | `PASS`；1 task、1 unit、execution/scoring 两个包 |
| worker 边界 | 只解压 execution ZIP；scoring ZIP 未解压到 worker |

首次从当前数据集源码重建 bundle 时发现源码与既有冻结 manifest 不一致，流程失败关闭，未运行 `update-lock`。随后使用既有冻结 dataset ZIP 完成 prepare；这两件事不能混写为“新数据集重建成功”。

## 发送前 UI 证据

只读前检确认草稿为空、唯一可见任务视图为 1，保持当前模型 `标准｜Qwen3.8-Flash` 和权限 `full-access / 完全访问`，未切换配置。

本轮 selector 的脱敏结构是：

```text
当前新任务输入区 .new-task-chat-input
└── button[aria-haspopup="menu"]：3 个可见控件
    ├── aria-label="选择权限模式"：1 个，明确排除
    └── 剩余 project trigger 候选：2 个，语义无法唯一判定
```

现场只保留控件作用域、ARIA 类型和计数，不保存项目名或其他用户内容。Driver 在任何目录选择、project 创建和 Prompt 输入之前抛错，`ui-preflight.json` 明确记录 `mutations_performed=[]` 与 `prompt_sent=false`。

后续修复必须按“可见 + 当前新任务视图 + 项目语义”取得唯一控件，同时覆盖重复可见控件、隐藏重复控件及旧视图残留；不能依赖 DOM 顺序。

## 启动与退出恢复边界

启动前 probe：QwenWork 未运行、9250 未开放、SQLite `quick_check=ok`、历史 session 21、active/pending 0。启动后 CDP 可读，UI 前检完成，但未进入任何执行动作。

退出时 AppleScript quit、TERM 和精确主进程处理没有形成可验证的自动退出闭环；QwenWork 出现退出确认弹窗，用户手动点击退出后才完全退出。因此本轮只记录“用户确认后的最终静态状态”，不声明自动退出/清理通过。`probe-after-restore.json` 的时间早于最终人工确认，且其中仍显示 QwenWork 运行，不能作为最终恢复证据。

人工确认退出后的最终只读检查（20:59:15 +08:00）：

- 精确 QwenWork 主进程不存在，9250 无监听。
- `agents.db`、WAL、SHM 没有进程占用；WAL/SHM 已不存在。
- 当前 Driver 快照路径和直接 `sqlite3 -readonly` 对 sidecar-free WAL 数据库均报 `unable to open database file (14)`，所以没有生成 `probe-after-restore-final.json`。
- 没有创建、删除、修复或 checkpoint 用户数据库及 sidecar。
- 仅在确认无 QwenWork 进程、无 9250、无数据库写者且 WAL/SHM 不存在后，用 `immutable=1` 做诊断性读取：`quick_check=ok`、session 21、active/pending 0。该结果只证明最终主库静态内容可读，不等于生产 probe 或自动恢复通过。

probe 修复必须区分：关闭且无写者的 sidecar-free 数据库可以在安全快照条件下采用 immutable 读取；活动数据库必须复制主库与现存 WAL/SHM 后读取，不能直接 immutable 而忽略未 checkpoint 的 WAL。严禁为了让 probe 通过而创建、删除或修复用户数据库 sidecar。

## 本地证据哈希

原始证据根：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-e2e/slot04/qwenwork-general-p2-9081df5-social-20260919-202600`。

| 文件 | SHA-256 | 大小 |
| --- | --- | ---: |
| `release/general-e2e-release-manifest.json` | `c25b1b26a31bce332b370bd54fb3aef6ad45410a0d70ae443762cff99cfa20b8` | 2970 |
| `prepared/.../manifest.json` | `3c5f8deb7633a026c3c93276ea2a7dcc5369bc42b218734e4f071759378c8a9d` | 5689 |
| `worker/.../manifest.json` | `be5ec7d99d95309095cce71224121c7b5dcd1ffbb0d0ea9db8bf9bbb3d1a6e1d` | 3470 |
| `probe-before-launch.json` | `21f8addc73f3e0a05b2eb3c1431b1a8ceba065279b8e5895da1fb8e63a6de1c6` | 3151 |
| `probe-after-launch.json` | `d71bbd7e73e64797eeb820cee5874e5007a1284de846bc2ce59b20b7bea54460` | 3381 |
| `probe-after-restore.json` | `3fca9048040743973cc8e4925638989bb81a00cc1062d9e166b42b75161883d2` | 3381 |
| `ui-preflight.json` | `ecc160e47fb35f753587c63ea4038b843784400d74faef92f1d53cf727b7fdac` | 995 |

`probe-after-restore.json` 仅是退出过程中的中间快照，不是最终恢复通过证明。

## 下一步

1. 独立修复 project trigger：基于当前可见新任务视图的语义唯一性，不按序号选取。
2. 修复 SQLite 只读快照：覆盖关闭后无 sidecar、活动 WAL 和并发写入三类反例；无写者证据不足时失败关闭。
3. 重新审视退出策略：默认不以自动 TERM/KILL 作为正常成功路径；需要退出确认时保留人工动作和未验证边界。
4. selector/probe 修复审查通过后申请新的 QwenWork-only slot，从全新 attempt 重试。
