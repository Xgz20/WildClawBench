# 仓库地址与本地配置

公司仓库迁移后的工程名称为 AStudio Eval Framework。GitHub 仓库继续使用 WildClawBench 名称，作为基于上游扩展的代码镜像。

| 工程 | 公司 SSH 地址 |
|---|---|
| AStudio Eval Framework | `ssh://git@code.iflytek.com:30004/CYXH_Agent/AstronStudio-Eval/astudio-eval-framework.git` |
| AStudio Eval Platform | `ssh://git@code.iflytek.com:30004/CYXH_Agent/AstronStudio-Eval/astudio-eval-platform.git` |

## 多远程配置

当前框架仓库使用公司 Git 拉取，并向公司 Git 和 GitHub 双端推送。

| 配置 | 目标 |
|---|---|
| `origin` fetch | 公司 `astudio-eval-framework` |
| `origin` pushurl | 公司 `astudio-eval-framework` 和 `https://github.com/Xgz20/WildClawBench.git` |
| `gitee` fetch/push | 公司 `astudio-eval-framework` |
| `github` fetch/push | `https://github.com/Xgz20/WildClawBench.git` |

`gitee` 是现有公司远程的别名。`script/switch-push-target.sh` 从该远程、`wildclawbench.gitee-url` 缓存和 `origin` 读取地址。已有检出迁移时，这些配置都应指向新公司地址。

核验实际配置与切换预览。

```bash
git remote -v
git config --get wildclawbench.gitee-url
bash script/switch-push-target.sh both --dry-run
git status --short --branch
```

实际切换使用 `bash script/switch-push-target.sh both`、`github` 或 `gitee`。Git 推送会按 `origin.pushurl` 中的目标逐个执行。

## 分支与目录

迁移后的公司仓库保留 `feature/astroncode-eval` 分支。分支跟踪关系由 `branch.<name>.remote` 和 `branch.<name>.merge` 维护，按实际远端分支核验。

已有工程的位置与远程地址分别配置。Git common config 中的远程配置由 linked worktree 共用，启用 `extensions.worktreeConfig` 的工程还需检查各 worktree 的有效配置。

目录迁移应一并处理 Git worktree 注册信息、Skill 符号链接、IDE/Codex 项目路径和平台的工程根目录配置。冻结评测中的执行器与 Skill 绝对路径由原批次契约管理。

框架与平台配套部署时，`WCB_ROOT`、`WCB_E2E_ROOT` 及相应 Python 参数指向实际安装目录。
