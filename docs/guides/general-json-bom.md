# General 候选 JSON 的 UTF-8 BOM 兼容

UTF-8 BOM 是文件开头的 `EF BB BF` 三个字节。`utf-8` 文本解码保留这一标记，
随后交给严格 JSON 文本解析器时可能失败；`utf-8-sig` 在解码时识别文件开头的单个
UTF-8 BOM。Windows PowerShell 5.1 的 `-Encoding UTF8` 会生成 BOM，现代 PowerShell
的 UTF-8 默认行为不同，所以这类问题可能随客户端使用的写文件工具而出现。

参考：[Python 编码说明](https://docs.python.org/3/library/codecs.html#encodings.utf_8_sig)、
[PowerShell 编码说明](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-5.1)。

## 本次修复

`score-general-e2e 0.29.5` / `grading-core 0.16.1` 登记
`expense-policy-json-utf8-bom/v1`，只匹配报销政策题及已审核的原规则源码 SHA。
它将候选 `results/reimbursement.json` 的读取编码改为 `utf-8-sig`；题面、原始评分
契约、候选字节、GT、输入文件摘要、业务字段、金额容差与四个 25% 权重均保留。
源文件没有被重写，业务值内的 BOM 字符也不会被清洗。

新评分尝试通过既有共享源码修复机制冻结 Profile、原始及有效规则 SHA，输出
`rule-source-correction.json` 审计。本地桌面、AgentCube 桌面和 CLI 使用同一共享规则
修复。历史未启用该 Profile 的尝试仍保留原源码与原结果。

## 使用边界

- 必须使用包含此修复的新版评分 Skill；更新执行器不能让旧批次已冻结的 Skill 自动
  升级。新建批次可冻结新版；复用旧执行结果时，应显式选择新版评分 Skill 创建新的
  评分尝试，保留原评分及其工具链。当前 AgentCube 桌面重评仍从批次冻结包取 Skill，
  不能把“点击旧批次重评”当作自动升级入口；本轮未新增平台的 Skill 版本选择功能。
- 此次按精确源码只修复已确认的报销题。其它严格读取 JSON 的用例需要核对读取对象
  是候选、素材还是 GT，以及该题是否明确要求无 BOM / 字节一致，再登记相应兼容。
- `utf-8-sig` 不负责修复损坏 JSON、UTF-16、重复 BOM 或文件中间插入的标记。
  编码兼容不能补填业务字段或放宽数值与输入完整性校验。

2026-11-25 对当前 General 任务做语法初筛，排除中文题面副本与 invalid 标签，扫描
296 题，在 91 题、127 处发现显式 `utf-8` 文本读取 JSON 的写法。这里包含素材和 GT
读取，并非 91 道已确认故障；也未覆盖所有封装读取函数。详细清单位于
`report-workspace/eval-dataset/encoding-audit/20261125/report.{json,md}`。

本轮仅进行本地单测、打包与静态契约检查，实机验收由用户手动执行。
