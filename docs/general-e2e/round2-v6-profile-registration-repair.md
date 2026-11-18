# round2的v6评分兼容登记

Office007的已完成独立裁判发现，8份受保护公开来源全部保持已审核的原始LF字节，转为CRLF后也精确命中原规则常量；但旧兼容入口只登记v3/v4/v5，v6未冻结既有Profile。原规则因此错误判断来源变化，并把该前提传播到工作流条件。这是评分输入身份适配故障，旧组件、查询和未评分证明原样保留。

Score0.10.114只将同一已审核contract/source及精确v6 dataset digest接入现有`release-protected-original-text-identities/v1`。只接受已登记的原始LF或原声明CRLF身份，任意内容差异仍拒绝；不改文件、数值算法、分母、权重或实际业务问题的判断。旧Manifest没有marker时仍按旧实现回放，修复从同一冻结执行的新评分attempt启用。

同次静态核查确认Office024的既有`sterilization-quote-complete-horizontal-fields/v3`也漏登记同一v6 digest。其contract/source与已审核版本相同，因此新准备启用完全相同的既有适配。当前该旧attempt尚在RULES_READY，无Worker、规则组件或裁判；通过精确准备故障证明保留旧输入，再独立准备，不伪造退出PID或已完成裁判。

Orchestrate0.11.91为两种原未评分状态分别保全证据。Office007须验证原生完整Prompt/模型/High/终态、原Worker、8份原字节及原阻断报告；Office024须证明上述已登记Profile缺失且从未启动评分。两者不产生能力分，最终只按明确基础设施修复范围选择新评分，保留全70题，不按高分择优。

针对精确身份、原值/公式保持、LF/CRLF原字节、任意内容修改、旧marker缺失回放、原生失败证明与无Worker准备故障运行合成回归。报价的真实EXW/CIP变化、金额/交期/有效期、安全公式和重大错误限分全部保持。
