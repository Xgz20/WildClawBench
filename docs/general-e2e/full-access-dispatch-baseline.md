# 正式评测的完全访问发送门禁

round3 Loomy的70题均回读为默认权限。原适配器只验证权限稳定，并将当前workspace值写成预期，因此没有实现统一全访问基线。该轮保留为默认权限历史观测，原评分、候选、原生证据及封存不改。

新正式入口共用desktop-gui/formal-permission.mjs，默认、询问、未知及含糊标签均拒绝。在所选workspace/project、发送意图前及实际发送处检查；Loomy探针新配置使用require-full-access，不能用工作区的默认值覆盖预期。现有客户端专属模型、完整路径、一次发送及原生身份门禁继续生效。

门禁覆盖原生macOS AStudio、Loomy、WorkBuddy、QwenWork、DoubaoWork。Windows/AgentCube拒绝default权限单元，WorkBuddy控制器必须明确支持权限字段传递；部署不支持时拒绝，不静默依赖旧默认。未修改外部WindowsAgentArena/AgentCube仓库或部署镜像。

旧Loomy preserve-workspace-policy证据仅按原条件回放，不追溯获得全访问资格。旧已发送观察保持只读；未知发送不重发。修复不自动启动客户端、改变现有轮次模式或重跑任务。

版本：Execute0.15.22、Collect0.12.30，Loomy组件0.1.16、desktop-gui1.0.1、DoubaoWork组件0.8.26；统一注册和vendored副本同步。Run元数据与统一注册对齐，同时保留此前合法空分及单数裁判观察目录导出修复。

验证包括所有客户端明确全访问允许、默认/未知拒绝、发送边界漂移零点击，以及旧默认权限回放不被重新标记。全部使用合成材料；实机完全访问评测必须另起独立完整执行attempt。
