# G4-01 流程串联与回传恢复证据索引

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

## 交付范围

- `run-general-e2e 0.2.0/interface_only`：batch/unit 两级阶段状态、显式阶段冻结、外部输入 SHA 锁和恢复动作。
- 标准完成入口：AstronStudio 终态 automation state、采集/报告 receipt、评分 submission、package 和 import；不允许用手工状态把阶段标成完成。
- 确定性回传包：固定 ZIP 时间、权限、排序和存储方式，逐成员记录类型、SHA 和大小；排除评分 `runtime/`、缓存及常见凭据文件。
- 安全导入：拒绝绝对/反斜杠/`.`/`..` 路径、重复成员、未知类型、越界链接、哈希/身份/范围漂移；手工解包到暂存目录后原子发布。
- 恢复与冲突：相同 archive SHA 幂等；索引丢失但已发布的同 package 可恢复登记；同一 unit 不同内容保留独立 package，清空选择并进入 `NEEDS_ATTENTION`，显式选择后恢复。

## 自动验证

- General E2E：`uv run python -m unittest discover -s tests/general_e2e -p 'test_*.py'`，113/113 PASS。
- 旧 `eval_e2e`：`uv run python -m unittest discover -s tests -p 'test_e2e_*.py'`，60/60 PASS。
- 13 个 Skill `quick_validate.py`：全部 PASS。
- `python -m eval_general_e2e check-layout --json`：7 Skills、6 components、0 errors。
- `run-general-e2e` 聚焦 fixture：阶段/输入漂移失败关闭、确定性 ZIP、runtime 排除、安全相对链接、路径穿越拒绝、同包幂等、冲突并存、显式选择均 PASS。
- 独立 Skill ZIP 与 General release/suite 构建、验包、仓库外 `-I` 装载均 PASS；run Skill 独立 vendoring `general-contracts 1.0.0`。
- Python 编译、`git diff --check` 和凭据模式扫描 PASS。

## 证据边界

以上是当前 macOS 开发机上的静态、离线 fixture 和独立发行证据。G4-01 未启动 AstronStudio、未调用真实 Codex/API Judge、未启动 Docker，也未生成 G4-02 报告。macOS 四题完整生产闭环与 Windows 真机仍为 `NOT_RUN`，不能由本项测试推断通过。
