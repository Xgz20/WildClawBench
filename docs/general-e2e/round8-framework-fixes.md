# Round8 框架修复同步

本次直接在 `feature/astroncode-eval` 工作分支同步。以同步前的 `22a871a0` 为仓库基线，移入生产评测冻结包中的九项补丁，同时保留该分支在 `61bba6fd` 之后已有的评分与取证修复。历史发行、数据集、执行、候选、评分和规范报告不改写。

逐项来源、原生产修订、补丁 SHA 和涉及文件见 [修复索引](round8-framework-repair-index.json)。索引引用研究交付包的 `ControlAudit/FrameworkPatches`，不把真实候选、SDK 正文、账号或控制机配置提交进仓库。

## 已接入的生产修复

| 问题 | 原生产修订 | 标准实现与约束 |
| --- | --- | --- |
| 首次预检被拒绝但没有落盘 state，队列无法安全恢复 | `79609087` | 执行器持久化零发送预检失败；`recover_astronstudio_missing_preflight.mjs` 只恢复精确受支持的旧状态，保留原失败与队列 SHA，不创建项目、不发送 Prompt |
| 新建项目路径未真正提交，或点击了其他提交按钮 | `f9047bbc` | 回读精确目录值，只选同一表单中相邻的提交按钮，拒绝歧义 |
| 项目表单尚未关闭便开始下一次导航 | `55d50fb2` | 等待提交完成、表单关闭以及完整 Workspace UI 稳定后继续 |
| 已完成的本单元页面被误判为外来活跃任务 | `ee58b3a0` | 核验完成态、任务归属和原生绑定后才导航，再重新检查全部发送门禁；外来或活跃任务继续拒绝 |
| 已结束且透明的完成提示层被当作阻塞对话框 | `2b83cc71` | 仅排除精确的零透明度、不可交互、已结束提示；其他弹窗和未知形状不放行 |
| 隐藏页面或未就绪窗口中发生未受理的物理发送 | `3a29cac0` | 激活已核验的现有窗口并复核 PID；隐藏页面禁止发送；准备状态与恢复元数据明确归档 |
| DOM 显示可见但系统前台实际属于其他应用 | `cb8a6391` | 核验 macOS 原生前台 PID、发送前完整预检，并在物理点击前再次确认归属 |
| 复制相对符号链接时，0777 变为宿主默认模式 | `ba833066` | 采集、评分输入、回传导入和研发复制均设置新链接自身模式并复核，不跟随目标、不改源链接 |
| 先恢复只读父目录权限，导致子成员无法复制 | `57b86cbe` | 全部子成员落盘后由深到浅恢复目录权限；独立逐题选择导出器同样保留链接自身模式 |

执行器新增的前台与可见性模块、零发送恢复脚本和相应测试均随源码及发行打包。后续运行使用标准队列与恢复入口，不再从本轮私有目录复制临时修复程序。

## 报告与回归中补齐的修复

- 内部评分详情表名将 `@` 规范为 `_`，仍按大小写冲突和 31 字符限制消歧。公开的模型名、客户端版本及原始单元身份不变。真实 Artifact Tool 的导出、重新导入和重算测试证明跨表引用仍能定位原工作表，避免只检查缓存值而漏掉重新计算后的 `#REF!`。
- 普通 Markdown 与领导版共用 `ROUND_HALF_UP` 显示函数。仅校正浮点聚合在十进制半分界附近两个 ULP 内的机器噪声；显式 Decimal/字符串及实质低于边界的值保持精确。原始分数、资源值及平均分算法不改。
- 未启用 `interrupted_answer_delivery_profile` 时，兼容适配器直接保留原规则及已有修正，不读取该可选 Profile 专用的必需身份字段。显式启用时仍严格核验原有绑定，错误身份、合同或准入不放行。
- 私有 GT 目录也在写完子成员后恢复只读模式。新增回归同时核验文件字节与模式，延续“只改新副本”的边界。
- 与当前合同不一致的历史测试夹具已对齐：补齐 Profile 表达式的局部输入，使用当前核心版本，并分别验证数据集物化后的参考 SHA 和完全相同的规则逻辑。不修改题源、参考内容、Rubric 或权重来迎合测试。

历史 v4 来源回归仍严格覆盖当时物化的八项修复。后加的指标窗口 Profile 使用 `general-custom116-v1` 原始快照独立验证原生桥的显式启用、错 SHA 拒绝及真实候选表头行为。Info001 的任务说明对照仅放行独立参考补正所登记的三处 Q=56→57 文本，其余 Prompt、预期、Rubric 和评分公式继续逐字核对；参考补正自身另有 SHA、唯一匹配台账及分母回归。

## 发行版本与后续使用

| Skill | 同步后的版本 |
| --- | --- |
| prepare-general-e2e-workspaces | 0.3.5 |
| execute-general-e2e | 0.14.88 |
| collect-general-e2e | 0.11.59 |
| orchestrate-general-e2e | 0.11.84 |
| score-general-e2e | 0.10.107 |
| run-general-e2e | 0.7.24 |
| report-general-e2e | 0.8.51 |

`eval_general_e2e/stages.py` 与各 `skill-metadata.json` 同步。源码更新不会改变已冻结的 Skill ZIP；下一次评测必须从新提交构建、验证并安装新 suite，记录新的源码修订、catalog、Skill 内容和 ZIP SHA。不得覆盖仍被旧运行引用的安装目录。

在仓库根目录构建和验证新的发行：

```bash
python tools/e2e-build/build_general_release.py build \
  --repo-root . --output-dir /absolute/new-release-directory \
  --release-id general-e2e-framework-sync \
  --source-revision "$(git rev-parse HEAD)"
python tools/e2e-build/build_general_release.py verify \
  --release-root /absolute/new-release-directory
```

新执行继续核验模型、High、Workspace、原生进程及发送归属。准备失败时停止补位并观察在途任务；已受理或发送状态不确定的请求不得自动重发。采集复制失败须保留旧证据，仅在相同完成执行及严格来源校验下重做受影响的复制/采集阶段。

领导版使用具体的模型与客户端版本，不要求读者记忆控制轮次代号。总原生任务耗时、发送至观察终态的流程耗时、批次壁钟及 ES 模型耗时分别展示；未取得 ES 数据不能用任务耗时冒充模型推理时长。

## 回归与验证边界

源码测试采用 Python 3.11 和 Node 24。除了项目声明的依赖，完整开发回归需要 `jsonschema` 与 `lxml`；使用满足规则运行时锁的专用解释器，缺少的开发依赖放入独立测试环境，不安装进历史冻结运行时。

专用开发环境可安装 `tests/general_e2e/requirements-dev.txt`。涉及隔离 Worker 的测试会使用 `sys.executable -I`，因此 `openpyxl`、`lxml` 等实际规则依赖必须安装在该开发解释器的 site-packages 中，不能只靠父进程的 `PYTHONPATH` 补齐；冻结运行时继续只按原锁管理。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
  python -X utf8 -m unittest discover -s tests/general_e2e -t .
node --test tests/general_e2e/*.test.mjs
```

真实 XLSX 引用回归另需显式配置报告运行时；未配置时该项跳过，不能把跳过当作导出验证通过：

```bash
GENERAL_E2E_NODE=/absolute/node \
GENERAL_E2E_NODE_MODULES=/absolute/node_modules \
  python -m unittest tests.general_e2e.test_report_reference_export
```

本次核验 15 个评分核心、Worker、运行时锁与既有证据政策文件相对同步前仓库保持字节一致。实际客户端兼容证据沿用冻结生产记录；新源码通过合成回归、真实报告导出及新发行校验，不重新执行历史用例或改判旧分，也不把同 UID 的材料放置方式称为操作系统隔离。

本次完整 General 回归为 Python 825/825、Node 1120/1120；真实 Artifact Tool 的 XLSX 导出、重新导入与重算回归已实际运行。首次环境缺包和既有夹具失败的日志、改动前版本对照及修正后的完整日志留在控制侧审计目录，不将实际评测材料或开发环境写入源码发行。
