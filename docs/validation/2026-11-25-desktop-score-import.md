# Windows 桌面评分回传权限修复

## 远程失败绑定

- 环境：`172.31.101.44:9619`；平台批次 #1，逻辑评分 #1 的 v2 实际操作 #5。
- 框架读取器：`fb28b13df8a855fcb3afab9aa453ab92088185d4`。
- 用例：`01_Productivity_Flow_task_001_expense_policy_check`。
- 执行：`exec-486de2fb47cb438f94d0bbd5147fd142`。
- 评分：`desk-9b301c2e381bd8ce8274ada6`。
- 冻结模板：`agentcube-windows/winarena-pc-20261125-a`。
- 冻结镜像：`sha256:363af9d8d3d4dd0f15126d6d084586679b1d12df62741545e6194e8337990240`。
- 冻结 WAA：`4adaa72571149964ac0d8e44dcfab3228b79a14a`。
- 评分回执中会话 `da27f3cd-e13b-4089-8d3e-b1333d81e7a9` 已释放；没有重新启动该沙箱。

## 观察与根因

新读取器已经完成 Windows 规则运行及回传，失败发生在 Linux 控制端的归档校验。
直接重放原 `verify-score --archived`，退出码 2，具体错误为
`CANDIDATE_ORIGINAL_WRITABLE`，目录为 `candidate-original/`。框架 `_run` 丢弃了
子进程错误输出，页面只剩 `DESKTOP_SCORING_VERIFICATION_FAILED`。

ZIP 解包后的候选目录为 `0755`、文件为 `0644`，GT `expected.json` 为 `0644`。
仅恢复候选只读后，GT 权限仍不匹配，校验返回 `CANDIDATE_ENTRY_MISMATCH`。
再按原 manifest 恢复 GT 的 `0444`，原冻结 Skill 校验即为 PASS。

## 修复与证据

控制端导入副本恢复候选只读及冻结 GT 权限，核对导入前后文件内容摘要，并保留权限
审计；原评分算法、标准分和完整性校验保留。校验日志作为评分日志归档，具体错误码
进入脱敏详情。适用于共用此通用回传适配器的 AStudio、ChatGPT 桌面评分。

在远程容器的独立临时目录中，加载本轮权限恢复实现，复制原尝试的 39 个文件，合计
460635 字节：

- 恢复后原 Skill 的 `verify-score --archived` 退出码 0，`status=PASS`、`score_valid=true`。
- `score.json` 摘要保持 `c7f33c59432c0a33cd92e311fc3ad042e1a513fcd082d9a50f46324126674c92`。
- 导入副本与原尝试的全部文件内容摘要相同，原尝试内容也保持不变。
- 在临时副本中给候选追加换行后重新封存，校验仍以 `CANDIDATE_ORIGINAL_DRIFT` 拒绝。
- 临时目录随探针结束清理；数据库评分、冻结发行、原始回执和业务服务均未修改。

本地覆盖 Windows ZIP 权限丢失、精确 GT 权限、内容不变、重复接收、目录 / 链接
拒绝、错误码与凭据脱敏、超时日志和失败后的回收路径。另回归现有桌面运行时、Web
回传、Docker CLI 与 Harness 配置测试，合计 59 项通过。此处是已有产物的离线验收，
不是新一轮沙箱评分验收。

## 冻结 Skill 边界

操作 #5 仍使用批次内 `score-general-e2e 0.29.4`，纯自动规则不调用语义裁判。
原标准分为有效 0 分，原因包含先前确认的候选 JSON BOM 与旧规则不兼容。
`fb28b13d` 中的 `0.29.5` 不会自动替换旧批次冻结 Skill；回传权限修复也不改写此零分。
验证 BOM 修复需新建批次冻结 `0.29.5` 或显式冻结新版评分 Skill 的新尝试；当前桌面
重评入口仍继承批次 Skill，不能声称点击旧批次重评就已升级规则。

需发布本轮框架修复后，由用户在平台手动重评验收；历史失败评分保持可追溯。
