# 法律场景接入与实机验收

日期：2026-11-28。验证范围：30题全量静态校验、六类各1题真实执行和评分。

## 分支与来源

- 框架基线：`feature/astroncode-eval`，`a2217ad3603d115b8228da1a9db4db98ac45d973`，已与远端核对。
- 产品分支：`feat/zhehanhuang_legal-eval`，共同基线`54e01b2c`；仅移植法律评测集的`c93629cb`、`98a286b3`，保留作者信息。
- 新框架分支：`codex/legal-eval-adaptation-20261128`。移植提交`31650228`、`2790093c`；执行适配`cecc5e93`；报告及静态校验兼容修复`cc88ad09`。
- 平台基线：当前工作分支`feature/union-web`的`9ecfda9`，包含远端`440ad12`及本机已有6个工作提交。
- 新平台分支：`codex/legal-eval-adaptation-20261128`，适配提交`d227c5f`、报告准入修复`e8d6f5c`。

未修改30题正文、输入、GT、评分权重或v1冻结清单。冻结数据集`xiaofa-legal30-v1`，digest：`aef6b95c0d6b84a0bfbb3cd96f7cb6c412b5eda38b1ee1a8effcdab3340b9045`。

## 适配

用例库和批次选择保留`legal`场景。执行记录使用既有General任务契约，规则评分、独立语义裁判、GT后置隔离与原始轨迹校验沿用原流程。支持当前题库子集及冻结发布版本；直接选择错误场景的数据集或跨场景混选会在派发前拒绝。

维护中冻结发布清单和CI分发资产包含法律集。冻结版本详情与素材预览保留法律场景；素材接口拒绝读取GT。平台的执行模板和桌面评分能力按General契约校验，法律场景仍受模板模型、推理档位和场景开放策略约束。无头评分默认沿用General的Codex CLI配置。

报告0.10.9按冻结数据集身份、分类与任务SHA接纳分类目录式编号；冻结题面中的`information_retrieval`由已封存别名表规范为报告七维的`retrieval_verification`，原名称、别名Profile和原报告契约SHA均保留。此转换只用于报告分组，不重算检查点或总分。静态校验改为发现注册目录，覆盖法律集，即使题内报告元数据缺失也不会跳过；未知、重复或跨系列映射仍拒绝。校验同时补齐显式运行时输入路径及exec覆盖层/历史根目录的查找。

## 本地环境与检查

调试入口：`http://127.0.0.1:8083`。8080原服务保留，未停止或重配。

独立API端口18195、WCB端口18197、数据库`astudio_legal_20261128`、测试库`astudio_legal_20261128_test`、对象存储桶`legal-eval-20261128`。复用本机MySQL/MinIO进程和受保护凭据；仅复制用户、租户、模型和模板等配置，未复制或恢复原环境执行批次。

本机材料位于`~/EvalDebugWorkspace/legal-eval-20261128/`；启动脚本、服务PID及命令身份、日志、预检、批次和截图均独立保留。凭据文件不入库。

- 静态校验：30题，`--fail-on review`，PASS。
- 冻结分发包构建和独立verify：30题，PASS；ZIP SHA256：`5ead9be73e49e71965345b96372a779a26aa0ed25bd6a0980f14971e4eabee2c`。
- CLI冻结选题：30题，全部hybrid，冻结identity匹配。
- 框架相关测试：35项通过，覆盖法律场景、现有选题、冻结资产和公开执行协议。
- 平台相关测试：31项通过，覆盖法律能力策略、模板开放和评分配置。
- 平台报告相关测试：9项通过，包括法律场景的来源身份和聚合配置冻结。
- 报告元数据、视图及平台报告适配回归：42项通过。
- 静态校验回归：14项通过，包含法律目录、缺元数据、未知维度及输入路径覆盖层。
- 前端场景路由测试通过；TypeScript与Vite构建通过。
- 真实浏览器UI检查：法律冻结题库、30题完整选择、Codex评分表单和首题执行页通过，无页面脚本错误；截图保留于独立调试根目录。

## 实机身份与结果

首题批次：`platform-e2e-87d20e0b25ae489e9e868719255599ef`，本地平台ID 1。执行发行`cecc5e93`。

被测端：AStudio，`spark-x2.6/high`，模板`winarena-pc-20261121-a`，namespace `agentcube-windows`。模板绑定镜像digest：`sha256:d3125209f578425f764c20b1bb4f41cb8ebc2cfe16e3693fe0df38a279a95370`，发布的controller修订`c93463a1d2e6ba7b2696fb0c374c44a484fc5aba`。基础客户端发布值3.6.2.157，本次配置请求运行时升级至3.6.3；最终实际版本以采集回执为准。

首题会话`ad6f98c9-2b55-4191-a522-11a82e7834f8`于10:08:54发起创建，10:23:34返回；10:27:00运行时准备通过，10:27:09进入RUNNING。运行时回执证明由3.6.2升级至3.6.3，使用模板账号、模型目录账号匹配，未覆盖登录快照。只读核验实机controller/guest共59个Python文件的SHA256，与发布修订`c93463a1`全部一致，无缺失、额外或不同文件；Linux控制器Python为3.12.7。会话接口返回容器ID，但未暴露运行时imageID，因此镜像digest仅记录模板绑定值，不将其表述为独立运行时digest核验。

其余五题批次：`platform-e2e-07363d9ff629440f9e197ae7878f1c6f`，本地平台ID 2，执行并发3。两批使用同一数据集digest、执行发行、被测模型和裁判配置。

版本口径：WGUI的`AStudioUiDriver`默认`product_version`仍为静态标识`3.5.0.36`，会出现在原始diagnostics中；它不是本次安装后读取的客户端版本。本次实际客户端版本以`metadata/astudio-runtime.json`的安装前后版本和官方安装包SHA512核验为准，即3.6.3。原始字段保留，不改写历史回执。

裁判：Codex CLI 0.146.0，`gpt-6.1-sol/high`，评分镜像`astudio-e2e-scorer:general70-browser-verified-20261116`，镜像ID `sha256:b4996889f1f3bbaa6f0d9e8ea540f3cb68db5f01068bf3fa359c94851f9e6109`。执行与评分并发独立，原始分和评分审计分别保存。

六题最终执行和独立评分均已收口，六份标准评分及审计、裁判日志/原始轨迹、执行备份已逐一复算SHA。每题独立复验为PASS，所有执行沙箱与评分容器均已释放。

| 分类 | 任务ID | 最终执行版本 | 有效质量分（100分制） |
|---|---|---:|---:|
| 案卷整理 | 01_Legal_Intake_task_001_case_registration | 1 | 93 |
| 诉讼分析 | 02_Legal_Analysis_task_003_citation_verification | 1 | 91 |
| 文书生成 | 03_Legal_Drafting_task_004_batch_five_documents | 1 | 98 |
| 合同审查 | 04_Legal_Contracts_task_001_editable_comments | 1 | 100 |
| 电子取证 | 05_Legal_Evidence_task_004_qr_source | 2 | 100 |
| 法律交付 | 06_Legal_Delivery_task_001_court_download | 1 | 92 |

底层总分仍为0–1，表内仅乘100展示。此处为技术链路抽样验收与原Rubric质量分，法律严重错误复核与专家业务认证继续按原`METRICS.md`单独开展；未用六题推导全30题表现。

执行阶段已收口：六类最终执行均为COMPLETED，原生轨迹complete、备份verified、沙箱全部释放。共7次正式执行：二维码题首轮在`set_prompt`阶段回读失败，未进入`send_task`；原失败及封存证据保留为版本1。同题通过平台按原始输入、模型、档位和控制器新建沙箱重跑，版本2完成真实二维码解码和执行。没有改题、补造产物或把输入阶段失败计作能力零分。仅一次受控同题重跑；原输入异常的具体根因尚未确定，不声明已修复WGUI。

二维码失败会话上的额外只输入诊断未能重新附着AStudio窗口，未执行输入和发送，不计为正式用例执行。该诊断和失败截图单独保留，没有改写封存材料。原批次尚未启动的自动评分操作2先被取消；最终五题评分操作12绑定二维码v2及其他四题v1，保持Codex/gpt-6.1-sol/high、同一镜像、并发3。操作1和12均完成，六题有效、零评分异常、零待评分，原任务内容及原始成绩未改写。

报告操作13暴露旧编号/能力维度校验限制，其失败记录保留。修复后操作14复用操作12的五题原分，成功生成JSON、Markdown、HTML和Excel；四份文件均通过本地API下载并复算SHA，JSON逐题分数与封存评分一致。单独的案卷整理题由操作1及六题验收JSON记录，五题报告没有冒充全六题或全30题报告。

报告Skill0.10.9已独立打包，ZIP SHA256为`805c16ca108baa29ec57280477a29127f2f4c97550b90da1115abf3fb9e93f06`，包内包含能力别名原件及SHA绑定。全量验收索引为本机调试根的`acceptance.json`，包含每题attempt、执行版本、原分、标准评分/审计/日志/轨迹和备份SHA；报告证明为`legal-report-proof.json`，下载原件位于`report-verification/`。

本地后端在执行和评分全空闲后按PID、启动时间、命令及cwd核验身份，仅重启本任务的18197服务以激活平台修复`e8d6f5c`；8080仍由原进程提供。新报告读取器为`cc88ad09`，原执行/评分发行继续记录`cecc5e93`。

Edge控制台历史详情补充核对了二维码重跑会话`9f213421-4e75-4a84-9619-270516feeb5b`：创建11:00:37，销毁11:11:28，namespace及用户关联匹配。本次读取Pod详情超时后浏览器连接不可用，未取得运行时imageID；镜像digest核验范围仍为上文所述的模板绑定。

## 外部源码快照

只读记录，未修改、切换或部署外部仓库。WindowsAgentArena checkout HEAD `c4197adbc028a04f461bf0ba36bea2364a9606e2`，工作区干净；AgentCube HEAD `3cadd8e0dc1531a5cbf035f8239de4086673987f`，工作区干净；waa-agentcube HEAD `1fe92639f24d2a75e565693bce0686114b3c6f20`，仅原有未跟踪`.DS_Store`。本机HEAD与已发布模板/controller身份分开记录，不以源码HEAD代替实际运行版本。
