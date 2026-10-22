# Round6 证据与交付问题的通用修复

本次将生产中使用的新副本/补采流程归纳为通用源码能力，不修改 round6 或其他轮次的冻结 Skill、候选、评分、报告及交接包。测试只使用合成样例；真实日志回放和原件完整性验证保留在控制端审计中，不复制题目答案、GT 或用户日志到仓库。

## 问题与修复

| 触发条件 | 原问题 | 新行为 |
| --- | --- | --- |
| 原生 `tool_search_output` 使用 `tools` 而非 `output` | 完整返回被误记为缺失，导致不必要的未评分 | 解析并保留结构化工具定义，拒绝歧义/非法/失败形状，真正缺失仍 partial |
| AstronStudio v1 trace 声明 binding_evidence | 正式采集只复制 generic profile 的绑定文件；清单自洽但评分交接缺文件 | 两种 profile 都复制绑定文件；verify-only 检查实际归档的完整引用闭包 |
| 完整绑定 SDK 与客户端投影不同 | 临时兼容提案越来越依赖各投影形状 | 提供明确选择的 SDK 规范来源；原件和未对账差异独立保存，身份/消息/未知调用硬门禁保留 |
| SDK 消息紧邻 compaction 而冗余 UI mirror 缺失 | 重复镜像校验误拒绝完整原生消息 | 限定同 turn、显式 compaction 和时间窗口，保留原消息及 mirror-gap 审计 |
| submission 采用合法补采执行记录 | 研发索引强制与初始采集字节相同 | 索引采用包内、与 score SHA 绑定的实际记录，初始记录另外保留，不声明两者等价 |
| 完整任务范围中有 evaluation_error/unscored | 研发导出只接受 valid 并假定总有 score.json | 导出完整范围，区分 null 与真实零分；只读 VERIFY 同时支持目录和 ZIP |
| 宿主随后追加 XLSX 元数据 | 独立工作簿 SHA 与原回执不同 | 生成进程内可封存规范 ZIP；研发导出可用封存成员，独立变体保留，不改旧 SHA |
| 管理员仅导入完成的 return | 生产 init 还要求原批次所有历史制品 | 文档明确可用原身份直接 import-return/select-import，不删锁、不伪造阶段或评分包 |

输出后缀、edit 等仅客户端投影不同的情况由明确选定的 SDK 来源策略统一审计，不加入 task ID/call ID 特判，也不读取最终候选来补造执行历史。严格模式仍是默认；来源策略不是评分规则，也不自动授权重跑、补评分或修改已发布证据。

## 新发行身份

- collect-general-e2e：0.11.0
- report-general-e2e：0.8.10
- run-general-e2e：0.7.5
- general-resource-supplements：1.3.0

评分器、grading core、题目、GT、Rubric 和权重没有随这些修复改变。执行/评分编排的既有版本不因本次补丁重写。canonical shared source 和 collector 的脱仓 vendor 同步；独立 report 发行由构建器从同一 canonical source 装配。

旧冻结 ZIP 仍是旧发行，不能指望更新仓库就修改其内容。后续新评测从新提交重新构建、校验并冻结 Skill/release catalog，记录新的 SHA；禁止把新文件直接覆盖进旧生产目录或沿用旧发行哈希。

## 后续运行入口

在准备阶段明确选定 SDK 规范来源时：

```text
node collect-general-e2e/scripts/archive_astronstudio_trace.mjs --state-file ABS --source-policy bound-native-sdk
```

随后沿用同一归档的 trace-index 采集资源和正式收口，完成不可变 verify-only 后才交接评分。真实缺口继续保留，不跳过准入。

新报告可在生成命令中增加：

```text
--seal-output-dir ABS_NEW_ARCHIVE_DIRECTORY
```

此选项也适用于 selected_report.py。研发导出使用：

```text
python build_developer_bundle.py --workspace-root ABS --report-dir ABS --output-root ABS --canonical-report-archive ABS_SEALED_REPORT_ZIP
```

不提供规范 ZIP 时，独立 XLSX 漂移仍失败关闭。提供 ZIP 时仍严格核验原回执中的 JSON、工作簿、来源与选择索引 SHA，保留独立变体，不重新计算任务分数。

若独立 XLSX 在生成返回后已变化，登记报告回执时也可加 `--canonical-report-archive`。登记器要求 ZIP 内回执字节与待登记原回执完全一致，并核验全体成员与制品 SHA；run state 冻结该 ZIP，恢复时重验。它不为 collect 或评分阶段提供绕过入口。

## 回归边界

覆盖结构化/空工具列表、缺失/重复/非法结果、严格与 SDK 两种来源、未知调用/Prompt/最终回复冲突、绑定文件遗漏与 SHA/路径异常、初始/实际执行记录分离、有效零分/评测异常/未评分共存、封存成员篡改和宿主独立副本变化。独立 Skill 发行还需执行 build/verify；真实日志回放不调用被测客户端或裁判。
