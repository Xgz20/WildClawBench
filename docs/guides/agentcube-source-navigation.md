# AgentCube 端到端接入源码导航

本页维护评测工程与沙箱工程之间的源码职责和查阅顺序。本机绝对路径由各台机器的
`~/Tool/AStudioEval/context/source-map.md` 维护，不写入本页或业务代码。

源码路径可用不代表部署正在运行该版本。下列入口于 2026-11-17 在 Intel Mac 的
checkout 中核验；后续排查先检查实际文件、HEAD 和工作区状态，再与运行身份对应。

## 五个仓库的职责与入口

| 仓库 | 本轮排查职责 | 先读入口，路径相对各自仓库根 |
|---|---|---|
| astudio-eval-platform | 页面、租户鉴权、批次展示、进程管理、调用执行器及操作回执 | `wildclawbench/backend/app/core/e2e_adapter.py`、`wildclawbench/backend/app/core/e2e_engine.py`、`wildclawbench/backend/app/routers/e2e.py`、`eval-web/src/pages/wildclawbench/e2e/` |
| astudio-eval-framework（WildClawBench） | 公开脚本协议、选题和调度、AgentCube 调用、采集备份、恢复导出及评分/报告实现 | `eval/run_e2e.py`、`src/e2e/`、`schemas/e2e-api-v1/`、[公开协议说明](e2e-api-v1.md) |
| WindowsAgentArena | 沙箱控制层，wgui 请求契约、产品配置和操作、执行完成判定及轨迹采集 | `src/win-arena-container/wgui/controller/cli/main.py`、`src/win-arena-container/wgui/controller/contracts/models.py`；AStudio 配置导航另见其 `docs/astudio_model_configuration_flow.md` |
| AgentCube | 沙箱平台，会话与工作负载生命周期、认证、路由及调用通信 | `router_workloadmanager_api.md`、`cmd/workload-manager/`、`pkg/workloadmanager/`、`cmd/router/`、`pkg/router/`、`cmd/picod/`；`sdk-python/` 可辅助对照 |
| waa-agentcube | Windows 模板注册、namespace、固定镜像及注册台账 | `templates/README.md`、`templates/<模板名>.yaml`、`createWindowsCR_private_auth_a.py`、`template_record.py` |

当前框架的实际 AgentCube HTTP 调用先从 `src/e2e/agentcube.py` 追踪，
不要把 SDK 仓库的最新接口直接认作冻结执行器已使用的实现。

## 根据现象选择源码层

- 页面参数、409 错误、批次投影或日志展示：先看评测平台，再对照执行器的正式回执。
- 选题、参数、派发、恢复、文件或原生轨迹绑定：先看框架的公开协议和对应 backend。
- wgui 产品配置、菜单选择、发送及完成判定：从 WindowsAgentArena 的 CLI 和请求契约
  追到实际产品适配器；内部模块位置以该 checkout 为准，不猜固定目录。
- 会话创建、TTL、平台认证、路由、PicoD 或上传下载：看 AgentCube，并对照框架实际请求。
- 模板名、namespace、镜像 digest 与注册参数：先查 waa-agentcube 的模板台账；再用线上实例及事件核对当前状态。WindowsAgentArena 的镜像构建记录不等于 AgentCube 模板注册记录。台账中的 `waa_commit` 用于定位镜像内容，不能用本地最新 HEAD 替代。
- `Model service request failed`：区分沙箱访问凭据、产品登录/运行状态与模型服务连接。
  核对实际 RunRequest、产品适配器、原生日志及脱敏 HTTP 错误，不把 AgentCube Token
  当作模型 API Key，也不假设本机配置已经传入 Windows 或所有产品支持相同自定义连接。

本地 Skill 直接控制 macOS 客户端的任务先按其 Harness Driver 排查，只有证据指向
沙箱链路时才进入本页的 AgentCube/Windows 控制层。

## 本机路径地图

每台机器的 `source-map.md` 登记本机的五个 checkout 根目录、适用机器、核验日期和
调试工作根。可记录上次核验的分支与 HEAD，但它们只是快照；每次排查重新核对。
框架源码 checkout 与批次绑定的只读执行器发行分别记录，实际运行身份以配置和批次快照为准。

Intel 和公司 M 芯片 Mac 分别维护自己的同名文件。公司提供的路径不能在 Intel 上
当作有效目录，Intel 路径也不自动迁移成公司配置。机器路径文件留在本机，不入 Git。
其中不放 Token、API Key、登录快照或密码，不替代 `agentcube.env` 等受保护运行配置。

## 诊断证据与修改范围

先绑定 batch、task、unit/run/attempt、session/job 以及执行器发行，再收集原始错误。
同时记录 wgui/controller 版本、客户端版本、模板或镜像身份；外部 checkout 的 HEAD
不能单独证明远端镜像或共享服务正在运行哪段代码。

将静态源码分析、用户提供的信息和实机结果分开标注。为诊断获取源码位置不代表可以
自动拉取、切换、修改外部仓库或部署共享镜像。需要代码修改时，按当前用户授权确定
目标仓库并遵守其工作区规则。保留既有冻结输入与原始回执，不用重复派发替代证据检查。

本页只维护源码导航。接入契约、运行协议、版本化方案和验收记录继续由各自文档维护，
不在此复制一套滚动进度或覆盖历史结论。
