---
name: run-general-e2e
description: 按用户明确选择的阶段串联 General E2E 准备、执行、证据、评分、回传和报告，并维护恢复状态；不替代各阶段 Skill 的判断与契约。
---

`0.7.7` 的七阶段链路同时支持 `general-custom60-v1`（旧 60 题、七维）与 `general-custom116-v1`（检索 20、Office 30、数据分析 66，独立五维）。管理员按 [数据集构建说明](../../../../../eval_general_e2e/datasets/README.md) 选择并构建 dataset bundle；独立安装后只消费冻结 ZIP，不依赖此源码链接。随后沿用相同的 prepare → execute → collect-evidence → score → package → import-return → report 流程；所有阶段保留 dataset ID/digest，不替换历史包或旧评分。


# 运行 General E2E 全流程

`0.7.6` 提供`prepare-imported-source --source-batch-root ABS --archive RETURN_ZIP --receipt PACKAGE_RECEIPT --output-root NEW_ROOT [--node ABS]`。它按原身份复制manifest/report-config、严格import/select并生成可移植source/task索引和只读JSON回放argv，不要求历史生产scoring ZIP，不初始化生产run state，不改制品锁或伪造完成状态。接收已有成绩时优先使用此入口；跨来源合并仍须逐条材料兼容与唯一报告单元映射，不能从旧Excel抄分或自动取交集。

经授权重评分的完整范围选择可由orchestrate的compose-rescore-selection生成，再通过本Skill的record-submission/package-return标准入口收口；保留旧submission、评分、回传和报告。该选择目录本身不含伪造的orchestration state。

`0.7.5` 的研发包保留完整报告选择范围，包括 valid、evaluation_error、unscored 和真实零分；未知分数保持 null，不为导出删题。支持实际评分采用的补采执行记录，保留原始回传成员和旧记录，不强制它与初始记录字节相同。

独立 XLSX 已被宿主追加属性时，`build_developer_bundle.py --canonical-report-archive ABS` 可从满足原回执的规范报告 ZIP 导出报告；独立副本作为变体保留，禁止改旧 SHA。规范 ZIP 可由 report `generate/selected_report.py --seal-output-dir ABS` 在生成进程内封存。该选项不放宽评分、来源包、JSON 或选择索引校验。

报告回执登记同样可显式使用 `record-receipt --root BATCH --stage report --receipt ABS --canonical-report-archive ABS`。必须逐字节匹配 ZIP 内的原回执并验证全部封存成员与回执制品 SHA；state 额外冻结该 ZIP 的路径/大小/SHA，恢复时继续核验。此参数只适用于报告，不替代 collect 回执或其他阶段验证；不提供时仍按原规则核验独立文件。

管理员只接收已有成绩时，可在新来源目录保留原 manifest/report-config，直接使用冻结 `import-return/select-import` 生成标准导入回执与选择索引，不必初始化原完整生产 run state。生产 init 会要求 manifest 中所有历史输入包存在；不能删 manifest 的制品锁、伪造评分包或手写完成状态来避开它。跨批次/同 unit_id 的比较仍需单独的派生报告映射，原身份不改。

`0.7.4` 的 prepare-score 新增 --keep-scoring-external：对 install-unit 安装的公开单元，将外置 scoring ZIP 的绝对路径和 SHA 绑定到 round 状态，不复制 ZIP 到 round-root。显式提供 --scoring-package ABS、--report-config ABS；后续调用仍须保留外置模式并重验路径/SHA。评分包实际在 round-root 内（含指向内部的链接）、已安装内部评分包或模式漂移均拒绝。默认缓存行为保持兼容。

此选项只是材料放置方式，不是 OS 隔离或停机屏障。原生分阶段评测必须先完成全部执行、正式采集/不可变校验和被测进程收尾，并保存屏障证明，再准备评分。外置目录在同 UID 下仍可能可读，按实际访问证据披露；prepare-score 不自动停止被测客户端，也不声称已拒绝私有读取。

```text
python -X utf8 /absolute/run-general-e2e/scripts/run_general_e2e.py prepare-score --round-root /absolute/round --harness AstronStudio --orchestration-id score-001 --scoring-package /external/private/scoring.zip --report-config /external/private/report-config.json --keep-scoring-external
```

报告登记后立即核验并封存规范 ZIP，保留原报告 receipt 和成员 SHA。若裸 XLSX 被宿主追加属性，保留变化字节与 OPC 成员差异，以封存 ZIP 内的原成员为字节权威；不得删宿主标记、改旧哈希或将重写文件冒充原件。研发打包可消费从规范 ZIP 安全重建并校验的报告目录；需要跨目录 workspace-root 时仅选择明确来源，不扫描整个用户目录。新增源码版本不替换已完成轮次的冻结 Skill 或规范交接包。

`0.7.3` 支持 execute-general-e2e 0.14.4 的原队列额度恢复；先读取该已安装 Skill 实际根目录的 `references/quota-recovery.md`。控制会话先生成未批准的授权草稿，只有取得人类“额度已恢复且授权重执行指定失败题”的直接指令后才填写确认及授权引用；保留旧 attempt 和完整现场，仅选择一个新 attempt 重执行该题。成功题不重跑、在途题不重发；后续恢复复用已持久化的一次授权，发送一经 armed 就只观察原生 turn。不得借恢复之名重评分、覆盖旧结果或执行已封存轮次。

`0.7.2` 的默认额度故障策略是暂停等待人工：发现原生额度耗尽，立即停止新任务/评分/打包，将当前阶段置为 NEEDS_HUMAN 并报告原生在途会话和恢复入口。不得自动转 UNSCORED 后继续，也不得计能力零分或自动重发。人工恢复额度后，还须明确授权恢复；已经终态失败的用例如需重测、建立新 attempt 或选择替代来源，单独保留授权与审计。历史轮次的一次排除授权不扩展为后续默认豁免。

正式语义评分统一使用独立项目中的独立单题聊天，通过标准 orchestrate-general-e2e 编排；不得由控制会话或协作子代理判分或作为会话失败后的替代。纯自动规则题仍使用受管 Worker。


## 默认工作空间布局

评测根目录未指定时使用控制 Harness 会话项目的当前工作目录；显式 `--round-root` 时采用用户路径。调用本 Skill 的绝对脚本路径，不 cd 到安装目录。新评测不创建顶层 rerun-execution-units、score-attempts、repair-control 等多套工作区。

收到单端 execution ZIP 后使用 `scripts/run_general_e2e.py install-unit --execution-package ABS`；完整冻结批次可用 `init-round --batch-root ABS`。两者均在评测根建立 Harness/execution/tasks 和 Harness/score/tasks，内部状态在 .general-e2e。已有输入 ZIP 和用户说明保留，冲突拒绝覆盖；单端安装无需提前收到私有评分包。

正式采集后运行 `prepare-score --harness AstronStudio --orchestration-id score-001 --scoring-package ABS --report-config ABS`，返回同一 Harness 内的编排根。新轮次评分必须交接标准轨迹、原始日志、trace-index、候选与私有标准，再按 orchestrate-general-e2e 推荐动作调度独立评分。历史失败证据例外显式保留。

修复留在对应单元/单题内，使用新 attempt 和显式选择，不自动重建整批。完成后的轮次可用 scripts/archive_round.py 的 import-final/verify/replay 迁移、校验和脱离旧目录复算，再按明确保留清单清理。

组合已实现的单阶段能力，支持单 Prompt 自动链路与人机协作交接，同时保持阶段级恢复和失败关闭。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --json
python -m eval_general_e2e check-layout
```

只执行用户明确选择且对应单阶段 Skill 已具备所需能力的阶段。当前 `0.7.3/operational` 已实现批次/单元两级状态恢复、冻结输入校验、标准回传打包、安全导入、幂等与冲突选择；支持资源覆盖不完整但身份和哈希有效的采集回执贯穿 unit flow，并按 submission 中的完整多级路径只打包目标评分 attempt。G4-03 已完成 AstronStudio macOS 五题执行、默认三槽评分、回传和同源报告闭环；QwenWork macOS 1.0.6 已完成单题 return/import/report 闭环。该状态不外推 Windows、其他 Harness、并发或 60 题全量。

新增 Harness 可按 [通用执行状态接口](references/adapter-execution-state.md) 接入 `record-execution`。该入口验证终态、业务身份、Workspace、原生会话证据与发送状态；公共 CB-B 首批接口已提供，新的 Harness 仍须完成原生采集和真实平台清理 hook 的接入验证，不因状态登记成功而宣称已具备生产准入。

## 已实现入口

最终选择已评分且报告生成后，可用`scripts/build_developer_bundle.py --workspace-root ABS --report-dir ABS --output-root ABS`生成研发数据包。默认读取报告目录中的逐题与来源索引；历史索引可通过`--source-index/--task-index`指定，独立资源补采可用`--resource-root`加入。按来源包和显式选择校验，不扫描整个控制目录；保留原件、相对符号链接、资源补充层及离线VERIFY。ZIP顶层名须与导出包名一致，既有包不覆盖。

先建立显式状态；`--input role=/absolute/file` 会冻结评分包、报告配置等外部输入，恢复时重算 SHA：

```bash
python scripts/run_general_e2e.py init \
  --scope unit --root /absolute/unit-root \
  --stage execute,collect-evidence,score,package \
  --input scoring-package=/absolute/unit-scoring.zip

python scripts/run_general_e2e.py resume --root /absolute/unit-root
```

阶段开始、人工接管或失败使用 `set-stage`；完成不能手工填写，必须用 `record-execution`、`record-receipt`、`record-submission`、`package-return` 或 `import-return` 记录通过身份、终态、契约与哈希校验的产物。详细命令和恢复边界见 [流程状态与离线回传](references/flow-and-return.md)。

单元评分完成后生成确定性回传包：

```bash
python scripts/run_general_e2e.py package-return \
  --unit-root /absolute/unit-root \
  --orchestration-root /absolute/orchestration-root \
  --output-dir /absolute/returns
```

collect receipt 的身份、任务范围、哈希和完整性仍是硬门禁；当客户端不暴露 Token 等资源字段时，合法的 `partial` receipt 也可进入回传，报告端必须保留缺失覆盖，不能补零。

管理员侧导入时会手工解析 ZIP，拒绝越界路径、重复成员、未知类型、哈希漂移和越界符号链接。相同 archive SHA 幂等；同一批次单元的不同内容分别保存在 `returns/<unit-id>/<package-id>/`，并清除当前选择。只有显式 `select-import` 后，冲突单元才能继续报告阶段。

## 阶段与责任

稳定主链路为：`prepare → execute → collect-evidence → score → package → import-return → report`。

- 冻结阶段选择、数据集、Harness、模型、裁判及推理配置；恢复时沿用原配置。
- 每阶段只消费上游有效回执，保留 `NOT_SELECTED / PENDING / RUNNING / NEEDS_HUMAN / NEEDS_ATTENTION / COMPLETED / FAILED` 状态。
- `collect-evidence` 采集执行证据；`import-return` 导入管理员回传，二者不能混称 collect。
- 支持人工执行或离线交接，但不补造自动化证据，不覆盖冲突 attempt。
- 组合器不重写单阶段规则；具体执行、取证、评分和报告由对应 Skill 负责。
- batch scope 只管理 `prepare / import-return / report`；unit scope 只管理 `execute / collect-evidence / score / package`，不能把两类根目录混用。
- 回传包只收录冻结 unit manifest、正式 receipts/evidence、完整 submission、执行记录和评分 attempt；排除评分 `runtime/` 副本、缓存和常见凭据文件。
