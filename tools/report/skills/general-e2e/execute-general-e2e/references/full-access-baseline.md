# 正式General E2E完全访问基线

所有新正式派发均要求被测客户端使用完全访问。读取当前权限并保持不变，只能证明一致性，不能替代合规门禁。只读探针、历史观察及离线回放保留原始权限；它们不因此获得正式全访问合规资格。

| 客户端 | 明确允许的回读 | 正式发送门禁 |
| --- | --- | --- |
| AStudio | 完全访问 / full-access | 预期配置、选定workspace、发送意图前及物理点击前 |
| Loomy | 完全访问 | 新probe、选定workspace、原生AX发送动作 |
| WorkBuddy | full-access | 预期配置、选定workspace、发送意图前及物理点击前 |
| QwenWork | full-access（由明确UI标签归一） | 选定project、发送意图前及按钮调用前 |
| DoubaoWork | 全部允许 / 完全访问 | General入口、选定project、发送前及按钮调用边界 |
| Windows / AgentCube | RunRequest ui.permission=full access | 拒绝default单元；WorkBuddy必须支持显式权限字段并确证参数传到原生界面驱动，不可静默丢字段 |

共享门禁profile为general-e2e-full-access-required/v1。默认/询问/未知值、含糊或否定的全访问文字均失败关闭；新任务或workspace切换后必须重新回读。缺少客户端对应证据时不能默认已开启，也不能从已有文件读写成功推断完全访问。

门禁不代答业务澄清，不批准运行中未知权限，不修改模型映射或系统权限。公开UI设置模式须在用户授权范围内，随后重新probe/核验。此处是客户端权限模式，不等同于给宿主增加系统管理员权限。

历史已发送attempt只观察原请求，不因新的基线修改原件或重发。未发送的新派发必须通过当前门禁。权限条件变更影响全轮范围，正式新结果使用独立完整attempt，不选择性替换旧失败题。

Windows实际UI配置和回读由WGUI原生驱动执行；不支持明确权限传递的控制器会被拒绝。本次离线回归不冒充远端镜像或客户端实机验收。
