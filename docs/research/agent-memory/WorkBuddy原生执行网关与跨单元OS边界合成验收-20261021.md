# WorkBuddy 原生执行网关与跨单元 OS 边界合成验收

2026-10-21 北京时间。仅修改 `.agents/memory-e2e` / `feat/memory-e2e`。
**完整合成启动链通过；真实桌面实例未接入，应用准入仍为 false，模型请求0，正式20题未启动。**

此前策略片段与 OS 连接身份的验证见
[原生目录与沙箱合成机制](WorkBuddy原生目录与沙箱合成机制验证-20261021.md)。
本轮推进到安装版 Electron 后端、可信原生执行服务、真实原生数据工作进程的完整控制链，仍不将它描述成 GUI 七步链。

## 实现与边界

- `workbuddy-backend-spawn-guard.cjs` 只接管冻结的 `sandbox-cli` 启动，保持原生参数和环境，返回真实原生 PID，传回退出码与信号，无本地回退。
- `workbuddy-executor-gateway.mjs` 在附加文件策略外监督受信任的原生执行服务；控制请求必须来自已绑定后端的子进程，核对 OS PID/UID、父进程、启动身份、完整命令和源码/二进制摘要。
- 数据工作进程仍由安装版原生服务执行；公开 IPC 对 `RunExecutable` 强制要求原有 `executionMode=sandbox`，其他模式拒绝，不能经接口发起无原生沙箱的程序。
- 原生 `fetch_profile` 经过身份绑定代理，保留全部原生片段与原有 grants，追加不可移除的拒绝。空缓存绑定同连接、会话、平台与版本。
- 新增单元规则：禁止读取其他 debug 单元；除本单元 app-home/tmp 等冻结路径外禁止持久写入。控制 spec 的少量精确文件只读，不能扩展成整个控制目录可读。
- 后端直接文件 IO 应用同一单元边界。原生 Center 保持非目标读取拒绝与单元写入约束；仅 Center 自己的 socket 和两份协调锁有精确写入许可。数据工作进程明确拒绝接收该许可。

安装二进制、签名和原生策略开关未改动。不是在外层沙箱内再次套用原生执行器；受信任服务负责生成和应用完整原生策略，数据工作进程一次应用原生策略与追加拒绝。

## 真实合成试验及旧失败

所有试验使用合成 UID、合成目录、固定 cat/touch，无认证导入、无应用 Prompt、无模型请求。
同一实验目录不重解释，失败原件保留。

| 试验 | 结果 |
|---|---|
| gateway-01 | Electron 明确禁用外部应用传入的 NODE_OPTIONS，预加载未生效；后端在调用 ps 时 EPERM。失败发生在 SDK 连接前，无 RunExecutable。其独立原生服务经 PID/UID/目录核验后 SIGTERM 收尾，回执保留 |
| gateway-02 | 使用显式 `--require` 参数预加载守卫；完整服务启动/真实 PID/退出透传成功。后端直接拒绝保护目录；5个原生工作进程中正控成功、4项越界 EPERM；host 模式请求被拒绝。服务均退出0 |
| gateway-03/04 | 加入跨单元读限制和写入约束后，Center 退出0而未创建 socket。原生日志记录“同纪元已有实例，pid=None”；不是健康运行，也不是隔离通过 |
| center-lock-discovery-01 | 独立合成 Center 的实际 FD 暴露两份 `/private/tmp/workbuddy-sandbox-center-*.lock`；有非目标目录拒绝，尚未附加单元写入限制。正常 shutdown 退出0 |
| gateway-05 | 精确允许 Center 协调锁后，Center 启动并核对实际 FD 成功；Electron 后端因取证 stdio 方式在原生初始化阶段 SIGABRT，未进入 JS 探针，未产生模型请求 |
| gateway-06 | 改为真实桌面后端使用的匿名管道后，完整单元边界链通过；8个原生工作进程、4次后端直接 IO 检查、缓存/原生模式门禁、正常退出均完成 |

协调锁名实测为 FNV-1a 64 位分别绑定 IPC 字符串和 app-home。`centerCoordinationPaths` 生成精确路径；
启动后必须以实际 Center FD 复核。03/04 的同纪元提示是锁打开失败被归入重复实例路径，不能据此声称存在另一实例。
只给 socket 写权限的04仍失败，加入两份实际协调锁的05/06恢复启动，保留了这一反例。

Node 初始化问题也有同命令、同策略的对照：`node-boot-diagnosis-02` 中，安装版 Electron 执行同一合成 `-e` 脚本，
匿名管道退出0；将单元外控制文件直接作为 stdout/stderr 时返回 SIGABRT/-6。
修复探针的取证传输，保持文件策略原样；没有为兼容性放开单元外文件访问。

## gateway-06 的验收分母

后端直接 IO 共4项：本单元正控可读；保护目录读、旧单元读、单元外写共3项均 EPERM。

原生工作进程共8项：

- 本单元 cat 退出0、内容正确；本单元 touch 退出0、实际文件存在。
- 两个保护目录直接读、符号链接读、保护目录写、旧单元读、单元外写共6项均退出1 / Operation not permitted。
- 旧单元正控内容不变，单元外缓存文件未创建。UID 与前一完整合成单元保持一致，未以换 UID 或换事实代替访问隔离。

原生策略合成1次、缓存验证7次；另有1次非 sandbox 的 host 模式请求被网关拒绝，未转发执行。
Center两份锁 FD 与冻结推导完全一致，原生 CLI、后端、Center、网关均完成退出。

memory Node 回归 **98/98**；新增4项覆盖单元拒绝规则、路径逃逸、Center许可不得进入数据工作进程及实际锁路径见证。
Python 本轮未修改；前轮 **127/127** 记录仍保留，不声称重新跑过 Python 套件。

## 原件、配置与下一准入项

证据根目录：
`/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/workbuddy-admission-20261021-r1`。
各 gateway 子目录含冻结 spec、探针源码、stdout/stderr、原生日志、result、gateway-events 和后端结果。
汇总 `gateway-synthetic-close-audit.json` 记录失败与成功、所有已知服务/工作进程 PID 的结束检查及精确分母。
`node-boot-diagnosis-01/02`、`center-lock-discovery-01` 保留独立诊断原件。

普通 WorkBuddy 主进程仍为11296，未重启；没有修改普通实例配置、记忆或登录，没有读取 Codex 真实记忆。
旧 AStudio 和旧机接受未知的评测操作未重发。

真实应用仍待完成：

1. 覆盖当前安装版另一个 Editor SDK 启动形态（stderr pipe、安装目录 cwd）；当前网关遇到该形态会拒绝，不能直接启动正式 GUI 验证。
2. 绑定主进程实际后端与 Center 启动、原生 epoch socket、私有数据目录及写入边界，保留原生 fd3/4 目录传输和其他 stdio。
3. 确认普通客户端任务/后台空闲后正常退出，再启动独立单元；复核同账号、GLM5.2(xopglm52)、权限及当前5.8.3资源/API。旧 General 版本白名单不得直接放宽。
4. 通过 OS 准入后执行全新七步 UI canary 和 A1→B1→A2 实际记忆隔离，分开记录形成、行为、文件残留、后台状态和恢复。正式20题继续暂缓。

AStudio完整 Rust 套件仍待先前用户确认；本轮没有执行该套件，也没有修改 ACode 原仓库。

后续已接入真实签名桌面实例并完成实际后端/原生工作进程检查，还确认了 `custom-local:xopglm52`
对应当前 MaaS 自定义路由。账号、配置复用、启动观察失败和剩余门禁见
[真实桌面接入与MaaS模型复用](WorkBuddy真实桌面OS隔离接入与MaaS模型复用-20261021.md)。
本机七步链仍未派发，不将这些合成程序检查当成记忆准确率。
