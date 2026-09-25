# DoubaoWork macOS Web E2E

Driver `0.7.6` 由 Web `execute-web-e2e 1.20.3` 独立发行。共用源码位于 `tools/report/e2e-shared/doubaowork/`，发行包自带 vendor；不需要安装 General Skill。Web 的 prepared task、正式记录、候选冻结和评分交接由本目录适配。真机准入范围以统一 Harness 接入契约与当次包 SHA 为准，历史 canary 和单测不代表生产通过。

## 单题执行

先在本目录运行 `npm ci --ignore-scripts --no-audit --no-fund`。客户端应已按调试参数启动；只读 probe 不会启动、重启、点击或发送：

```bash
node probe.mjs --endpoint http://127.0.0.1:9260 \
  --output-dir /absolute/debug-root/probe
```

正式入口要求 prepare 产生的 DoubaoWork v3 manifest 恰好包含一题。选择的项目目录是 `execution/tasks/<task_id>/`，产物目录是它的 `workspace/`。控制输出必须位于 Harness 根内、单题目录外。保持当前模型/权限，通过唯一项目、完整路径、模型及 Prompt 回读后最多发送一次：

```bash
bash <skill-dir>/scripts/run-doubaowork.sh <harness-root>/execution/tasks/<task_id> \
  --output-dir <harness-root>/.execute-web-e2e/doubao-single \
  --project-name WCB-Doubao-Web-L1 --formal-receipt
bash <skill-dir>/scripts/run-doubaowork.sh --resume --formal-receipt \
  --output-dir <harness-root>/.execute-web-e2e/doubao-single --observe-seconds 60
```

持续恢复同一 attempt，直到正式回执或明确需要处理的状态。观察窗口不是任务时限；发送不确定不能重发。未传 `--formal-receipt` 仍为开发观察路径。多题串行入口为 `run-doubaowork.sh --batch --harness-root <根> --run-id <ID> --run-slots 1`；它按 manifest 顺序逐题调用同一 Driver，完整任务集合收口后才发布根回执。恢复加 `--resume`，已发送题不重发。并发执行槽保持关闭。

## 原生证据与收口

1. `bound-evidence.mjs` 共享校验已绑定的 native IM、conversation、原生 request、project/完整 cwd、Prompt、终态、工具事件与轨迹快照。来源冲突失败关闭；不从“最近目录”猜身份。
2. Web v2 finalizer 还要求同次 UI 绑定、无待处理交互及后台空闲。未经记账的人工确认禁止自动收口；原生 Error 仅映射 `execution_error`，不能评分。
3. 通过前置校验后，按完整单题目录和 PID/启动/可执行身份清理本题进程。保留安静窗口与残留证据，不按 Node、Python 或客户端名称清理。
4. 对 `workspace/` 冻结 SHA；`.git` 拒绝，`.cache/.vite/node_modules` 按 Web runtime directory policy 忽略，原件保留。发布前后再次校验。
5. `formal.mjs` 独立写 Web `execution_record.json`、automation state、原始证据索引和 Harness `execution-receipt.json`。回执覆盖完整单题 manifest、实际模型、清理与候选哈希。
6. 发布事务先冻结每份字节，回执最后发布；中断后的 `--resume` 仅恢复原事务。已完成回执只读复验，任何原件漂移都拒绝。

日志和原始 ID 留在仓库外私有 debug 工作目录；正式单题原生证据位于 `.web-e2e-evidence/<attempt_id>/`。评分必须使用既有 scoring workspace 交接脚本，不直接进入 execution 候选。

## 指标边界

- 流程耗时优先采用发送至同一主机观测的原生完成事件；只有服务器完成时间时不能跨时钟相减。
- 原生 `elapsed_block` 提供时单独记录智能体耗时；错误/取消的观察时长不能冒充智能体耗时。
- 工具次数按已绑定原生 call ID 去重；覆盖不足时总数 null，仅保留已知小计和未知分母。
- Token、模型请求数、重试次数与费用没有可信原生账本时均为 null/unavailable。上下文窗口占用或订阅额度展示不等于消耗。

## 验证

```bash
npm test
node --check formal.mjs
node --check publication.mjs
```

离线 fixture、真实历史材料重采、新包真机执行和能力评分是不同证据等级。旧 `finalizer.mjs` v1 与 receipt bridge 的纯函数测试继续保留兼容，但公共正式入口必须经过 v2 原生门禁。
