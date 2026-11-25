# E2E 用例内容与发行制品

## 新任务的版本规则

页面仍然按用例 ID 手动勾选。未指定冻结版本时，从当前用例文件构建本批次的输入，
`source.revision` 使用 `sha256:<内容摘要>`。摘要覆盖所选题目、输入素材、私有评分材料、
执行及评分契约、题源登记和数据包 schema，不读取 Git 日志；无关代码提交不改变它。

新任务只提供每个用例库登记的最终冻结版本，由 `default_release` 明确指定：

| 用例库 | 最终冻结版本 |
| --- | --- |
| 基础回归 | `general-custom60-v1` |
| 真实工作 | `general-custom70-v6` |
| 通用挑战 | `general-challenge60-v3` |

通用挑战原名称已改为 `general-challenge60-v3`，冻结清单和题源登记投影按新身份重新计算摘要，
60 道题的题面、素材、评分契约和统计保持一致。新任务不接受旧名称。

真实工作 v2—v5、116 题历史版和独立单题历史版不再出现在新任务列表或 E2E 发布包中。
直接以退役版本创建 E2E 批次也会被拒绝。仓库中的旧清单、快照和开发校验工具仅作为历史资料，
不要求服务器具备这些版本的重建能力。

已创建批次继续读取自己的 `batch.json`、输入、冻结 Skill 和绑定的执行器发行。
恢复、评分和报告不重新选题，也不把历史批次改为最新冻结集。旧发行目录和批次快照应保留。

## CI 构建和服务器读取

在框架源码 checkout、Python 3.11.8 或更新环境中执行：

```bash
python -m src.e2e.dataset_assets --output /tmp/wcb-release-assets
```

构建需要 PyYAML 和 python-dotenv。CI 将每个最终冻结版本编译并与原冻结清单严格比较，
再输出独立 ZIP 及 `index.json`。旧布局的最终版本在此阶段从既有源码锚点整理材料；
浅克隆需要获取 `datasets/layout.json` 中的历史源提交。此操作只在构建端发生。

发布制品将上述输出放在根目录的 `.wildclawbench-assets/` 下，不携带 `.git` 和
`eval_general_e2e/datasets/source-snapshots/`。服务器读取 ZIP 并校验整包摘要、文件成员、
每个文件和冻结清单；包缺失或内容漂移即失败，不回退到 Git 重建。

```bash
cd /path/to/framework-release
.venv/bin/python -m src.e2e.dataset_assets --verify
```

`.wildclawbench-revision` 仍记录 CI 构建的框架 commit，供执行器和 Skill 发行追溯。
它与数据集的内容摘要分开使用；数据集内容版本不再由 `git log` 推断。
独立源码 checkout 的执行器版本仍可从 Git 读取，制品运行则使用发布标记。

平台仓库 `deploy/cicd/wildclawbench-framework-cicd.sh` 已包含资产构建、归档和部署验包命令。
CI 平台中复制保存的构建段、部署段需要同步更新；仅推送脚本文件不会改写平台任务配置。
