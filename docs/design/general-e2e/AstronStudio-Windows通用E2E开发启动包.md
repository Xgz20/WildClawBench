# AstronStudio Windows General E2E 后续实施清单

更新：2026-09-21。**状态：暂缓，真机 NOT_RUN。** 先完成 macOS 四个 Harness 的 General 并进入评测，再启动 Windows。当前不创建 Windows 任务或 worktree、不要求 macOS 接收 Windows 交接。当前进度以 [General E2E 接续入口](README.md)为准。

本文件保留 Windows 平台差异和未来实施顺序；原双平台并行启动 Prompt 已撤下。没有 Windows 真机证据，不能凭共享代码、旧 Web 或 macOS PASS 宣称支持。

## 启动时核验

- 从当时已交付源码冻结实际 SHA、dataset digest、Skill/组件版本与包哈希；不采用旧 COMMON-001 至 004 的历史 SHA 作为默认最新基线。活动批次继续其原身份。
- 核对本地 checkout/分支、未提交修改和活动运行；沿用届时约定的串行开发分支，保留主检出与无关 worktree，不自动 reset、删除或另行派发。
- 记录 OS/架构、客户端与 Codex 安装、Node/Python、评分依赖锁、Playwright/Chromium、状态库和 loopback CDP。版本是元数据，真实能力决定兼容性。
- 调试根建议 `C:\e2e-debug\astronstudio-general`；验证短路径、可写性和隔离。本地任务产物不使用云电脑。正式包与调试数据分开放置。
- 模型、推理与权限回读本机已选配置；评分冻结本机批次的 Judge protocol/model/reasoning，不照搬 macOS 路径或配置。

## 有序实施与退出条件

| 次序 | 技术任务 | 完成条件 |
| --- | --- | --- |
| G5-01 | 原生安装发现、launcher、只读 probe | 真实进程/CDP 页面身份、DB 路径和环境条件有据；探针不发送、不顺便重启 |
| G5-02 | 项目/路径/配置回读、一次发送、原会话恢复、原生采集 | 单题后扩到固定小批；无重复 Prompt；session/turn/cwd、原始与标准轨迹、候选完整性可核验 |
| G5-05 | 停止/重启、任务进程树与基础设施异常 | 精确归属、残留和 quiet window 可验；Windows cleanup hook 不能用 supported=false 代替成功 |
| G5-04 | Windows 本机规则 Worker、语义评分与完整报告 | 专用依赖、GT 隔离、固定 Judge、score/submission、回传与同源报告全链路通过 |
| G5-03 | 按需验证 Windows 执行 → macOS 评分 | 逻辑身份和候选/轨迹哈希一致；单列跨机能力，不替代本机闭环 |
| G5-06 | 仓库外发行与支持范围 | 独立安装可运行；声明的架构、并发和恢复有本机证据；未测项保持 NOT_RUN |

题目 `timeout_seconds` 不限制 Harness 总执行时间，也不参与评分。CDP/UI、启动/停止、绑定、cleanup 与评分 Worker/API/线程控制 deadline 独立保留。

## 平台差异

- 安装发现覆盖运行进程、注册表与标准目录；同层多个实例失败关闭，不硬编码用户名。
- SQLite 只读一致快照、活动 WAL、中文/空格路径、UTF-8/CRLF、长路径、符号链接和文件权限分别验证。
- `python3`/Shell/工具依赖差异优先在环境层解决；改变题目或命令语义时发布可辨识变体，不悄悄改题。
- PowerShell/.cmd 入口与精确进程树停止使用 Windows 实现；不要照搬 POSIX 进程组，也不按进程名称批量终止。
- 独立发行必须包含依赖闭包和真实可调用的 Windows 路由；macOS wrapper 存在不等于 Windows 支持。

恢复开发时只维护 [接续入口](README.md)的 Windows 行与[验收清单](通用场景端到端自动化评测实现计划与验收清单.md) G5/WIN 对应项，追加必要证据索引。旧启动包与跨机交接历史可在 Git 中查询，不再重建并行协调台账。
