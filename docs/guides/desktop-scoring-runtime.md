# Windows 桌面评分的通用规则运行时

AStudio 与 ChatGPT 的通用场景桌面评分复用冻结的 `score-general-e2e`。
桌面客户端使用的模型与规则 Worker 使用的 Python 是两个独立配置。
`scoring-runtime-lock.json` 当前要求 Python 3.11 虚拟环境，不能把 Windows
预装的 Python 3.12 直接传给 `--runtime-python`，也不能修改评分锁来绕过校验。
主、次版本不符或解释器不在虚拟环境中时，评分器返回 `RUNTIME_PYTHON_MISMATCH`。
这类错误属于评分环境异常，分数保持空值。

执行器在评分 Skill 准备时自动完成以下步骤，无需用户额外配置环境预处理方案：

安装器在来宾中以后台进程运行，以 PID 和启动时间绑定一次启动，并原子发布终态回执。
控制端只发送不超过 30 秒的启动/轮询请求，避免沙箱接口的同步命令时限中断冷启动；
恢复时复用原进程与回执，不重复启动。进程丢失、取消或总评分预算耗尽时停止并回收沙箱。
启动请求读取超时时保留来宾的独占启动标记，继续查询同一任务；不把未收到响应等同于
未启动，也不另起安装器。

1. 按固定 SHA-256 获取官方 PyPI 的 Windows x64 `uv 0.10.12` wheel，提取并再次校验
   `uv.exe`，不向系统 Python 安装包，不改系统 Python 版本。
2. 先准备并校验冻结的私有评分契约，再通过其自带 Grading Core 的静态依赖审计判断
   是否需要 Chromium。文本规则使用 `bootstrap-runtime --skip-browser`；有 Chromium
   依赖或无法确认时准备完整运行时，并执行对应版本、导入及浏览器启动探针。
   不把未安装浏览器的环境标记为浏览器就绪。依赖包沿用框架部署的清华 PyPI 镜像，
   仍核对冻结 requirements 中的哈希；配置仅放在私有 bootstrap 目录，不改用户或系统
   uv 配置。首次启动需要访问对应制品下载源。
3. 以评分锁摘要区分运行时目录，放在项目目录的同级 `.desktop-scoring-runtime/` 中。
   环境不会进入候选目录或评分导出包，沙箱释放时一并回收。
4. 对已有环境重新运行 `probe-runtime`，不以目录存在作为成功依据；状态不明或校验
   失败时停止，不自动覆盖或重做原规则 Worker。
5. 在 `desktop-scoring-tooling/installation.json` 的 `python` 与 `general_runtime`
   中记录已校验的解释器、版本、虚拟环境状态及评分锁摘要。规则评分和裁判后续调用
   `run-rules`、`prepare-rule-review`、`check-aggregation` 时使用该解释器。

Web 桌面评分继续使用原生浏览器和原有 Node 工具链，不安装这一套通用 Python 运行时。
本改动位于 AgentCube 桌面评分适配器，不改变本地 Codex、Docker CLI、API Judge 或
冻结评分 Skill 的契约与计分规则。

## 失败诊断

运行时安装或验证失败时，用例保持 `evaluation_error`，分数留空，评分 Agent 不派发。
控制端保存稳定错误码及 `scoring-runtime-steps.jsonl` 步骤回执，作为评分日志归档，
沙箱释放后仍可查看；原始 CLI 错误输出保留在来宾的私有诊断文件中，不直接投影任意
下载服务响应或代理配置到公开错误消息。网络、安装或依赖校验失败不能记作候选零分。

部署需要发布包含本适配器的框架制品。已失败的评分操作及原执行回执不修改；更新后
通过平台“重跑本轮评分”创建新的评分尝试，无需重跑原题执行。

## Windows 评分回传至 Linux / macOS

Windows ZIP 中的只读属性不能直接当作 POSIX 权限，通用解包也会为目录添加写权限。
桌面评分器在控制端导入副本中重新封存 `candidate-original/`，并按冻结 manifest 的
`private_scoring.workspace_entries` 恢复 GT 的精确权限，再调用原 Skill 的
`verify-score --archived`。导入前后核对全部文件内容摘要；不改候选、GT、分数、规则、
manifest 或评分审计，不取消只读校验，不让校验失败降级成有效评分。

`scoring-verification.json` 记录权限恢复审计、校验工具、退出码、稳定错误码和限长的
脱敏 stdout/stderr，通过评分日志入口预览或下载。错误提示同时提供稳定的具体原因；
超时与工具不可用也会留下回执。该接收逻辑由 AStudio / ChatGPT 桌面评分共用，不修改
原生 Codex 评分 Skill 或 Docker CLI 的评分逻辑。

执行器修复不会自动升级旧批次的冻结 Skill。特别是 `0.29.4` 的报销 BOM 问题，需按
[JSON BOM 兼容说明](general-json-bom.md) 使用新版评分 Skill；不能把回传校验通过
解释为已升级评分口径。
