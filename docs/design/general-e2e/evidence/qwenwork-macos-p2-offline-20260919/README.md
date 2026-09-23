# QwenWork macOS General E2E P2 离线 Driver 证据

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

日期：2026-09-19（Asia/Shanghai）。任务：`MAC-QWENWORK-GENERAL`。实现提交：`0b732fb432674eb2c1fd388018b1e66ede790066`。

## 结论

已完成 QwenWork 客户端专属 P2 离线实现和 mock 验收：严格 UI 控件定位、完整 Workspace 数据库回读、保持当前模型/权限、发送前 journal、一次 dispatch、原生 session/cwd/local-project/Prompt transcript 精确绑定、同 attempt 恢复不重发、可信终态和进程级 attempt 锁。

这不是 live canary 通过结论。本轮没有启动、重启、聚焦或退出 QwenWork，没有选择目录/项目，没有切换模型/权限，没有点击发送。当前仍缺桌面独占时段；General Skill 当前运行环境也没有独立装配 `playwright-core`，不能借用 Web Skill 的依赖目录。COMMON 的 CB-B/发行装配固定 SHA 尚未发布，正式 collect 和候选冻结仍未开放。

## 一次发送与恢复契约

1. Driver 在任何 UI 动作前创建 attempt journal；journal 的既有祖先和 leaf 出现 symlink 时拒绝读写。
2. 完整 Workspace 只认 `local_projects.root_paths[0]` 的绝对路径，不以 UI basename 代替。
3. 当前模型和权限都只回读、不切换；空值、未知权限、发送前漂移均失败关闭。
4. Prompt 填入并回读后持久化 project、完整 cwd、模型、权限、Prompt SHA 和 pre-send session baseline。
5. 调用发送前，原子写入 `dispatch_attempt_count=1`、`state=invoking`、`send_status=uncertain`；之后任何恢复只允许检查原 session，禁止再次调用发送动作。
6. 新 session 必须同时满足：真实 `sentAt`、精确 local project、完整 cwd、pre-send baseline 中不存在、创建时间边界，以及 transcript 中恰好一个 user text 的 SHA 与 Prompt 一致。旧 session 仅更新时间变化不算本 attempt。
7. attempt 锁覆盖 journal 读取、UI、发送和绑定全过程。锁记录 host、PID、进程启动身份和 owner ID；活 worker 或无法本机核验的 owner 拒绝接管。只有同主机 PID/启动身份明确死亡时，旧锁才归档为 `.stale-*` 后重新获取。
8. completed/failed/interrupted/cancelled/timeout 只有在无 active stream、停止已确认、session/cwd/binding 一致且观察源无冲突时才进入终态；否则为 `NEEDS_ATTENTION`，不冻结、不进入下一题。

## 新 General canary CLI

入口：

```bash
node tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs \
  --config /absolute/qwenwork-general-canary.json \
  --validate-only
```

live 首次执行和同 attempt 恢复的预留命令：

```bash
node tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs \
  --config /absolute/qwenwork-general-canary.json

node tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs \
  --config /absolute/qwenwork-general-canary.json \
  --resume --observe-once
```

冻结配置使用 `wildclawbench.general-e2e-qwenwork-canary-config/v1`，至少包含：

```json
{
  "schema_version": "wildclawbench.general-e2e-qwenwork-canary-config/v1",
  "config_digest_algorithm": "sha256-canonical-json/v1",
  "config_digest": "<calculateQwenCanaryConfigDigest 结果>",
  "identity": {
    "batch_id": "<batch>",
    "unit_id": "qwenwork-macos",
    "task_id": "<完整 General task ID>",
    "attempt_id": "<全新 attempt ID>"
  },
  "dataset": { "id": "<dataset>", "digest": "<dataset SHA-256>" },
  "task_root": "/absolute/execution-task",
  "candidate_workspace": "/absolute/execution-task/workspace",
  "prompt": { "path": "/absolute/execution-task/prompt.md", "sha256": "<Prompt SHA-256>" },
  "state_file": "/absolute/debug-root/automation-state.json",
  "evidence_root": "/absolute/debug-root/evidence/qwenwork",
  "client": {
    "bundle_id": "cn.qwenwork.desktop.mac",
    "endpoint": "http://127.0.0.1:9250",
    "session_db": "/Users/<user>/Library/Application Support/QwenWorkCN/data/agents.db",
    "trace_root": "/Users/<user>/.qwenworkcn"
  },
  "control": {
    "desktop_slot_id": "<控制任务分配的独占时段 ID>",
    "probe_path": "/absolute/new/read-only-probe.json",
    "probe_sha256": "<probe SHA-256>",
    "probe_max_age_seconds": 300,
    "model_policy": "keep-current",
    "permission_policy": "keep-current",
    "create_new_project": true,
    "live_execution_authorized": true,
    "timeout_ms": 30000
  }
}
```

`config_digest` 对除自身、运行时 `resume` 和内存中的 `prompt.content` 之外的 canonical JSON 计算。代码入口导出 `calculateQwenCanaryConfigDigest()`，配置冻结工具尚未接入公共 run 入口。

草稿字段填完后可在仓库根冻结 digest：

```bash
node --input-type=module -e '
import { readFile, writeFile } from "node:fs/promises";
import { calculateQwenCanaryConfigDigest } from "./tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs";
const path = process.argv[1];
const config = JSON.parse(await readFile(path, "utf8"));
config.config_digest = calculateQwenCanaryConfigDigest(config);
await writeFile(path, `${JSON.stringify(config, null, 2)}\n`, "utf8");
' /absolute/qwenwork-general-canary.json
```

## live 前置条件

- 控制任务明确分配 QwenWork 桌面独占时段；配置字段本身不视为 OS 锁。
- 新生成的只读 probe 在 300 秒内，应用身份正确、SQLite `quick_check=ok`、active/pending 为 0，且 probe 未执行 UI 修改或发送。
- QwenWork 已由获准的控制流程开放 loopback CDP；Driver 自身不会启动或重启客户端。
- General execute 发行闭包独立提供 `playwright-core` 或等价已审查 CDP 实现；不得从 Web Skill 运行时目录加载。
- macOS 辅助功能允许 General Driver 的 `select-folder.swift` 操作原生目录面板。
- 使用全新 General canary、全新 attempt 和隔离 debug root；正式 production output 仍不得写入调试根。
- COMMON 固定 CB-B/trace-index v2/cleanup hook/组件版本后再做正式 collect；本轮仅允许 execute canary 采样。

## 回退方案

- 发送前失败：保留 journal 与项目现场，不删除或伪造同 attempt；修复后只有 journal 仍为 `PREPARING` 或 `READY_TO_DISPATCH/count=0` 才能继续。
- `invoking/attempted/uncertain`：只使用 `--resume` 查询原 project/session/transcript；无匹配、多个匹配或 Prompt 不一致均保持 `NEEDS_ATTENTION`，禁止重发。
- active stream、数据库状态和 UI 停止控件冲突：不冻结、不进入下一题，保留现场交由人工核查。
- 活 worker 锁：拒绝第二 worker；陈旧锁只在同主机 PID/启动身份明确死亡后归档接管。
- 依赖或发行装配未满足：只运行 `--validate-only`，停用 QwenWork live Driver；不回退到 Web E2E Driver。

## 离线验证结果

```text
QwenWork Node focused                           25/25 PASS
QwenWork Python adapter                         3/3 PASS
COMMON public regression                       55/55 PASS
Node syntax checks                             PASS
git diff --check                               PASS
```

25 项 Node 测试覆盖 UI 控件唯一性、模型/权限漂移、完整 Workspace、不安全相对 cwd、intent/invoking 中断、唯一/无/多 session、Prompt transcript 绑定、同/不同 attempt、终态冲突、停止未确认、工具 completed≠success、工具结果冲突、journal symlink 和双 worker dispatch 上限。
