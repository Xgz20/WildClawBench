# M芯片Mac迁移与接续Prompt

> **2026-10-21 用户约束补充：评测必须基于安装的生产客户端，禁止修改/重编 ACode 源码或替换内核/执行服务。**
> 此前自编译路线已停用，不能作为生产包准入证据；见[边界纠正与恢复记录](AStudio生产包评测边界纠正与自编译入口停用-20261021.md)。

日期：2026-10-19。迁移分支：`feat/memory-e2e`。已有实现与验证记录基线：`1ca6c26`；本交接文档随同一分支发布。

建议将空闲Mac作为专用桌面执行机，保留登录、解锁和唤醒的GUI会话，在执行期间避免其他人或自动化操作桌面。它能减少日常操作带来的焦点争用；但旧机最后一次阻断发生时焦点检查已经通过，不能保证换机就解决表单提交后的应用层问题。新机需要重新准入，不直接恢复旧机的运行批次。

历史会话：[四Harness记忆评测集成](https://chatgpt.com/s/cx_6ad5d1c285bc81918c37d555760eefb6)。共享链接用于补充背景；访问失败时以仓库文档和可取得的原始证据继续，不把共享会话当作唯一状态来源。

## 拉取分支并建立worktree

本机远程配置已核实：

| 远程名 | 地址 |
|---|---|
| github | `https://github.com/Xgz20/WildClawBench.git` |
| gitee | `ssh://git@code.iflytek.com:30004/CYXH_Agent/AstronStudio-Eval/astroncode-eval.git` |

`gitee` 是现有企业Git远程名，实际域名是 `code.iflytek.com`。旧机的 `origin` 配置了两个push URL；本次分别指定github／gitee及精确分支，不推送其他分支、标签或改写远程历史。发布完成应核对两个远程分支SHA与本地HEAD一致，结果以实际推送回执为准。

以下命令适用于新建clone目录；父目录可按新机习惯选择，不能覆盖已有工程。新机须具备相应仓库访问权限，企业远程还需要可用的SSH鉴权与网络。

```bash
git clone -o github https://github.com/Xgz20/WildClawBench.git WildClawBench
cd WildClawBench
git remote add gitee ssh://git@code.iflytek.com:30004/CYXH_Agent/AstronStudio-Eval/astroncode-eval.git
git fetch github
git fetch gitee
git rev-parse github/feat/memory-e2e
git rev-parse gitee/feat/memory-e2e
mkdir -p .agents
git worktree add --track -b feat/memory-e2e .agents/memory-e2e github/feat/memory-e2e
cd .agents/memory-e2e
git merge-base --is-ancestor 1ca6c26 HEAD
git status --short --branch
```

两个远程SHA应一致；若只有GitHub可达，可以先从GitHub建立worktree并继续本地准备，将企业远程同步核验标为待办，不把它描述成双端已验证。已有clone先检查remote、分支、worktree与未提交内容；复用合适worktree，不重复使用 `-b` 创建已有分支，不用reset或强制覆盖。

在新Mac的Codex中打开clone主目录，新会话的代码修改、测试和本地提交全部在其 `.agents/memory-e2e` 内执行。后续若需另建分支，遵循 `feat/<描述>`，worktree仍放clone主目录的 `.agents/` 下。

## 新机先做的适配与准入

目前没有连接或操作这台M芯片Mac，也没有完成ARM真机验证。以下为从当前源码确认的迁移工作，不是已经实现的跨机器配置接口：

| 项目 | 当前源码事实 | 新机要求 |
|---|---|---|
| 用户目录和调试目录 | `activation.py`、`configuration.py`、`observation.py`、`recovery.py`、`batch.py`及多个native驱动写有 `/Users/gzx` | 按新机真实home与各客户端数据位置适配；不得伪造其他用户home或全仓字符串替换 |
| AStudio内核 | `activation.py` 与 `configuration.py` 直接选择 `acode-darwin-x64` | 查验安装包内实际二进制及架构，选择有效的arm64／universal入口，并保留版本、路径和回读证据 |
| Python | 部分native驱动默认 `/usr/local/bin/python3.11`，另支持 `MEMORY_E2E_PYTHON` | 使用实际Python 3.11+解释器；Apple Silicon的安装路径可能不同，不假设固定Homebrew前缀 |
| Node与依赖 | 原生驱动要求Node≥22；千问、豆包依赖锁定的playwright-core | 在新机安装依赖，不复制Intel的node_modules；核对Node实际架构 |
| 客户端与资源指纹 | 原生驱动校验版本、renderer源码指纹和存储身份 | 安装适用于新机的客户端；未知版本重新核验／适配，不仅加入白名单绕过门禁 |
| GUI与调试连接 | 固定loopback端口，需可用GUI会话和原生身份 | 核对实际监听进程、bundle、目录和系统权限；端口可达不等于记忆准入 |

默认端口来自 `eval_memory_e2e/__init__.py`：AStudio 9240、WorkBuddy 9229、QwenWork 9250、DoubaoWork 9260。按各端受支持启动方式开放本机调试端口，不将调试服务暴露到外网。若需要重启客户端，先检查原生任务空闲、确认没有接受未知的请求；不要为了配置调试口强制退出正在运行的任务。辅助功能／屏幕录制等系统授权若实际需要用户确认，再说明具体缺项。

基础依赖核验及安装示例，在新机worktree中执行：

```bash
uname -m
python3.11 --version
node -p 'process.version + " " + process.arch'
xcrun --find swift
export MEMORY_E2E_PYTHON="$(command -v python3.11)"
npm ci --prefix tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork
npm ci --prefix tools/report/skills/general-e2e/execute-general-e2e/drivers/doubaowork
```

缺少工具时先安装所需工具并复核版本。`playwright-core`用于连接真实客户端，不需要为此额外下载一个替代浏览器。上面的环境变量只覆盖当前源码中读取它的Python调用，不会修复其他硬编码路径或内核架构。

先完成离线检查，修复结果要分清旧基线与新机适配的影响：

```bash
python3.11 -m eval_memory_e2e validate-dataset
python3.11 -m unittest discover -s tests/memory_e2e -p 'test_*.py'
node --test tests/memory_e2e/*.test.mjs
```

在新机home下创建新的 `debug-workspace/e2e-evaluate/memory-e2e`，修复路径后生成新的scan、native-preflight和native-profiles，并将机器架构、账号指纹、模型、权限、版本和源码摘要冻结到新批次。启动／配置／扫描分别留证；预检不发Prompt。不要将这里的路径建议误当作当前CLI已有的任意目录覆盖参数。

优先在memory专用层实现机器配置解析，保持精确作用域、路径归属、Codex排除和恢复门禁。分支历史中已有General驱动与共享组件修复，不能声称整条分支与General/Web完全无关；可用 `git diff feature/astroncode-eval...HEAD` 核查当前参考分支的差异。若新适配确需修改共享代码，先明确影响面，完成对应General/Web针对性回归，不仅跑memory测试。

## 哪些状态随Git迁移

Git带走评测代码、用例、来源归属、测试与调研记录。旧机的debug证据、批次journal、运行时Profile、配置租约、账号数据库、认证信息、客户端安装包和真实记忆不随分支同步。仓库文档中的 `/Users/gzx/debug-workspace/...` 链接在新机可能不可访问，这是证据未复制，不能据此否定旧结果或补造文件。

新机可以不带旧证据先进行离线适配和新批次验收。需要继续研究旧机阻断时，再单独保留所需原件，放到私有历史归档目录，只读使用并校验SHA；不要修改旧manifest中的路径来强行恢复执行，也不要把私有配置备份、认证文件或整份用户数据目录提交到仓库。

新机使用四个客户端当前登录的账号；未登录时由用户完成登录，不复制旧机登录凭证。同账号的云端状态可能跨设备共享，新Mac不等于记忆冷启动。每个新批次必须新experiment ID／合成事实，并先验证C0；旧机在新机接管期间不再运行这组评测。真实账号的无关记忆不得清空。

## 可直接复制到新Codex会话的Prompt

```text
继续推进WildClawBench四Harness记忆评测集成与真机验证。这台M芯片Mac作为专用执行机，先完成迁移适配和重新准入，再执行新批次，不要只输出计划。

历史会话：https://chatgpt.com/s/cx_6ad5d1c285bc81918c37d555760eefb6
共享会话若无法访问，直接依据仓库文档和可取得的原件继续。不要尝试向旧会话发消息。

代码分支：feat/memory-e2e，GitHub和企业gitee远程都应有同名分支。先核验remote、HEAD、status及worktree；至少包含1ca6c26与本交接文档提交。复用clone主目录下的.agents/memory-e2e，所有修改与本地提交都在该worktree。不要在主checkout直接修改。新建worktree仍放项目根.agents/，新分支用feat/<描述>；commit使用type(scope): 中文说明，只提交相关修改。

先阅读：
1. docs/research/agent-memory/M芯片Mac迁移与接续Prompt-20261019.md
2. eval_memory_e2e/README.md
3. docs/research/agent-memory/记忆评测准入门禁与渠道分层实施-20261018.md，重点第8—14节。
4. docs/research/agent-memory/记忆评测优化实施与三个问题澄清-20261016.md
5. docs/research/agent-memory/四Harness客户端记忆支持与淘汰策略及评测重置调研-20261015.md

范围和约束：
- 被测仅AStudio（内部ID AstronStudio）、WorkBuddy、QwenWork、DoubaoWork。Codex仅作为控制端与调研参考，绝不操作其记忆配置、开关或数据；不能把它加入被测目标。
- 使用新机四端当前已登录账号。允许核验、切换并恢复被测端记忆配置，但须保存原值和恢复回执；仅处理精确合成事实，不清空日常账号记忆。
- 完整逐端串行，一个Harness完成全部计划并确认原生任务、相关后台作业和控制锁已收尾后再进入下一端。禁止跨端交替派发或模型请求重叠。
- 保持完整桌面UI发送链路。已发送或接受未知的旧操作仅可只读观察，不能重发、取消、改journal或换后端填成绩。新机创建新批次，不复用旧机Profile／session／operation／账号指纹。
- 调试产物放新机home下debug-workspace/e2e-evaluate/memory-e2e；正式分发另用report-workspace。私有原件、账号数据和配置备份不入Git。
- 配置可用、执行完成、记忆形成、行为结果、检索／文件残留和评分分开报告。异常保持evaluation_error／unscored，不能补为能力零分；没有内部事件就不能推导Recall@k。遗忘区分主动清理、访问频率淘汰、时间衰减，主动删除canary不能代表全部淘汰策略。

已知进度（旧机事实，新机须复核）：
- 正式混合20题位于tasks/memory-e2e/memory-mixed20-v1/manifest.json，有开源适配和自建场景，尚未启动正式四端评测。
- WorkBuddy与QwenWork各完成一条v3.1七步链；清理前回忆准确，遗忘后均泄漏旧值。WorkBuddy可见文件有残留；QwenWork可见Markdown已清除，但原生memory_search仍返回旧片段。都是未正式评分的单链观察，不是四端排名。
- AStudio 3.5.0记忆关闭的三步控制曾完成3/3。随后显式开启记忆的批次astudio-memory-canary-20261019-r1完成2/7：C0目标／保留项均未知；seed通过原生add_ad_hoc_note真实写入两事实并回读。第3步新会话before可信click／submit后未找到原生接受记录，后4步未发，渠道审核未导入，跨会话回忆和遗忘不可评。
- 上述AStudio未知操作为op-3b52a34413aa618e8018556f869b57c84a9b56c908d3dde75ed368b151b6937b，只能在原机证据上观察。焦点与RPC门禁当时通过，编辑器序列化与冻结Prompt完全一致，事后额度条件满足；具体应用层准入／派发分支仍未知，不预设根因。
- AStudio两份配置的受控字段已恢复、总开关回读false；未验证旧会话热加载，合成笔记未删。新机不得据此假定自己状态相同。
- DoubaoWork旧机安装版本2.32.12，新队列工具执行与结果上传采集尚未适配，仍不准入；新机必须重新查验安装／运行版本与资源源码。

请按顺序执行：
1. 做只读环境清点：arm64／Rosetta状态、Python 3.11+、Node>=22、Swift工具、客户端架构版本、GUI解锁、账号登录、模型权限、数据目录和loopback监听。检测实际缺项后处理，不预设用户名是gzx或Homebrew位于/usr/local。
2. 先修复memory执行层的迁移阻断：/Users/gzx硬编码、Python路径、acode-darwin-x64固定选择、真实客户端home和统一锁路径。优先集中解析真实路径，保留路径与身份门禁，禁止全仓替换或把ARM源码SHA直接加入白名单。若必须动General/Web共享代码，说明影响并跑相应针对性回归。
3. 在新机安装锁定依赖，跑memory数据校验及Python／Node测试。生成新的只读scan/preflight、配置往返回执和native Profile，不复制旧机的运行冻结物；所有输出用新目录。
4. 先用新批次验证AStudio三步基础控制，再执行v3.1七步canary：C0 before；M+ seed、before、forget、after、neutral、reappearance。before回忆与渠道审核门禁都通过后才能forget。若再次submit后无接受，补充同期应用层准入／派发证据，保留未知原操作，不反复点击重试。
5. 按完整逐端串行继续其余客户端；豆包先适配新版队列的执行、返回与上传证据。按证据记录遗忘结果，不人工改文件制造成功。四端执行准入和评分契约完成后，再启动正式混合20题及独立重复。
6. 持续追加实施记录，保留旧失败；分阶段本地提交。收尾报告给出新机环境、变更、实测分母、原件位置、配置恢复情况和下一阻断。可独立推进的工作继续做；需要实际登录或系统授权时才指出具体缺项。
```

新会话的首个交付应是新机环境清点和迁移适配结果。旧机上的Python93项、Node74项通过是历史验证，不能冒充新机测试结果，也不能代替ARM真机准入。
