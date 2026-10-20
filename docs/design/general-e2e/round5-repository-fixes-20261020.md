# round5 原生评测问题的源码修复

本次更新用于后续轮次。round5 的冻结发行、60 题候选/执行/评分、原版失败、限定兼容副本、所有回执、规范报告和管理员交接 ZIP 保持原字节，不重跑、不重评分。不能用本次源码版本替换旧轮次发行身份。

## 已更新的源码

| 问题与直接原因 | 通用修复 | 保留的门禁 |
| --- | --- | --- |
| bash 的 SDK 参数 login=false 对应桌面 -c，但比较器固定要求 -lc | 按显式布尔值核对已知壳与完整命令；保留此前静态 rg 摘要比较 | 不执行 shell；命令、摘要、返回、退出码、耗时仍逐项核验；未知 shell/参数继续拒绝 |
| SDK 完整 acode_artifacts 名称和字符串返回，与桌面 dynamicToolCall 的短名/结构化返回不同 | 只对成功 publish 和失败 allocate 两个已验证 profile，比对原始 provider 行、namespace/tool/call ID/参数、终态、唯一 inputText、错误字段及耗时 | 不泛化去前缀，不改变 SDK 原文或 unknown 工具状态，失败 allocate 不伪装成功；缺原生行/歧义/漂移拒绝 |
| 工具显式 workdir 为同题子目录，但采集器只允许根 cwd | 仅 bash/exec_command 明确声明的规范绝对 workdir 可等于 Workspace 根或其内部子目录 | 未声明仍要求根；相对路径、点段、同名前缀越界、外部路径、两端 cwd 不同拒绝；离线词法比较不宣称阻止 symlink 或 OS 访问 |
| `_semantic_active_tasks` 每次按候选题序截取；前序 hybrid 规则完成后可挤出已有项目/线程，随后 record-wait/score 报 TASK_NOT_ACTIVE | 优先保留已有项目注册、线程、等待/超时、待验分及 API_RUNNING 的槽位，其余空槽按题序补位 | 不增配额，不创建替代线程；预留数超过容量失败关闭；原执行/评分内容不变 |
| `prepare-score` 默认将外置 scoring ZIP 复制到 round-root，与原生分阶段材料要求冲突 | 新增显式 --keep-scoring-external，通过绝对路径/SHA 绑定外置包，默认缓存模式兼容 | 实际路径在 round-root 内（含链接指向内部）、已内部缓存、路径/SHA 或存储模式漂移拒绝；不自动证明阶段屏障或 OS 隔离 |

`general-resource-supplements` 源码及 collect 的 vendor 副本同步。新版本：组件 1.2.9、collect 0.10.4、orchestrate 0.11.9、run 0.7.4；report 因分发该组件同步为 0.8.9，报告统计不变。评分器、数据集、GT、Rubric、权重和 Judge 协议不改。exec_command 命令投影仍要求已知 SDK 结果格式与精确可对账耗时；不能借本次改动放行未知结果或未对账时间。

## 操作问题与保留边界

- round5 自建采集控制器曾因查找 python3 而遗漏实际名为 Python 的旧进程，形成重复控制器。原审计没有证明 task12/13 收口失败的唯一因果；重复控制器与15秒等待预算同时存在。操作规程现要求单例锁、精确 PID/命令/子进程核验、只在安全边界替换控制器，再沿原 attempt 收口。标准 finalizer 的 --process-wait-ms 入口保留，不降低候选稳定性要求。
- 宿主 CWM 曾给裸 XLSX 追加属性，标准 SHA 校验据此拒绝是正确行为。规程要求保留原变化字节/OPC 差异、规范 ZIP 和旧 receipt；研发打包仅消费从已验证封存重建的原字节，不能剥离宿主属性或改旧哈希。
- Swift/SDK 匹配是本机注册器子进程环境问题；只允许使用经验证的 SDKROOT 和私有 module cache，不改全局 xcode-select，不把某台机器的 SDK 路径硬编码进通用 Skill。
- 已受理或不确定的发送不能自动重发。本轮 task058 的一次补点授权与 ledger 只适用于原轮次，不编成通用自动重发规则。
- 同 UID 下私有目录可读与控制服务残余通道如实保留。本次外置评分包选项不把目录分离宣称为 OS 隔离。

## 验证方式

使用合成 fixture 验证投影正例、篡改负例、原始 SDK 事件保持一致，以及 canonical/vendor 两条入口。编排测试覆盖前序 hybrid 完成后已有三槽不被挤出、槽位释放后补位和 API/超时/待验分状态。run 测试覆盖外置路径/SHA 绑定、内部或链接路径拒绝、模式漂移和默认缓存兼容。

另运行仓库的归档、资源、finalizer、run、发行、共享组件及 Skill 布局测试；打包仅生成临时合成验证产物，不覆盖 round5 原发行或交接包。最终通过数及保护原件 SHA 复验记录留在控制审计中。

2026-10-20 最终验证：80 项 Python 测试与 181 项 Node 测试通过，包含独立发行中的 collect/report 投影、run 外置参数和 orchestrate 槽位行为；子进程不依赖 checkout 或 PYTHONPATH。布局检查和 git diff --check 通过。旧 Docker 导入所需的 python-dotenv 1.0.1 仅下载为私有测试 wheel，经临时 PYTHONPATH 使用，没有安装/升级全局或被测环境。88 份原件（含60份原评分、原发行/输入、规范报告和管理员ZIP）按既有 SHA 复验一致。

问题依据来自 round5 的 `collector-runtime-application-manifest.json`、两份批准记录、采集修复提案/原版失败、`collector-control-incident.json`、原生评分控制记录及 `report-host-property-drift-audit.json`。提案文档标题保留“未应用”的原始撰写状态，实际应用以随后批准与逐题运行 SHA 清单为准。
