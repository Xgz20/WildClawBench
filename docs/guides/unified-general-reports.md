# CLI / 端到端统一通用报告

公开入口 `eval/run_unified_report.py` 只读冻结材料，不执行候选、不调用裁判、不覆盖原分数。
平台可以混合选择 CLI 执行与评分组、AgentCube 通用执行的配置单元与评分记录，并显式选择轮次。
第一期仅支持已登记用例库中的通用场景，原报告入口保留。

## 来源和兼容性

- CLI：原执行 `scoring-input/task.json`、输入清单、`provenance.json`，以及所选评分组最终版本的原 `result.json`。
- 端到端：原 `batch.json`、冻结原题面、原执行素材、私有评分素材和绑定最终执行尝试的标准评分。
- 对齐已选来源的用例 ID、原始题面 SHA、解析后的 Prompt/Rubric/权重/声明以及原执行/私有评分材料指纹。
  题面相同但素材不同也会拒绝；不读取当前仓库题目补写历史。旧产物材料不全时说明原因，可继续使用原报告。
- 数据集 `digest` 是所选冻结题面、契约和素材的比较指纹，`identity_mode` 显式说明其范围；
  各来源的原用例库/发行/完整数据集摘要单独保留，不冒充原数据集发行摘要。
- 规范快照独立采用 `wildclawbench.unified-report-snapshot/v1`，不伪造 General E2E submission 或 return package。
  原回传包的正式验收继续由 `report-general-e2e` 及原契约执行。

## 口径

复用报告 Skill 的 `score_summary` / `grouped_score`，以及既有 `aggregate_case` 多轮算法：
每题先对有效轮次求均分，再对有效用例等权平均；有效零分保留，异常/未评分不补零。
比较对象独立计算成绩，不把不同模型、Harness 或裁判协议混成全局均分。
裁判配置与实际记录的协议分别披露，协议不同或缺失时提示为组合对照。

JSON、Markdown、HTML、XLSX 共用同一组 `presentation.tables`。
总览、分类、难度、逐题对比、分轮明细、评分配置、资源覆盖及来源索引保留轮次、执行/评分版本和原 SHA。
资源只读取已验证原执行中的显式字段；没有接入公共口径的资源或细分能力保持未知，不从总分或流程耗时推算。

## 命令

```bash
python eval/run_unified_report.py --describe
python eval/run_unified_report.py --spec source-spec.json --prepare-only --output source-snapshot.json
python eval/run_unified_report.py --snapshot source-snapshot.json --output /new/report-directory
```

输出：`report.json`、`report.md`、`report.html`、`report.xlsx`、`source-snapshot.json`、`report-manifest.json`。
原子发布新目录，来源快照或产物漂移时失败关闭。同一目录同一来源可幂等回读。
离线复算读取已校验快照，不再次读取失去访问权的原始材料；它不替代对原始证据的重新验收。
