# Linux / Windows 工作区路径兼容验证

日期：2026-11-27。实现分支：`feat/cross-platform-workspace-paths-20261127`，基于 `68331c30`。

## 行为

- 基准题面仍维护 `/tmp_workspace`。CLI 映射到实际 Linux 工作区；Windows 沙箱映射到当前目录 `.`。General、Web、旧桌面入口和独立准备 Skill 使用相同的完整根目录匹配器。
- 中文紧邻根目录可正确处理，例如 `/tmp_workspace的材料`、`/tmp_workspace绝对路径`。`/tmp_workspace_backup`、`/tmp_workspace-backup`、`/tmp_workspace_eval`、URL 和嵌套目录中的同名段不会被误当作工作区根。
- 执行输入增加操作系统、工作目录和命令环境说明。Windows 明确使用 PowerShell / 本机 Python 3 等价命令；不假设存在 `bash` 或 `python3`。原题中的脚本示例和公开素材不作全局替换。
- Windows 公共准备流程建立并验证 `C:\tmp_workspace` Junction，目标为 `C:\ProgramData\WGUI\workspace\project`，不再依赖可选的 AStudio 安装器。AStudio、WorkBuddy、ChatGPT Desktop 共享此步骤。遇到已有的不相符目录/链接时停止，不覆盖。
- 派发前记录实际 Python 路径/版本及别名读写证明：`metadata/workspace-environment.json`。CLI 保存基准/实际 Prompt 哈希、映射和 `effective-prompt.md`。
- General 评分交接引用批次封存的实际 Prompt，并绑定映射、环境版本和公开上下文偏移；不根据交接时安装的准备工具重新生成执行输入。

## 冻结评分兼容

`wildclawbench.frozen-rule-path-aliases/v1` 对 11 份已审核私有校验器的路径字段解析函数提供兼容：将已知 Windows 工作区根按逻辑根解释。限定条件为选定工作区 `gt` 内的文件名、SHA256 和函数名；原始产物、冻结校验器字节、评分权重及业务规则均不修改。

Linux 原有字段原样进入原校验器。未知盘符/目录不转换，原有越界、来源前缀和普通文件检查继续执行。适配函数及调用计数进入评分回执；CLI 记录 `workspace-path-aliases.json`，独立评分记录 Worker `result.json` 中的 `workspace_path_aliases`。

新评分尝试显式冻结此兼容版本，Worker 请求必须与尝试记录一致。未声明此版本的历史评分尝试沿用原解析行为。未知或已变更源码不会套用这些适配函数。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 执行、准备、交接、符号链接、Prompt、Skill 布局回归 | 137 项通过 |
| Python 3.11 评分运行时与研究来源回归 | 39 项通过 |
| 276 题 Prompt 审计：回归 60 / 工作 116 / 挑战 60 / Web 40 | 无工作区根漏映射；挑战集原有 16 题中文紧邻问题已覆盖 |
| 通用回归 60 题整批准备 | 通过，保留 1 个符号链接用例，未派发 |
| 挑战集冻结 60 题静态校验 | 通过，0 问题；未改数据集源文件或锁 |
| 独立准备/评分 Skill ZIP 解包后，以 `python -I` 脱离源码目录运行 | 通过 |
| Linux 容器实际 CLI `_exec_container_grade` 入口 | 通过，`python:3.11-bookworm`；逻辑根和两种 Windows 根的字段等价，越界反例拒绝 |
| Windows 实机 `winarena-pc-20261125-a` | Python 3.12.10；Junction 准备、重复验证、读写和 H040 冻结解析器检查通过，校验器字节未改变 |

Skill 版本：`prepare-general-e2e-workspaces` 0.3.7、`prepare-web-e2e-workspaces` 4.4.2、`score-general-e2e` 0.29.8。详细验证回执见同目录 JSON。

Windows 首个检查会话 `681b8cd0-bdff-48cc-ae35-a63f51e9780f` 已释放并核验不存在。该次路径检查已通过；额外使用的 `capabilities` CLI 命令不受镜像支持，后续身份采集改用 `vm health`。第二个会话 `659a1860-971c-49bf-9a3b-e045c62f9a92` 的路径验证和健康检查均通过，已释放并核验不存在；实测协议为 `wgui.v2`，控制器 `/wgui/controller/cli/main.py` 的 SHA256 为 `72f60da243063b34df10ce966ec65cd585adb904d31dc880fd777bf190e70403`。本轮未读取实际 AIO 镜像 digest，不能据此把本机源码 HEAD 视为镜像版本。

## 范围与使用

新准备的批次带有环境说明及路径版本，已有批次的冻结 Prompt 不改写。重新评分是否使用兼容版本，以实际选用的评分发行和新尝试记录为准。

本轮没有启动正式用例执行、模型调用、登录态覆盖或服务部署，也未改模板、母盘或外部仓库。Windows 验证只使用自有短期检查会话，Linux 检查容器已删除。页面验收和正式评测由用户另行发起。

源码导航核验：WindowsAgentArena `c4197adbc028a04f461bf0ba36bea2364a9606e2`、AgentCube `3cadd8e0dc1531a5cbf035f8239de4086673987f` 均干净；waa-agentcube `1fe92639f24d2a75e565693bce0686114b3c6f20` 仅有既存未跟踪 `.DS_Store`。这些是本机源码身份，不代表沙箱实际控制器版本。本机台账未找到 `winarena-pc-20261125-a.yaml`；实际使用模板名由创建请求固定。
