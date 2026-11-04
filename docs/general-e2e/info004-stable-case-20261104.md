# Info004 稳定材料版单题修订

本次业务修改仅限Info004的题面、公开材料、参考答案和判据。
通用CLI、评分core、执行/评分Skill和评分协议均未修改。
沿用23个顶层检查点、2/98组预算及C13现有两个单元接口：R1、R2各2分，
分别明确核对作者作品绑定和给定观点范围，不新增四单元协议。

## 本题改动

- 新题名：鲁迅国民性批判的材料对照分析（稳定材料版）。
- 独立工作区：`workspace/general_e2e/01_Information_Search_Organization/task_004_luxun_national_character_source_comparison_stable_v1/`。
- 公开资料：M1/M2两篇留日文章，M3/M4两篇杂文或随感，M5后来回忆，R1/R2两项研究短摘录。
- 每份材料含原始URL、载体、获取日期、原响应SHA、精确节选SHA、段落编号及可采用年代精度。
- 参考答案逐项绑定84处材料/字段位置；所有必评研究命题均可在包内核对，不要求取得未给全文。
- 自动规则核验包及GT完整性、导出证据并检查引用入口；不联网判断史学观点。
- C13仅评价R1/R2；外部附注不替代必评材料或扩大核验分母。不同合理分析、简繁和意译均可接受。

正常材料包可完全离线完成。缺包、篡改或真实评测缺证保留异常/null，不能补零；
完整答复可证的未交付仍是业务失败。评分端导出的材料不算候选读取、产物或自验。

## 版本边界

只登记`general-info004-stable-v1`单题包，不发布整套70题新版本。
旧60题、116-v1、70-v2、70-v3的数据锁和能力映射不变；原Info004工作区保留。
旧版Info004题面通过原数据集的SHA快照重建，配套快照和数据集登记只用于保护历史与分发本题。
公开输入及题义已经改变，稳定版需新执行，不能把原AStudio/WorkBuddy回答套新标准重评分。
原AStudio Info004待核验及原WorkBuddy38分均保持原样。

## 使用与验收

CLI直接使用已有单题入口：

```bash
python eval/run_batch.py --task tasks/general_e2e/01_Information_Search_Organization/01_Information_Search_Organization_task_004_luxun_national_character_source_comparison.md --model <已配置模型>
```

使用新的输出目录/轮次。E2E沿用已有七阶段Skill，准备阶段选择本次单题dataset bundle；
不需要修改模型、Harness或升级评分core。

```bash
python tools/e2e-build/validate_info004_stable.py
python -m eval_general_e2e.datasets.bundle build --dataset general-info004-stable-v1
```

本题8项自检与静态门禁通过；现有受管规则Worker和独立裁判请求准备入口已用合成数据验证。
没有运行新的真实模型或语义裁判，没有重跑历史任务。
这些验证说明材料/契约可执行，不代表L3难度和模型区分度已完成真实样本校准。
来源与变更台账见`eval_general_e2e/datasets/audits/info004-stable-materials-20261104.json`。
