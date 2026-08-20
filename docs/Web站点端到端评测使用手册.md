# Web 站点端到端评测使用手册

本文面向参与人工评测的测试人员，说明如何在 Harness 桌面客户端逐题执行 Web 站点任务、准备评分工作空间、在评分智能体中逐题评分并打包回传。整个流程不调用 WildClawBench 的执行或评分链路。

文中的 `<batch_id>`、`<harness>` 和 `<task_id>` 需要替换为实际目录名。例如：

```text
<batch_id>  = web-e2e-20260820-105921
<harness>   = codex
<task_id>   = 07_Website_Generation_task_002_focus_pomodoro_clock
```

## 1. 领取文件

每个 Harness 对应两个任务包，整个批次另有一个评分 Skill 包：

| 文件 | 使用阶段 | 用途 |
| --- | --- | --- |
| `<batch_id>__<harness>__execution.zip` | 执行 | 包含 Prompt、初始 Workspace、执行清单和评分工作空间准备工具 |
| `<batch_id>__<harness>__scoring.zip` | 评分准备 | 向评分副本中增加私有评分契约和评分素材 |
| `<batch_id>__score-web-e2e-skill.zip` | 评分 | 导入评分智能体，每台评分客户端安装一次 |

不要把 scoring ZIP 当作评分 Skill 导入，也不要把评分 Skill ZIP 解压到某个用例目录。

### execution ZIP 解压后的结构

```text
<harness-package-root>/
├── manifest.json
├── 执行清单.md
├── execution/
│   └── tasks/
│       └── <task_id>/
│           ├── PROMPT.md
│           └── workspace/
├── score/                              # 评分准备前必须为空
├── tools/
│   └── prepare_scoring_workspace.py
├── 准备评分工作空间.command            # macOS Shell 入口
└── 准备评分工作空间.cmd                # Windows 入口
```

默认不生成 `execution_record.json`，测试人员也不需要创建或编辑 `task_manifest.json`。

## 2. 执行 Web 站点任务

### 2.1 每题创建独立工作空间和会话

每个用例分别操作。以 Codex 包中的 002 题为例：

```text
web-e2e-20260820-105921__codex/
└── execution/tasks/
    └── 07_Website_Generation_task_002_focus_pomodoro_clock/
```

macOS 工作空间路径示例：

```text
/Users/tester/WebE2E/web-e2e-20260820-105921__codex/execution/tasks/07_Website_Generation_task_002_focus_pomodoro_clock
```

Windows 工作空间路径示例：

```text
D:\WebE2E\web-e2e-20260820-105921__codex\execution\tasks\07_Website_Generation_task_002_focus_pomodoro_clock
```

在被评 Harness 桌面客户端中：

1. 新建项目或工作空间。
2. 选择 `execution/tasks/<task_id>/`，不要选择其中的 `workspace/`，也不要选择整个 Harness 根目录。
3. 为该题新建一个会话。
4. 在会话中输入对 `PROMPT.md` 的引用并执行。

推荐输入：

```text
@PROMPT.md
```

也可以输入更明确的指令：

```text
请严格执行 @PROMPT.md 中的任务要求，所有产物写入 ./workspace。
```

如果当前 Harness 不支持 `@文件名` 引用，打开当前目录唯一的 `PROMPT.md`，复制其完整内容发送给 Harness。

### 2.2 执行时的目录要求

- Harness 只能在当前题目的 `workspace/` 中创建或修改站点产物。
- 不要修改 `PROMPT.md`，不要把其他题目的文件复制进来。
- 不要把真实账号、API Key、Cookie、私钥或生产数据写入 Workspace。
- 一个工作空间和一个会话只执行一个用例。完成后关闭当前会话，再处理下一题。

### 2.3 单题执行完成检查

在当前题目目录确认：

```text
<task_id>/
├── PROMPT.md
└── workspace/
    ├── package.json
    └── ...站点源文件
```

至少确认：

- `workspace/package.json` 存在；
- Harness 的最终回复没有报告未处理的执行错误；
- 站点源文件位于 `workspace/`，没有写到题目目录或其他用例目录；
- 未删除初始 Workspace 中的必要素材。

### 2.4 全部执行完成后备份

完成全部用例后，在准备评分前压缩整个 `<harness-package-root>/`，将备份 ZIP 移到该根目录外。评分只在后续生成的 `score/tasks/` 副本中进行，不能直接污染 `execution/tasks/`。

macOS Finder 示例：选中 `<harness-package-root>`，右键选择“压缩”。

Windows 文件资源管理器示例：选中 `<harness-package-root>`，右键选择“压缩为 ZIP 文件”或“发送到 → 压缩文件夹”。

## 3. 准备评分工作空间

准备评分前应满足：

```text
<harness-package-root>/
├── manifest.json
├── execution/tasks/                    # 已完成的候选产物
├── score/                              # 必须为空
└── <batch_id>__<harness>__scoring.zip # 放在 manifest.json 同级
```

若 `score/` 已有评分结果，不要清空或覆盖；先停止操作并确认是否已经执行过评分准备。

### 3.1 macOS 推荐操作

macOS 下载的 `.command` 可能被 Gatekeeper 阻止双击。推荐从 Terminal 通过 `bash` 调用，它不要求对脚本做开发者签名。

假设 Harness 根目录为：

```text
/Users/tester/WebE2E/web-e2e-20260820-105921__codex
```

执行：

```bash
cd "/Users/tester/WebE2E/web-e2e-20260820-105921__codex"
bash "./准备评分工作空间.command"
```

也可以在 Terminal 输入 `bash `，然后将 `准备评分工作空间.command` 从 Finder 拖入 Terminal，按回车执行。

成功时显示：

```text
PASS: 评分工作空间已生成：.../web-e2e-20260820-105921__codex/score
```

脚本最后显示“按回车键关闭”时，再按一次回车即可。该工具依次查找 `python3` 和 `python`；均不存在时按 3.3 节手工合并。

### 3.2 Windows 推荐操作

将 scoring ZIP 放在 `manifest.json` 同级，并保持 `score/` 为空。可以直接双击：

```text
准备评分工作空间.cmd
```

也可以在 CMD 中运行：

```bat
cd /d "D:\WebE2E\web-e2e-20260820-105921__codex"
准备评分工作空间.cmd
```

PowerShell 示例：

```powershell
Set-Location "D:\WebE2E\web-e2e-20260820-105921__codex"
.\准备评分工作空间.cmd
```

工具优先使用 `py -3`，其次使用 `python`。成功时会显示 `PASS: 评分工作空间已生成`。

### 3.3 没有 Python 时手工合并

仅在系统没有 Python，且 ZIP 工具支持合并同名目录时使用：

1. 确认已完成整个 Harness 根目录的备份。
2. 将 `execution/tasks/` 整个复制到已有的 `score/` 下，得到 `score/tasks/`。
3. 将 `<batch_id>__<harness>__scoring.zip` 解压到 `<harness-package-root>/`。
4. ZIP 工具询问同名目录时选择“合并”，不能选择替换整个 `score/`。
5. 若生成 `score 2/`、`score (1)/` 或另一个 Harness 根目录，立即停止，不要开始评分。

### 3.4 准备完成检查

每个评分题目必须具备：

```text
score/tasks/<task_id>/
├── PROMPT.md
├── workspace/
├── private-scoring/
│   ├── task_contract.json
│   └── fixtures/                       # 仅题目引用评分素材时存在
└── .web-e2e-scoring-ready
```

评分目录中不应出现 `.agents/skills/score-web-e2e/`；评分 Skill 应安装在评分智能体中，而不是复制到每个题目。

## 4. 安装并启用评分 Skill

在评分智能体的 Skill 管理界面导入：

```text
<batch_id>__score-web-e2e-skill.zip
```

导入后确认：

- Skill 名称为 `score-web-e2e`；
- Skill 已启用；
- 同一台评分客户端只保留需要使用的版本；
- 更新评分 Skill 时只重新导入新的 Skill ZIP，不需要改动各题评分目录。

## 5. 逐题评分

### 5.1 每题创建独立评分工作空间和会话

在评分智能体中：

1. 新建项目或工作空间。
2. 选择 `score/tasks/<task_id>/`。
3. 为该题新建一个会话。
4. 触发 `$score-web-e2e`。

推荐输入：

```text
请使用 $score-web-e2e 对当前工作空间中的单个 Web 用例进行完整评分。请启动站点，使用浏览器逐项操作和取证，并生成 private-scoring/task_score.json。
```

不要选择 `<harness-package-root>/` 或 `score/tasks/` 作为单题评分工作空间，否则评分 Agent 可能同时索引其他用例。

### 5.2 评分 Agent 应完成的工作

评分 Agent 将：

1. 读取 `private-scoring/task_contract.json` 中的 Prompt、Expected Behavior 和 Rubric。
2. 在 `workspace/` 安装依赖、构建并启动站点。
3. 使用浏览器实际点击、输入、切换、刷新、改变视口或上传文件。
4. 按 criterion 记录动作、观察、理由和证据；视觉检查点保存截图。
5. 生成 `private-scoring/score_input.json` 和 `private-scoring/task_score.json`。

测试人员不需要手工编辑 JSON，也不要要求 Agent 仅通过源码或静态截图推断交互结果。

### 5.3 单题评分完成检查

确认以下文件存在：

```text
score/tasks/<task_id>/private-scoring/
├── score_input.json
├── task_score.json
└── evidence/                           # 正常评分按检查点保存证据
```

若站点无法启动、浏览器不可用或评分过程中发生异常，应由评分 Skill 记录 `evaluation_error`，不能伪造操作证据或成功结果。

完成一题后关闭该题启动的站点服务，再为下一题新建工作空间和会话。

## 6. 生成回传结果

全部单题评分完成后，新建一个不参与单题评分的管理会话，并将 `<harness-package-root>/` 选为工作空间。输入：

```text
请使用 $score-web-e2e 的回传准备流程检查全部评分结果，关闭残留站点进程，清理可重新安装的 node_modules 和候选过程意外生成的 .git，检查敏感文件，并在当前 Harness 根目录生成 submission.json。不要删除源文件或评分证据。
```

完成后确认根目录存在：

```text
<harness-package-root>/submission.json
```

随后使用系统 ZIP 工具压缩整个 `<harness-package-root>/` 并回传。不要只回传 `score/` 或 `submission.json`。

macOS：在 Finder 中选中 Harness 根目录，右键选择“压缩”。

Windows：在文件资源管理器中选中 Harness 根目录，右键选择“压缩为 ZIP 文件”或“发送到 → 压缩文件夹”。

## 7. 常见问题

### macOS 双击 `.command` 提示“来自身份不明的开发者”

这是 Gatekeeper 在脚本运行前的拦截，不是评分准备脚本报错。不要关闭系统安全功能，直接使用：

```bash
cd "/path/to/<harness-package-root>"
bash "./准备评分工作空间.command"
```

### 提示 `score` 已包含内容，拒绝覆盖

工具只允许向空的 `score/` 生成第一次评分副本。若尚未评分，把误放进 `score/` 的 scoring ZIP 或其他文件移到 `manifest.json` 同级后重试；若已经开始评分，不要移动或删除现有结果，先联系评测管理员。

### 提示找不到 scoring ZIP

检查文件名是否与 `manifest.json` 中的 `scoring_archive` 一致，并将 ZIP 放在 Harness 根目录或其同级目录。最简单的位置是与 `manifest.json` 同级。

### 系统没有 Python

使用 3.3 节的 ZIP 目录合并流程。不要安装来源不明的 Python，也不要用覆盖整个目录的方式解压。

### `$score-web-e2e` 无法识别

确认已在评分智能体中导入并启用 `<batch_id>__score-web-e2e-skill.zip`。评分 Skill 不在单题目录的 `.agents/skills/` 下。

### `@PROMPT.md` 没有自动读取文件

不同 Harness 的文件引用语法可能不同。直接打开当前题目目录中的 `PROMPT.md`，复制完整内容发送；不要从其他题目复制 Prompt。

### 出现 `score 2`、重复 Harness 根目录或同名目录替换提示

说明 ZIP 工具没有按预期合并目录。停止评分，保留执行备份，清理错误生成的重复目录后，优先使用 macOS/Windows 评分准备脚本重新生成。不要用重复目录中的混合结果继续评分。

## 8. 最终检查清单

### 执行人员

- [ ] 每题选择 `execution/tasks/<task_id>/` 作为工作空间。
- [ ] 每题使用独立会话，通过 `@PROMPT.md` 发起执行。
- [ ] 候选产物全部位于该题 `workspace/`。
- [ ] 全部题目完成后已备份 Harness 根目录。

### 评分人员

- [ ] `score/` 从执行副本生成，未修改 `execution/tasks/`。
- [ ] 已独立安装并启用 `score-web-e2e`。
- [ ] 每题选择 `score/tasks/<task_id>/`，并使用独立评分会话。
- [ ] 每题均生成 `private-scoring/task_score.json`。
- [ ] 全部评分后根目录已生成 `submission.json`。
- [ ] 回传 ZIP 包含完整 Harness 根目录，且不包含真实凭证。
