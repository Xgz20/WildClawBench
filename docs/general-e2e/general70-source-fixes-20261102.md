# 新通用70题源级修复交付（2026-11-02）

后续修订：新增8道Office规则同步、v3与历史兼容验证见[2026-11-04说明](general70-source-sync-20261104.md)。本文保留原v2交付记录。

修复范围严格为信息检索20题、Office30题、数据分析001—020，共70题。其他46题的题面、输入和GT保持原字节。没有修改模型或Harness实现，没有重新执行模型，没有覆盖原冻结评分和报告。

## 已实现的修改

| 范围 | 具体实现 |
| --- | --- |
| Info004题源 | 更新参考/判据修订说明、原两个固定单元的缺证规则和逐主张台账；保留23检查点、2/98组权重及原分档；不要求必须取得全文 |
| Info004参考材料 | 新增reference_sources.json及5份分级证据，区分实际短引文、审核概括、书目及不可核定部分；题内grade核验索引/文件SHA后导出到裁判证据目录，拒绝文件漂移及符号链接 |
| 直接评分规则 | 已验证的等价表头、日期/枚举表达、日报主表与附录关联、采购矩阵及条件公式、HR行号定位、报价表头、Office022渲染副本缺省距离、取证预算、唯一grade入口等直接落实到原任务Python代码 |
| 研究题答复边界 | 18题统一保留同一已完成用户回合的公开交付，后续纠错与矛盾均保留；不以最后收尾消息抹去正文，不择优选草稿，显式final仍取最终交付 |
| 两题GT校验清单 | Data002、Data003原清单记录CRLF摘要，而冻结文本实际为LF。只修正各一个摘要值；公开输入、标准答案业务数据和权重不变，原GT文件逐SHA归档 |
| CLI | 使用同一题源；新增结构化criterion状态、原分档校验、缺证null、零权重诊断分离和原最终总分封顶；修复未知总分回退取已知检查点均值的问题 |
| CLI批次 | `--dataset general-custom70-v2`显式选择70题，先核验manifest；使用独立输出命名空间，版本冲突在写日志/配置及派发模型前拒绝；记录dataset ID/digest及正确数据分析分类 |
| 静态校验器 | 修复exec覆盖层、中文/空格路径、XMind内部附件、Python Path除法、相对附件上下文及辅助函数grade入口误报；设计缺失输入有显式声明，不补造材料 |
| E2E发行 | Score0.10.52、Run0.7.12、grading-core0.2.1、independent-validity1.0.1；按新契约及源码SHA登记既有语义复核、独立有效性、原生渲染及只读输入兼容，不替换历史身份 |

累计36题有规则实现修复，另2题修正GT校验清单，共38个不同用例。70题均采用结构化缺证协议。完整逐题索引见[审查记录](../../eval_general_e2e/datasets/audits/general-custom70-v2-review.json)，逐步骤SHA和原回执见[源级修复谱系](../../eval_general_e2e/datasets/audits/general-custom70-v2-source-repairs.json)。

## 缺证的实际判分规则

- 可以用准确摘要或足够的相关段落核定具体主张；不强制下载论文全文。
- `supported`与`contradicted`必须有来源证据；`evaluator_reference_unavailable`不能记0或1。
- 两个原固定单元各自判断；有已证实的独立反例才使对应单元失败，无反例但证据不足则保持未知。未知不删项归一，不以额外正确来源抵消已证实错误。
- CLI与Codex/API Judge使用相同状态及台账校验。General E2E的台账引用必须包含在该criterion已查询的冻结证据中；记录与归档核验均检查。
- 候选内容正确性与其自述阅读范围分开。裁判访问失败不能证明候选未阅读；只有完整轨迹能证实独立的虚假核验声明时，才按原校准项归因，避免重复扣分。

杨联芬论文的两个具体观点归属尚未取得足够原文证据。新增材料明确标为不可核定，没有伪造全文或替候选改答案。原Info004继续待核验、总分null；原报告仍为69项有效、1项待核验，均分72.20，不补零。此次没有生成新的模型成绩。

## 版本与历史兼容

- 新修订集：`general-custom70-v2`；完整范围由独立定义和manifest冻结。
- 默认旧集仍是`general-custom60-v1`，digest为`e5fd1ed401b45729d85d7aaf9c94c36d3900c1bcb43446bb7d43cca584a2886c`，原七维映射不变。
- 历史`general-custom116-v1`的digest仍为`8a066c60dfb1b45403b5b792f9cd6264a5ee639e9cd263b8dc0acfc2031dcb01`。改动前题源、Info004原参考和两题原GT清单由SHA快照提供；旧bundle能按原锁重建，旧评分不承担新协议义务。
- 发布修订版不覆盖v1数据锁、独立Skill包、执行回执、评分、submission或报告。旧60题继续使用七维，新修订集使用独立五维，不折算、不混合版本均分。

源码、题面、输入和评分预算的版本登记由`tools/e2e-build/build_general70_revision.py`维护。默认只检查，显式`--write`才能更新新修订集；该工具拒绝旧集漂移和公开任务/输入/权重变化，不修改旧锁。

## 实际验证与边界

- 569项General E2E Python回归、110项CLI/legacy聚焦回归通过；另有当前源码、原生准入及旧政策35项聚焦检查通过。
- 70题静态校验PASS，0告警；所有题的CLI与Skill解析同一规则源码，唯一grade入口、分值预算及来源映射可校验。
- 20道数据分析题均用GT工作簿通过原始自动规则自检，规则组件均为1.0。自检只验证标准交付可被本题规则接收，不包括语义/过程评分，不代表模型得100，也不独立证明所有业务真值或指标设计合理。
- 当前新评分器对历史70项归档结果做只读核验：69项有效、1项待核验，0错误。原score SHA与源submission锁一致，没有导入新分数。
- 字节级原题/原输入、权重、旧60七维和历史116-v1锁均有回归；另外46题通过原manifest逐项SHA确认未改。
- 独立发行、bundle构建与脱离源码的准备验收入口及回执保存在`report-workspace/general-e2e/source-repair-20261102/`。这类验收不启动Harness或真实Judge。

不能用上述检查宣称全部70题的难度、区分度及每个业务真值都已多模型校准。没有新的模型/Harness实现修改；真实漏行、算错分母、错误窗口、未知值误处理、缺图和虚假核验仍按原判据保留，建议在模型/产品侧改进范围对账、未知值传播、来源追踪和交付自检，不以放宽评分掩盖。

## 使用与复现

```bash
python tools/e2e-build/build_general70_revision.py
python -m eval_general_e2e.datasets.bundle build --dataset general-custom70-v2
python eval/run_batch.py --dataset general-custom70-v2 --parallel 3 --model <已配置模型>
```

CLI新数据集输出位于`<OUTPUT_DIR>/<backend>/general-custom70-v2/`，不复用旧60题输出根。新E2E批次选择对应新bundle，沿用标准七阶段链路。评分环境缺原生Office能力、必要证据或明确的语义复核时应保留评测异常及恢复信息，不能用结构检查、占位0或猜测代替。

标准答案自动规则自检可复现：

```bash
python tools/e2e-build/check_general70_reference_outputs.py --probe-rule-review-paths --output-dir <新的自检目录>
```

本轮代码提交包括`29cd2c61`（题源/CLI/历史快照）、`67ca6a64`（更多源级规则与答复边界）、`c72afc7a`（两题GT清单）以及本文件所在的最终发行/验证提交。均为本地中文Conventional Commits，没有推送远端。
