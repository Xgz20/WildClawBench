# Info004 私有标准答案内置完整PDF

本次补齐的是参考证据的分发：上一版open-v2只在题源保留节选，完整原件随一次独立评分归档。
当前open-v3将同一原件直接纳入Info004的私有GT，使其他Harness及新批次评分不依赖旧attempt或用户Downloads目录。

## 标准参考文件

在`workspace/general_e2e/01_Information_Search_Organization/task_004_luxun_national_character_source_comparison/gt/`内：

- `reference_answer.md`：标准参考说明及包内原文入口。
- `reference_sources.json`：所有参考文件的SHA、角色与来源索引。
- `source_evidence/Y1-yang-lianfen.pdf`：原始10页PDF，699353字节，原SHA不变。
- `source_evidence/Y1-yang-lianfen.pages.txt`：15505字符的完整杨文分页文本，便于CLI和文本裁判直接读取。
- `source_evidence/Y1-yang-lianfen.json`：书目、段落定位、每页文本SHA、页码映射及文章边界。

PDF SHA256：`d42a5b5dd458469b160f57da3abfde3e27e194a2b107a1c2227b858cface0455`。
原PDF未裁剪或修改。分页文本保留杨文正文和全部续注；第10页上方另一篇文章被排除，
下方注31续文及注32—36保留。原文字层控制符保留并有说明，以PDF像素为准。

## 评分入口与隔离

原题内规则按`reference_sources.json`逐文件校验并原样导出至`evaluator_evidence/source_evidence/`。
现有CLI和E2E均已声明读取这一目录，不需要改评分核心或Skill协议。
CLI默认参考文件预算内可完整读取分页文本，不截掉中间段落；E2E可同时读取原PDF和分页文本。
PDF或文本缺失、损坏、SHA漂移属于评测异常，不是候选零分。

所有参考只进入私有scoring包，不进入任何被测Harness的execution包；
题面、Expected Behavior、执行素材、L3难度、检查点、权重和分档保持不变。
仍允许可靠替代来源；没有把杨文变成必选论文，也没有把裁判取得的原文计作候选已读。

新评测该题使用`general-info004-open-v3`，例如：

```bash
python -m eval_general_e2e.datasets.bundle build --dataset general-info004-open-v3
```

将生成的单题dataset包交给现有`prepare-general-e2e-workspaces`即可为不同Harness准备隔离包。
CLI直接使用当前题源时也会携带同一GT。旧冻结70题包、open-v1/v2包及历史结果不会自动升级或被改写；
后续批次需显式使用新参考版本，不能继续拿旧包并假定其中已有PDF。
本次不改整套70题定义或其他用例。

## 验证范围

43项聚焦回归通过，覆盖六份历史数据锁重建一致、原题输入/评分含义一致、私有参考隔离、
离线CLI全文无截断、PDF/文本缺失或篡改失败关闭。题目静态检查PASS。
四种Harness的验证只准备与核对包，不执行模型、不产生新分数。
既有AStudio87分及WorkBuddy38分、旧null和历史报告均保持原样。

实际使用独立分发的prepare Skill生成并验证AStudio、WorkBuddy、QwenWork、DoubaoWork四对包：
四份scoring ZIP均携带相同原PDF SHA与15505字符分页全文，四份execution ZIP均无该私有参考。
另用合成输入运行受管规则、语义请求准备及真实query-evidence读取：从冻结grader-evidence快照
完整返回863行、has_more=false、无截断，PDF SHA一致；未启动语义裁判、未生成score.json。
只读验证回执位于`report-workspace/general-e2e/info004-reference-bundle-20261105/`下
的`four-harness-portability.json`及`native-reader-portability.json`。

这次完整内置解决的是杨联芬论文的既知缺证路径；其他来源若确实缺证，原null、不补零规则继续适用。
