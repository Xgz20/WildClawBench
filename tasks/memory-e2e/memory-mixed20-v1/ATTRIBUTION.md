# 来源与适配边界

本集包含14道 LongMemEval 作者发布的原题适配和6道明确标记的自建补充题。

LongMemEval: Di Wu, Hongwei Wang, Wenhao Yu, Yuwei Zhang, Kai-Wei Chang, Dong Yu. LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory, ICLR 2025.
https://github.com/xiaowu0162/LongMemEval
https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned

数据 revision: 98d7416c24c778c2fee6e6f3006e7a073259d48f。MIT许可全文见 LICENSE.LongMemEval.txt。

使用 oracle 文件的证据会话，保留原始问题、答案、角色文本和业务日期；增加档案作用域包装，转成桌面多会话输入。这降低了完整 S/M 长历史条件的检索负担，且固定选择了较短的历史，不能作为官方 LongMemEval 成绩或代表性抽样。

自建补充为 MEM-13/14/15/16/19/20：遗忘、隔离和可控工具经验，来源不得写成开源原题。所有难度标签均未经四端实测校准。
