# WorkBuddy 跨用例与跨重复记忆隔离验收

2026-10-21，北京时间。源码、本地提交仅在`.agents/memory-e2e`、`feat/memory-e2e`。
**A1→B1→A2共9次UI请求完成，跨用例与跨重复隔离复算通过。正式20题未启动，UNSCORED。**

本轮验证同账号在“用例 × 重复”边界切换后，旧事实不会进入后一个评测单元。
轮内跨会话保留记忆，不删除旧单元笔记，也不清空日常账号记忆。
七步链的遗忘失败独立保留，见[批次门禁与真机记录](WorkBuddy批次门禁接入与Sidecar兼容修复-20261021.md)。

## 条件与验收范围

- 安装版WorkBuddy5.8.3 arm64，签名和原生沙箱未修改。每个单元使用私有app-home/tmp/candidate，
  实际后端与原生工作进程保留OS边界。UI Main仍为原生角色，没有穷尽验证全部外部OS代理。
- 使用当前登录账号，指纹`ce6e994bb89e10b515ea7023dadb59acdb636204c4bf3631c90dea12ad64aa7a`。
  只复用MaaS模型`custom-local:xopglm52`→`xopglm52`，thinking=true、high、default-sandbox。
  没有替换成内置glm-5.2，也没有扩大到普通实例的Full Access条件。
- 数据集`memory-case-isolation-v2`：只把v1提示中的AStudio名称改为当前被评测客户端，旧v1和旧批次未修改。
  A/B项目名固定，三个单元各有冷查询、学习、跨会话回忆，共9次UI请求；六次查询字节一致。
- 实际形成的存储渠道是工作区`.workbuddy/memory/MEMORY.md`及当日日志，由模型文件工具写入、读取。
  这组结果不推导原生自动抽取、账号画像或云端全部索引已被隔离。
- Python runner的INTENT前与Driver实际按下前均复核OS边界；Driver使用可信Chromium输入进行桌面UI发送。
  原生session/request、cwd、Prompt SHA与模型元数据分别绑定。没有重发已接受或未知操作。

## 实测与独立复算

| 单元 | 冷查询 | 学习后新会话 | 旧单元实际文件操作 |
|---|---|---|---|
| A1 | A/B均未知 | 本轮A准确，B未知 | 六项原生正负控通过 |
| B1 | A/B均未知 | 本轮B准确，A未知 | 对A1的5项操作均EPERM |
| A2 | A/B均未知 | 本轮A准确，B未知 | 对A1/B1的10项操作均EPERM |

跨单元负例包括直接读取、stat、目录枚举、经当前单元符号链接读取、向旧目录创建负例文件。
只涉及合成测试笔记；每次均有当前单元可读正控，旧文件前后SHA相同。
三个单元另各自执行6项安装版原生worker检查，保留原生sandbox执行模式和完整原生SBPL。

最终`verification.json`为`PASS_WORKBUDDY_CASE_REPETITION_ISOLATION`：
9个不同原生会话全部完成，六次查询SHA为
`baebc1dfb5d7b2b7a852baa34a579cf043732872194bd28c34c321eb7d56bfa3`。
B1完整原生请求投影及扫描文件没有A1旧值；A2没有A1/B1旧值。
三个单元共扫描70,595个常规文件、1,769,198,676字节，39个符号链接明确未跟随。
三个关闭回执中记录的9份可见记忆文件SHA全部保持不变，没有通过删除旧记忆制造冷启动。

`scripts/memory-e2e/verify_workbuddy_isolation.py`从冻结证据重新检查：

- 三个准确case/repetition、同账号、9个不同原生会话、完整终态与精确模型路由。
- 可见编辑器内容、原生userMessage和冻结Prompt SHA一致，六次查询SHA完全相同。
- 三次冷查询和三次学习后回忆，seed实际文件原件存在；后单元的原生轨迹无旧值。
- app-home、candidate、tmp的常规文件扫描；符号链接不跟随并单列数量。
- 已关闭单元记忆原件SHA不变、进程和端口退出、自建tmp别名收回、普通模型配置SHA不变。

这些检查只覆盖已观察原生请求投影、文件字节和明确测试的OS路径，不能替代不可见provider上下文、
云端状态或任意外部broker的完整证明。分数始终为空，不作为正式模型排名。

## 证据与配置恢复

证据根为
`/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/workbuddy-case-isolation-20261021-r1`。
三个子目录A1/B1/A2各自保留scope、Profile、manifest、journal、完整原生请求投影、文件原件、
`app-home/admission-probe/result.json`，B1/A2另有`cross-unit-control-receipt.json`。
`audit_workbuddy_unit.py`在正常UI退出前检查原生请求与自动化状态，退出后核验准确进程身份均消失。
没有把安装版固定回false的checkMemoryUpdating当作后台空闲证明；后台自动记忆内部状态仍单列不可观测。

普通模型文件SHA基线为`8884410df80809ad5371c544356e26a04d634a397f7187fe86108a5eec486fdc`。
三个单元全部通过退出前原生状态核验后正常UI退出，Main与gateway均exit0，准确进程身份均消失，
9229/9336/9337无监听，三个自建短tmp别名均已删除、单元数据保留，共享UI锁不存在。
普通实例保持关闭；普通模型文件SHA与基线一致，未清空日常账号记忆。
最终广泛进程扫描另外发现3个本轮之前已存在的AStudio crashpad处理进程
（启动于10月15/17/18日），首次宽泛匹配及其PID/启动身份均留证；它们未被当作本轮执行根，也未结束。
精确退出与例外记录见`final-process-audit.json`，控制源码/数据集/验证脚本快照见`source-snapshot/manifest.json`。
没有读取或修改Codex真实记忆、配置或权限，旧机未知操作和旧批次失败保持原样。

回归基线Python133/133、Node104/104；新数据契约与新增脚本语法检查通过，
新增OS探针已在B1/A2真实签名后端执行通过，验证脚本已对完整三单元原件实际复算通过。
完整ACode Rust套件仍待先前询问的确认，本轮没有执行；AStudio自动事实抽取和真实周期仍未据此验收。
