# 已受理失败回合的原SDK前段

原生错误已核验、标准轨迹尚未收口而原SDK前段仍存在时，不能把该前段留在控制目录后按“完全无过程”评分。先准备同目录的输入清单及原SDK逐字节副本，再运行：

```text
python scripts/score_general_e2e.py register-execution-supplement --attempt-root ABS --source-manifest ABS
```

输入清单使用`schema_version=wildclawbench.native-execution-supplement-input/v1`，填写原执行`identity`（含原attempt_id）、当前冻结`execution_record_sha256`、`candidate_sha256`以及唯一`files`条目（`path`为清单目录内相对路径，`kind=native-sdk-prefix`，原`sha256`与`size`）。副本必须等于原件，保留原来源路径与最早留档SHA作为控制审计，不以重新生成日志代替原件。

入口只接受已按`evidence-accountability/v1`通过原生失败证明的评分attempt，核对原SDK唯一session_meta、同cwd/turn、唯一原Prompt、调用及返回归属；不要求终态，反而拒绝把已有完整终态的日志误作前段。文件冻结在`execution-supplement/`，原SDK以`raw_trace`纳入裁判目录，绑定清单以`rule_audit`索引。必须在`prepare-semantics`前登记；不得改已有语义索引、原始执行记录或候选。独立rescore会保留该证据及原清单来源摘要。

裁判必须通过`query-evidence`完整分页核对该SDK前段及绑定清单。它是原被测回合的行为证据，不是评分端生成的行为或GT。前段包含的实际调用、返回及说明可支持原检查点；未返回的调用不能推断成功，缺失尾段不能冒充完整未发生证明。不得推断未见的媒体或产物。评分仍按原Rubric、原权重和统一证据归属规则执行。
