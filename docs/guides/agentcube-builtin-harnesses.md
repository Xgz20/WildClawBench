# AgentCube 内置产品适配

执行产品与内置模型候选来自 WindowsAgentArena 控制层。更新默认候选后可用 `tools/e2e-build/publish_controller_capabilities.py --controller-root /path/to/WindowsAgentArena --output /new/path/capabilities.json --template <template>` 发布新的只含非敏感元数据的能力文件，再配置 `WCB_E2E_CAPABILITIES_FILE`；输出文件已存在时拒绝覆盖。

默认注册 AStudio 与 WorkBuddy 的 AgentCube 驱动。AStudio 模型候选来自默认模型 JSON，WorkBuddy 来自默认内置模型集合，记录源提交及摘要。也允许透传其他产品内置模型标识并在实际菜单与原生轨迹中验证；不接收自定义连接，不注册第三方模型，不静默回退 Auto。目录含版本兼容项，不意味着部署模板已验证该条目。

WorkBuddy 单元使用 `max_mode: true|false`，与 AStudio `reasoning_effort: none|high|max` 分开；框架先检查已部署控制层的请求字段，再下发开关。WorkBuddy 复用模板登录，AStudio 的运行时与登录注入只作用于 AStudio 驱动。

WorkBuddy 原件保留未裁剪项目 JSONL、控制层报告、诊断、终态 Workspace 和进程收口证明。新规范化器核对唯一原生会话/请求、Workspace、Prompt、原生模型、Max 配置、原生终态、调用配对，并基于 provider 原始 usage 对账；不可核验的用量不补零。评分材料复用标准 General Skill，通过独立归档重放验证。多个无法关联的新增原生会话保留原件并拒绝猜测或拼接。

`environment-status` 是公开 v1 只读命令。`--probe` 仅探测 DNS 与已发布健康端点，不创建沙箱、不调用模型；凭据配置通过不等于鉴权有效。AgentCube 当前的公开工作负载 API 没有模板内模型列表或实时配额接口，因此能力来源与实际部署、配置上限与云配额分别标记。

历史发行和既有批次不原地升级。先测试新发行，再将新建批次默认执行器指向新的不可变 checkout；旧批次与旧评分记录沿用原读取器。
