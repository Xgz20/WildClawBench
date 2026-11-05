# 通用场景完整70题：v4参考证据发行

数据集：`general-custom70-v4`。基线：`general-custom70-v3`。
本次只将Info004已验证的完整参考纳入整套发行，其余69题的全部文件字节、模式、输入、GT和评分契约保持不变。
70题的题序、题面、执行输入、分值、权重和难度分布均不变。

## 完整发行内容

- `dataset/general-custom70-v4.dataset.zip`：完整70题数据集，含执行素材与私有标准答案，仅供管理员准备批次。
- `skill-suite/`：七阶段Skill ZIP、suite ZIP、catalog、schema及原生安装说明。
- `prepare-four-harness.example.json`：四端整套70题配置示例。
- `verification/unchanged-69.json`：逐题摘要与历史数据锁校验。
- `verification/four-harness-and-reader.json`：四端整套包及评分读取器验证回执。
- `distribution-manifest.json`、`SHA256SUMS`：完整分发文件与SHA校验。

Info004的私有GT包含同一原始10页PDF、15505字符分页全文、页码/文章边界和SHA索引。
PDF SHA256为`d42a5b5dd458469b160f57da3abfde3e27e194a2b107a1c2227b858cface0455`。
证据不依赖用户Downloads、旧attempt或外网，不进入被测Harness执行包。
开放检索、可靠替代来源和缺证保留null的评分含义不变。

## 准备后续四端整套评测

先解压完整发行ZIP。校验：

```bash
shasum -a 256 -c SHA256SUMS
```

从`skill-suite`中安装或解压`prepare-general-e2e-workspaces` Skill。
复制配置示例为新的批次配置，填写四端各自实际冻结的模型ID，并设置新的batch_id及输出目录。
示例中的`REPLACE_WITH_FROZEN_CURRENT_MODEL_ID`是占位值，不能用作真实评测模型身份。
题目清单已为四端分别列出完整同一组70题，不需手动拼接Info004单题包。

```bash
python <prepare-skill>/scripts/prepare_general_e2e_workspaces.py prepare \
  --dataset-bundle dataset/general-custom70-v4.dataset.zip \
  --release-suite skill-suite/general-e2e-suite-general70-v4-20261105.zip \
  --config <新的批次配置.json> \
  --output-dir <新的批次输出目录>
```

只把每端`__execution.zip`交给被测Harness；`__scoring.zip`仅交给评分端。
实际评测继续四端串行，各端执行并发3、评分并发3；当前发行验证不启动模型。
裁判默认`gpt-6.1-sol/high`，在新批次report-config中冻结。

评分使用本套Score0.10.69与Orchestrate0.11.54，按精确数据集/契约/源码身份延续v3的原读取和适配配置。
不要拿旧Skill去识别新数据集后依赖宽松兜底，也不要修改旧包的manifest或给旧attempt换GT。

## 兼容性与验证

新版本保留原四项取证文件通配符及其来源/契约校验，只新增v4身份；
其余69题在v3下实际启用的运行时配置和有效规则源码逐题对照一致，没有重新启用旧v1/v2中不适用于v3的适配。
CLI支持显式`general-custom70-v4`，并继续拒绝跨数据集复用历史输出目录。
旧60题、116-v1、70-v2/v3及已有单题版本的数据锁、发行包和历史执行/评分/报告保留。

发行脚本会用独立分发的prepare Skill准备四端各70题的执行/评分包，校验PDF一致且仅在私有包，
并以合成完成记录运行Info004受管规则与语义请求准备，从冻结证据快照读完863行全文。
这证明证据分发和评分入口兼容，不代表已重新执行280项任务或产生新的模型分数。

源码发布前的验证：通用E2E回归645项通过（以包根`-t .`发现测试，避免重复加载测试Runtime），
CLI及缺证评分回归32项通过，70题静态检查PASS、零问题。
所有69题的运行时配置及有效规则源码另有逐题对照测试；旧七份数据锁均可重建原摘要。

源码构建入口（要求相关发行源码已提交，目标目录不存在）：

```bash
python tools/e2e-build/build_general70_v4.py
python tools/e2e-build/build_general70_v4_distribution.py \
  --output-dir report-workspace/general-e2e/releases/general70-v4-complete-20261105
```
