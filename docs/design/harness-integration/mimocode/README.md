# MiMoCode 集成依据

结论：MiMoCode 原生 CLI 提供三类 provider、JSON 事件及 SQLite 持久化，可作为独立 Docker Harness 集成。协议支持不代表所有网关与模型组合均兼容。

分析范围为配置/协议、可观测与存储，采用聚焦 overview，不是全仓架构报告。源码快照 `799e5052362d1067e8eb795528460023fbb3d07f`（main，clean）；运行验证使用 npm `@mimo-ai/cli@0.1.14`，不能假定两者逐字一致。

- [源码地图](源码地图.md)
- [协议与采集](协议与采集.md)
- [证据与待验证项](证据与待验证项.md)
- [分析清单](分析清单.json)

用户操作参见 [镜像说明](../../../../docker/mimocode/README.md)。源码分析推动了 SDK 选择、主会话/数据库分层采集和 token 口径修正；没有修改上游 Harness 源码。
