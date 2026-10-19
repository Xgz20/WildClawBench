# AStudio OS级非目标记忆访问隔离验收

日期：2026-10-19，北京时间。分支为feat/memory-e2e，继续复用项目内.agents/memory-e2e worktree。实现提交为4c23f64a；不改主checkout，不推送远程。正式混合20题未启动。旧机接受未知的操作及上轮失败批次均未重发、未改写。

本轮原件根目录：[astudio-os-boundary-20261019-r1](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1)。政策中的真实非目标路径仅构造为字符串；合成验收不打开、枚举、stat或读写Codex真实记忆、配置及数据库，也未改变它们的权限。合成拒绝测试通过后，才创建新canary批次。

## 实现与覆盖范围

适配器为macos-seatbelt-astudio-backend/v1，额外的Seatbelt限制覆盖**安装包原有Node后端、ACode内核和这些进程派生的工具进程**。Chromium主UI、GPU、renderer与network进程继续使用产品原有沙箱，未使用--no-sandbox或--disable-gpu-sandbox；它们不属于此额外文件拒绝Profile的覆盖范围。本机制不宣称隔离整个macOS桌面、所有XPC/LaunchServices代理或其他应用，不把同UID目录分开视为OS隔离。

Profile通过file-read*／file-write*拒绝当前OS账号的非目标路径：整个.codex目录，以及WorkBuddy、QwenWork、DoubaoWork的已知本地根与Application Support目录。另覆盖/System/Volumes/Data路径形式；不解析这些真实数据目录。拒绝AppleEvents发送，限制后端改写评测器代码和租约控制文件。仍允许AStudio自身.acode、业务候选目录和正常网络调用。

启动器在AStudio应用入口暂停阶段安装一个范围精确的spawn包装：只有可执行文件为原AStudio、参数含原安装包server/dist/index.mjs且ELECTRON_RUN_AS_NODE=1的后端启动才改为sandbox-exec -f Profile 原命令 原参数。环境、stdio、IPC和内核入口保留。没有替换业务RPC、模型、提交处理器或原生记忆工具，也没有编辑／重签客户端安装包。临时主进程Node Inspector仅监听127.0.0.1:9271，完成bootstrap后关闭；评测CDP为127.0.0.1:9240。

内核检查使用sandbox_check查询**合成路径**的file-read-data、file-read-metadata、file-write-data、file-write-unlink策略，并要求同一后端／内核对允许目录的查询为允许。用主进程PID、启动时间、命令绑定应用实例，核验唯一受限后端及实际安装内核的进程后代。控制器在新Prompt INTENT之前检查，原生Driver入口再查，实际按下发送前再查并落原件。布尔标记、手填verified或声称的proof不能替代这些实时检查。

租约冻结机器、Python、内核、Profile、合成测试原件、启动器源码、编译桥接摘要与启动身份。受限后端的重启仍经过包装；PID／资源／政策漂移或出现未绑定执行根时拒绝下一次发送。既有操作继续只读观察，不因此授权重发。

Seatbelt SPI及系统工具依赖当前macOS实现，未知平台须重新执行准入；不是永久跨版本保证。[Apple子进程说明](https://developer.apple.com/documentation/Foundation/Process)和[WebKit/Apple的Sandbox SPI声明](https://github.com/WebKit/WebKit/blob/main/Source/WTF/wtf/spi/darwin/SandboxSPI.h)仅作为实现参考，本轮结论来自下面的实际测试，而非引用文档代替运行验收。

## 合成拒绝与正向对照

最终租约为[lease-r6](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/lease-r6/lease.json)。

合成目录测试覆盖10种拒绝操作：读取、枚举、stat、写现有文件、创建、删除、移出重命名、移入重命名、通过目录符号链接读取、向外建立硬链接。允许目录读取与创建均须成功；不存在文件的ENOENT不算拒绝通过，必须是EPERM/EACCES。保护文件和正向对照原件摘要在前后核对不变。

两条执行路径分别通过：sandbox-exec直接限制Python，以及安装包Electron RunAsNode进程通过原生桥接施加相同Profile后派生Python。每条路径有父探针14项（10拒绝＋2允许＋cat/find两个实际exec）、再派生子探针12项，共26项；两路径共52项实际文件操作检查。另有OS策略查询和控制器未受限制的正向对照，不与52项混计。真实非目标路径不用于这些访问尝试。见[合成验收原件](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/lease-r6/selftest.json)。

安装客户端实际启动后，后端PID75681与ACode PID75778均对上述合成保护路径的四项OS查询返回拒绝，对允许文件返回允许；不是把“查不到进程”或“无权限查询”当成拒绝。见[实际进程树回执](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/isolated-attest-r6.json)、[AStudio只读预检PASS](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/isolated-native-preflight/AstronStudio/probe.json)。

离线回归为[Python105项](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/python-final105.log)、[Node82项](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/node-final82.log)通过。Node测试另验证包装只作用于精确后端启动，renderer／其他命令原样委派、IPC和环境对象不改，源码漂移与错误执行模式在spawn前失败。

## 保留的启动失败及恢复

所有试验均发生在新模型Prompt之前，没有为修复启动而发送评测问题。

- 整应用外套Seatbelt的r2：Chromium GPU／network子进程二次初始化自己的沙箱失败，应用退出。未通过关闭Chromium沙箱规避；保留原stderr。
- r3的NODE_OPTIONS预加载方案：打包客户端忽略该选项，实际后端OS查询仍允许，正确拒绝准入；没有用“设置了环境变量”宣称生效。
- r4：在Node内部初始化之前require模块报testEnabled错误，bootstrap停止；仅对精确自有、尚无后端／Prompt的启动进程发SIGTERM并留证，不终止用户任务。
- r5：暂停时Runtime.evaluate等待Promise造成控制回执超时。随后只读发现包装已安装，实际后端／内核的合成OS查询为拒绝；没有再次安装同一包装。一次临时诊断按命令子串筛选过宽，连检查命令自身也列入，不能当作“所有AStudio进程”的证明。最终r6使用精确后代树和同步call-frame求值，完整取得安装回执。
- ARM64的sandbox_check是可变参数接口，最初未声明固定参数时正向对照也返回拒绝，未据此准入；修正固定参数ABI后，正控为允许、受限进程为拒绝。构建原生桥接时xcrun默认SDK27与当前linker不兼容，显式使用本机配置的SDK26.5，未修改全局Xcode设置。

最终入口：[安装回执](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/lease-r6/bootstrap-install.json)、[应用入口暂停位置](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/lease-r6/bootstrap-entry-pause.json)、[启动控制输出](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/isolated-launch-r6.stdout)。52项合成操作通过和实际进程政策通过分别保留，不互相代替。

## 新七步canary：执行7/7，遗忘后仍再现

批次astudio-os-boundary-canary-20261019-r1，新experiment ID与事实；继续冻结原v3.1七步契约、当前已登录账号、GLM-5.2／High／完全访问，开启AStudio两份配置的原生memory功能，提取／整理模型spark-x2.5。只有OS边界条件新增，不修改旧批次、旧回复或旧评分。

新experiment ID为e1a6b12fda9c4e2888ee278cb849678b，manifest SHA256为f9692e342b9ce7f03d547b3e5d305bba3d52cdcfa1f70f3fed77c9c8ca6d0fe3。C0回复新项目两项未知，但提到了旧合成档案，不把当前账号当成冷启动，也不清空日常记忆。

清理前回忆与源步骤渠道审核均通过后，才首次派发forget。**本轮seed实际采用通用write/read写入AStudio原生ad-hoc目录，没有调用专用add_ad_hoc_note。** 审核据此准入native_local_memory／agent_tool文件渠道，不升级为专用API调用、开关因果控制或自动形成证据。此前进度消息中的“原生工具保存”以此处完整原始轨迹核对为准。

| 步骤 | 实测 |
|---|---|
| C0 before | 当前合成项目两项未知，未提供学习事实 |
| M+ seed | 通用write创建一份笔记，read回读两事实 |
| M+ before | 新会话精确回忆2/2，门禁通过 |
| M+ forget | memories__add_ad_hoc_note追加较晚的撤销笔记，原条目仍在 |
| M+ after | target未知，keep正确，整份回复未泄漏目标 |
| M+ neutral | 回复19 × 23 = 437（带算式） |
| M+ reappearance | JSON再次直接给出目标旧值，keep正确 |

7个不同原生session／turn均完成，7次实际按下、7次可信click和7次可信submit，下一次发送意图均晚于前一步完成。7次登记Prompt意图前的OS检查、14份按下前OS检查全部通过；结束前再次实际OS检查仍PASS。完整解析7份冻结raw rollout，检查全部19次可见函数调用，未发现工具参数中的Codex等非目标路径访问；这不冒充所有内部文件系统调用的穷举审计。

两次相关的遗忘后查询中，目标不泄漏1/2、保留项正确2/2。forget之后的三次阶段快照中，原写入笔记和新撤销笔记这两个物理文件均含目标旧值，不能把6条观察记录算成6个不同文件。最后一次的memories__search（call_i9egy8poha7hifblwjo7j9ic）以及两次memories__read（call_wipyxkgguoasdb3h99b0ouyk、call_znbmzmll2x1be2wy6730zssx）均返回含旧值的片段；不是只凭最终回答猜测来源。

因此本轮确认的是**OS访问限制生效、UI执行链可用，同时追加撤销后的行为遗忘仍失败**。不将“追加撤销说明”当作物理删除成功，不声称OS隔离修复了AStudio自身的遗忘能力，也不把本轮相同的1/2比例与上轮拼成正式评分、排名或因果对比。两轮都保留UNSCORED，不运行正式20题或独立重复评分。旧存储仍可影响新轮，seed也重复了ERASE／KEEP“冲突优先级”的解释，这属于实际观察而非认可的业务语义。

原件：[完整逐步审计](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/canary-verified-audit.json)、[源步骤渠道审核](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/channel-review.json)、[UNSCORED报告](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/canary-reports/report.md)。审计校验94个按路径去重的journal原件，另校验14份按下前OS原件。上轮证据索引中的955份文件全部摘要不变，见[旧证据保护校验](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/old-evidence-preservation.json)；没有向旧操作追加重发或修改原journal。

## 配置、启动与收口

19:38:00已恢复配置租约：主配置按原字节恢复，overlay仅恢复受控记忆字段，保留客户端其他并发变化；随后两home安装内核回读memories=false。后台最新可见记录为stage1 done4／error5、global pending1、running0。pending行仍保留旧worker及旧开始／完成时间，无租约，不将它计作一次新模型请求；没有取消或改写此行，也不宣称所有后台周期已结束。见[独立恢复核对](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/restore-independent-check.json)。

确认263个历史原生session中阻断数0、后台running0后，从原生菜单正常退出测试实例并普通启动。19:47:34复核：9240／9271均关闭，启动命令恢复为原AStudio可执行文件；所有受控记忆字段仍与本轮原始备份一致，总开关false。客户端启动改写的其他字节保留，没有强行回写整文件SHA。旧隔离租约因原PID已退出而被实际拒绝，错误为BOUNDARY_PROCESS_REPLACED，不能把普通启动当作仍处于本次额外Seatbelt限制下。

普通启动恢复原件：[normal-restoration-verified.json](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/normal-restoration-verified.json)。测试隔离是按实例租约启用，非永久修改应用或全局OS权限；下一次执行需重新selftest／launch／attest并冻结新Profile。没有用恢复验证Prompt新增模型请求，没有人工删除候选便笺或清空日常记忆来制造成功。原始撤销笔记和旧值残留均保留。

当前已完成本机AStudio记忆执行链直接文件访问隔离的准入与一轮七步UI canary。没有完成整机／所有代理隔离、其他三端OS适配、物理清除、真实周期后无再现、访问频率／时间衰减或正式20题能力验收。

最终[恢复后原生空闲核验](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/final-native-idle-after-restoration.json)为263个历史session、0个阻断；普通启动UI、编辑器可见且发送按钮禁用。完整[证据索引](/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/astudio-os-boundary-20261019-r1/evidence-index-final.json)保存本轮原件摘要。仓库只提交实现、测试和说明，配置原件、账号信息、编译物和运行轨迹不入Git。
