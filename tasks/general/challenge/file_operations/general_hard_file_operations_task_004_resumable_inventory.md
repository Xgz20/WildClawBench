---
id: general_hard_file_operations_task_004_resumable_inventory
name: 归档索引的中断恢复与幂等补齐
category: file_operations
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
dataset_report: {"category": "file_operations", "category_name": "文件与本地资源管理", "category_order": 3, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 归档索引的中断恢复与幂等补齐

## Prompt

请恢复受控中断后的归档副本与索引，核实真实内容并纠正检查点声明，避免重复登记或漏文件。主要交付是完整副本、索引和恢复报告，辅助入口用于实际重跑验收。

只读输入：/tmp_workspace/source_tree/有60份原创惰性源文件；/tmp_workspace/partial_archive/为受控中断副本（包含未登记、坏hash、孤儿等真实状态）；/tmp_workspace/manifest.tsv为部分登记；/tmp_workspace/state.json为中断检查点声明；/tmp_workspace/operation_contract.md公开幂等key、纠正规则、字段和入口限制。先完整读取契约，按源路径NFC key和原字节SHA核对全部对象，不从state或旧表自述猜已完成。输入状态保持不变，只在results创建结果。

三主交付均写/tmp_workspace/results：archive/（60个按key独立保留的原字节普通副本）；manifest.tsv（每source key恰一条有效verified记录）；recovery.json（初始中断逐文件纠正、检查点差异、最终核验和输入SHA）。字段、resolution枚举和初始/最终口径详见operation_contract.md。归档目标可以任意安全无碰撞archive/...路径，不能把同内容不同key合并；不能按原表越界路径打开文件。原partial孤儿只报告不导入，也不删除原件。

为验收“再运行同一入口状态不变”，另交results/resume_entry.json及其指向的自包含Python脚本。描述符api=h038-resume/v1、language=python、script为相对results的任意.py路径、args为可选固定字符串数组。实际命令为python -I -S <script> --workspace <隔离副本根> [args...]；不能写死当前宿主路径、依赖GT/网络/外部包。会实际在隔离副本调用：完整结果重复调用、仅保留辅助入口后从原中断状态恢复、结果副本再次损坏且索引重复后修复，再重复调用验证幂等。合法完整结果的归档路径-字节集合、规范化TSV记录及JSON事实须不变；JSON/TSV序列化等价可接受，日志与原字节前后SHA均独立保存。入口缺失/无效/只noop/重复追加/只补缺文件而不修坏hash都会失分，自述通过不能代替运行。若原交付本身不完整，原交付错误单独评分，重跑先核实际修复再核后续稳定，不重复处罚同一缺交。

入口执行限定本地Python标准库及契约列出的模块，Python审计钩子只允许该副本读取和results写入，禁止网络、子进程、ctypes、系统命令、链接和外部依赖；有限时及资源限制。这是本地Python受限执行验收，不冒称OS沙箱。所有程序仅在受管评分副本运行；缺可信probe/helper/通用派生证据环境是评测异常，不补能力0分。不要安装依赖。辅助脚本不改变非代码主交付定位。

UTF8/BOM、列/成员重排、Unicode NFC/NFD、SHA大小写及整数等价允许。TSV中文列键为幂等键/原路径/归档路径/内容哈希/字节数/状态；恢复JSON可用初始/文件/最终/输入哈希、处理结论/初始副本状态/初始索引行数/来源哈希/初始副本哈希、已核验数/唯一键数/归档文件数/完成/缺失键/损坏键，及来源数/初始已校验副本数/部分副本文件数/初始索引总行数/重复登记键/忽略登记行号/孤儿副本路径/检查点声明完成键/错误完成键/未声明已校验键/检查点声明完成数/恢复前实际完成数；枚举值沿用英文。missing的初始副本SHA用null而非0。可附稳定解释字段，不能以当前时间、重试次数或追加记录破坏幂等。

仅使用本题exec映射材料，不扫描真实用户目录，不读GT，不联网、不访问真实账号/服务、不发送消息或调用付费接口，不执行数据文件。全部新交付只在results，原60源、部分副本、旧索引和state只读。完成前核对源/副本/索引双向一致，并区分真实观察、声明与未知。

## Expected Behavior

核源/真实部分副本/部分索引/声明检查点，恢复60独立key并给可复核纠正报告；同一辅助恢复入口在受管隔离副本真实重跑保持幂等、修坏hash和重复登记。主交付非代码，L3预估。

## Grading Criteria

- [ ] `business_correctness`: 恢复未完成的归档副本与索引，检测已复制但未登记、已登记但校验失败两种状态，不重复登记也不漏文件。
- [ ] `boundary_cases`: 逐项识别并正确处理：仅续传缺文件；校验失败仍标完成；重跑重复追加。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': 'eb9a6da122eb8a05694db62e47e0efe3c6c8d10fc410feff03c7ef191b9e2aa4', 'trusted_files.json': 'ee01f33ce2e58fe86edeac5a60e0fa7bcd7b6ad0092ab9ef91f6d3ed3d452604'}.items():
        p = root / "gt" / name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H038_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    r = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {"business_correctness": r["business_correctness"], "boundary_cases": r["boundary_cases"],
            "delivery_integrity": r["delivery_integrity"], "evidence_binding": r["evidence_binding"],
            "overall_score": .55*r["business_correctness"] + .25*r["boundary_cases"] + .15*r["delivery_integrity"] + .05*r["evidence_binding"]}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/file_operations/general_hard_file_operations_task_004_resumable_inventory
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 纯automated .55/.25/.15/.05；不以辅助脚本名称、参考源码或输出语句评分。
- 源先行三类真实中断及额外冲突；Python oracle与Node仅公开输入实际字节/TSV/state复算，参考之前一致。
- 实际probe要通用规则派生证据环境，不加Office/HTML/runtime标签绕过。root负责必要通用框架适配、普通归档绑定与正式验收。
- 受限Python入口是行为验收辅助，非代码主交付；清环境、文件范围/禁网络/子进程/ctypes/Python审计、资源和超时，不冒称OS沙箱。
- 作者Host smoke不能宣称Worker；真实Worker验收与绑定SHA日志单独记录。无真实Harness/Judge/finalize，模型复核非人类专家，L3及区分度待实测。
- 原91输入只读，所有源/部分副本/SHA和目录allowlist交root核Git index；.bin保持真实格式，若忽略仅force-add预期fixture。
