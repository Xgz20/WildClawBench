# WorkBuddy 原生目录与沙箱合成机制验证

2026-10-21 北京时间。全部源码修改与本地提交仅在 `.agents/memory-e2e`、`feat/memory-e2e`。
**合成机制探针通过，真实 WorkBuddy 隔离尚未准入；评测模型请求为0，正式20题未启动。**

AStudio 的七步链与生成开启条件下 A1→B1→A2 隔离复测均已收口，全部实例、记忆作业和执行服务关闭后，
才开始 WorkBuddy 的只读清点和合成原生服务试验。此前 AStudio 遗忘泄漏结论不改写。

## 当前安装与只读界面

- WorkBuddy 应用 **5.8.3 arm64**，ASAR
  `a7eff702411704d140d7d8d706fe9e711d9b13e304928481c9eba0af9c06f731`。
  内部沙箱目录版本为 **5.8.6**，不能将它作为应用版本。
- CLI `codebuddy-lite-wb.mjs` 实测9485334字节，SHA
  `9eacdcdaaf3d53877ca4eac53836a446770b9a40f5dc6382b43230c73fdc5448`。
- native sandbox-center / sandbox-cli 均为 arm64、hardened runtime；没有改签名、注入动态库或修改安装文件。
- 当前界面模型选择器为 `xopglm52`，权限为“允许完全访问”，可见当前任务已完成。
  此为正常实例的只读观察，不证明隔离实例复用了同账号；未归档日常任务内容。
- 当前9229无监听。旧 General 探针登记5.5.3/5.5.6，不能仅将5.8.3加入白名单冒充资源核验。

## 目录与认证的源码事实

桌面主进程原生支持 `WORKBUDDY_USER_DATA_DIR`、`WORKBUDDY_CONFIG_DIR`，并把解析结果写入
`CODEBUDDY_CONFIG_DIR`。产品配置支持 `ACC_PRODUCT_CONFIG_PATH` / inline配置入口。

CLI `PathUtils.getHomeDir()` 通过模块48912的 `resolveCliHomeDir()` 解析：
产品快照 `dataLayout.configDir.userDirName` 存在时优先于 `CODEBUDDY_CONFIG_DIR`。
因此只设置通用环境变量不能证明记忆根已隔离。源码模块在隔离 VM 的三项无文件读取验证通过：
无产品快照时遵循环境变量；有产品目录时覆盖环境变量；独立产品目录可以得到独立路径。
这是源码语义证据，不是应用运行态证明。

原生记忆文件、全局记忆、项目记忆和任务历史均存在基于该 home 的路径。
用户目录名 schema 要求隐藏名称、1—64字符，禁止路径分隔符、绝对路径和控制字符。
还有 `.codebuddy` 旧数据迁移及 `legacyReadFallback`，冷单元必须核对迁移/回退来源，不能复制整份用户数据。

认证与记忆分开：WorkBuddy主进程源码的共享 auth 目录位于
`Library/Application Support/CodeBuddyExtension/Data/Public/auth`，认证ID为 `workbuddy-desktop`。
本轮没有读取认证内容或改变登录；后续仍需验证最小认证复用及 UID 指纹一致性。

## 独立合成原生服务探针

探针 `tests/memory_e2e/probe_workbuddy_native_center.mjs` 仅接受
`synthetic_only=true`、`application_integration_allowed=false` 和合成 UID。
真实日常沙箱 socket 未连接，原生日常配置与记忆未修改，真实 Codex 记忆未读取。

从安装 CLI 精确提取并冻结 SDK模块34094/65649（Center）及84283/68331（执行器）；
使用原生协议、独立 Unix socket、独立 appHome、当前安装的原生二进制。
Center 在附加拒绝策略内运行。所有程序请求都为固定合成路径的 cat/touch，executionMode保持 sandbox。

| 试验 | 实际结果与判定 |
|---|---|
| 01 | 原生规则读取与 shutdown 成功；其余请求缺参数，保持协议探索结果 |
| 02 | `platform=macos` profile获取、规则设置、会话状态及正常关闭成功；`darwin`被明确拒绝 |
| 03 | 执行器继承外层策略时，连正控也返回71 / `sandbox_apply: Operation not permitted`；不是隔离通过 |
| 04 | 可信原生执行服务外置后正控恢复，但两个配置拒绝的合成目录仍被cat读到；原生规则回执不能作为OS拒绝证明 |
| 05 | 在原生 fetch_profile 响应追加拒绝片段后，正控成功、两个合成保护目录实际EPERM；缓存响应处理有错误，未准入 |
| 06 | 修复缓存绑定后，正控退出0；直接读两个保护目录、经符号链接读、向保护目录写共4项均实际EPERM，原生片段保留，4次缓存校验通过 |

06 的合成数据工作进程边界判定为 true，**application_admitted 仍为 false**。
profile原文片段保留，控制端仅追加拒绝，不增加授权；缓存只接受本连接已合成的同版本 profile。
Center及CLI均正常退出，保护文件内容不变。旧失败与可读反例均保留，未改写为成功。

## 后续未完成项

真实客户端的启动链尚未接入：须将后端直接文件IO、可信原生执行服务和数据工作进程分开绑定，
保证后台整理与所有执行入口保留原生沙箱，同时强制非目标拒绝。当前探针不能被当成生产代理使用。
还需完成产品快照/目录绑定、迁移回退验证、同账号认证复用、实际PID与socket身份、空闲收尾、
当前版本桌面UI/原生历史适配，之后才可冻结 GLM5.2（xopglm52）新批次并发送Prompt。

证据根目录：
`/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/workbuddy-admission-20261021-r1`。
主要原件：`installation.json`、`static-home-overrides.json`、`home-resolver-witness.json`、
`normal-ui-metadata-observation.json`、`native-sandbox-discovery-summary.json`，以及 `native-center-01` 至 `06` 的
spec/result/stdout/stderr。06额外保留探针自身源码、原生profile合成审计和缓存证明。

AStudio 完整 Rust 套件仍待用户确认；此处没有把合成机制成功、配置存在或UI空闲扩大为端到端准入。
