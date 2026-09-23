# MAC-QWENWORK-GENERAL-003：SLOT04 发送前门禁失败证据与加固需求

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 创建时间 | `MAC-QWENWORK-GENERAL-003` / 2026-09-19（Asia/Shanghai） |
| 来源任务 | `MAC-QWENWORK-GENERAL` |
| 目标任务 | COMMON / 控制任务 |
| Driver 源码 / 桌面时段 | `9081df5288d59c83e9e4d34d3bc8b288d96d7568` / `SLOT-MAC-20260919-04` |
| 结果分类 | `NEEDS_ATTENTION`；发送前 UI 控件歧义，`PROMPT_SENT=0` |
| 集成状态 | LOCAL_ONLY；未 push、未集成；SLOT04 已释放 |
| 证据 | [SLOT04 canary](../../../../general-e2e/evidence/qwenwork-macos-slot04-canary-20260919/README.md) |

## 结论与有效边界

真实 release/prepare/verify-batch 通过，且 worker 只解压 execution 包；QwenWork 启动后的只读 UI 前检也读到空草稿、当前模型和当前权限。但 project selector 在排除权限按钮后仍有两个可见候选，Driver 严格失败关闭，没有调用任何目录选择、project 创建、Prompt 填写或发送动作。

因此本轮不是一次 attempt 的执行失败：没有 attempt journal，没有 session/cwd/Prompt 绑定，没有 resume，也没有可供 collect/score 的候选。不得把它计入模型、任务或 Harness 执行分数。

## 现场结构与失败点

当前 selector 为 `.new-task-chat-input button[aria-haspopup="menu"]`。现场存在三个可见匹配，其中一个以 `aria-label="选择权限模式"` 排除，剩余两个仍无法按稳定语义区分。旧实现正确拒绝二选一；后续不得改成 `nth()`、`first()` 或按当前 DOM 顺序挑选。

修复目标是把候选限定到唯一可见的当前新任务视图，并以项目控件语义确认。至少新增以下反例：

- 同一当前视图有两个可见 menu button 时失败关闭。
- 当前视图一个可见项目控件、一个隐藏重复控件时只接受可见唯一项。
- 旧/隐藏视图保留控件时不与当前 `.agents-chat-view-root` 混淆。
- 权限控件与项目控件都使用 `aria-haspopup=menu` 时不能靠排除一个中文 label 后猜剩余顺序。

## 退出与数据库恢复

程序化 quit/TERM/精确进程处理没有形成已验证的正常退出；QwenWork 显示确认弹窗，用户手动点击退出后才完全退出。交接只确认最终无 QwenWork 主进程、无 9250 监听、无数据库占用，不声明自动 cleanup 通过。

客户端完全退出后 WAL/SHM 消失，当前 probe 的临时复制仍用 `sqlite3 -readonly` 打开 sidecar-free WAL 主库并报 error 14。严格无写者条件下 `immutable=1` 诊断得到 `quick_check=ok`、session 21、active/pending 0，但该手段不能直接用于活动数据库：活动 WAL 可能包含尚未 checkpoint 的真实状态，immutable 会静默忽略。

probe 修复的接收条件：

1. 关闭、无写者、无 WAL/SHM 的主库可安全只读，并覆盖 error 14 反例。
2. 活动数据库只使用一致快照，复制主库及存在的 WAL/SHM；不直接 immutable。
3. WAL 在复制期间变化、sidecar 出现/消失、检测到写者或快照身份不稳定时失败关闭并重试有界次数。
4. 不创建、删除、checkpoint 或修复用户数据库及 sidecar。

## 接收动作

| 接收方 | 动作 | 通过条件 |
| --- | --- | --- |
| 本任务 | 单独提交 selector 修复与反例 | 按可见/当前视图/项目语义唯一定位；重复候选继续失败关闭 |
| 本任务 | 单独提交 probe 快照修复与反例 | sidecar-free 关闭库 PASS；活动 WAL 保留最新行；并发漂移失败关闭 |
| 本任务 / COMMON | 合并父任务的 CLI main-guard 修复 `dc5ff64` 后复核脱仓 ZIP | 不重复修改同一区域；仓库外 `--help` 正常 |
| 控制任务 | 上述修复审查完成后分配新 QwenWork-only slot | 使用全新 attempt；发送前重跑 probe/UI 唯一性门禁 |

## 未声明范围

未声明 Prompt 发送、同 attempt 恢复、任务完成、正式 collect、cleanup、评分/回传/报告或并发通过。用户手动退出不是自动恢复证据，诊断性 immutable 读取也不是生产 probe 通过证据。
