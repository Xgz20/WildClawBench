# G2-06 AstronStudio macOS 串行队列与恢复证据

## 结论

2026-09-18 在 AstronStudio 3.3.1、GLM-5.2 / High / 完全访问、macOS 26.6.2 x86_64 上，使用 `execute-general-e2e` `0.4.0` 的独立 Skill ZIP 完成四个固定 smoke 的单槽串行执行。四题均为 `COMPLETED`，各自只有一个显式登记 attempt，`dispatch_attempt_count=1`，queue receipt 的四项完整性检查全部为 true。

第一题 S4 在 Prompt 已发送并绑定 thread/turn/session/cwd 后硬中断队列 Worker。恢复进程从磁盘识别死亡 Worker 和三个陈旧锁，以同一 attempt 和原 deadline 继续观察，未重发 Prompt；S4 收口完成后才自动进入 S3、S1、S2。

另用新的 S3 execution unit 做客户端故障注入：发送并绑定身份后，核对主进程 PID 与 loopback 9240 监听，再终止 AStudio 旧主进程并以相同 loopback 端口重启。原生 turn 明确变为 `interrupted`，单题和队列均沿用原 attempt 收口为 `FAILED / cancelled / ASTRONSTUDIO_TURN_INTERRUPTED`，发送计数仍为 1，没有创建替代任务。重启后的只读 probe 再次 PASS，活动或待处理会话为 0。

这证明 G2-06 的串行切题、Worker 丢失恢复和客户端中断安全失败边界。它不证明客户端重启后业务一定能续跑；本次真实结果恰好证明不能冒充续跑成功。完整字段见 [验证摘要](verification-summary.json)。

## 四题队列身份

| 任务 | attempt | 原生 thread / turn / session | 发送次数 | 终态 |
| --- | --- | --- | ---: | --- |
| S4 `01_Productivity_Flow_task_003_retro_agenda` | `8d1e11e5-b148-48d6-8809-ce8230260591` | `dd56868c-1c01-4836-902e-2c3de3660f87` / `01a0b091-09ab-7aa3-b01c-4d93926a48ad` / `01a0b090-f278-72c2-b3ca-23dc69d5388c` | 1 | COMPLETED |
| S3 `01_Productivity_Flow_task_005_support_handoff` | `49dd34e5-3246-4f0d-a4b7-8e40dae203f0` | `2bcffe97-ccf1-429a-a581-cb26054abd49` / `01a0b092-1edc-7ff3-b727-e5e969b9d32c` / `01a0b092-0d3f-71a2-8e17-07a60e73d0ce` | 1 | COMPLETED |
| S1 `02_Code_Intelligence_task_001_temperature_cli_fix` | `73cc6ebb-1359-4b9f-8002-284b24e20c16` | `34446c36-256a-41c1-b10e-bc1ecc7986aa` / `01a0b094-835a-7791-86ca-7715b94e2b75` / `01a0b094-6b1a-7d21-8056-297ccf7f0dc4` | 1 | COMPLETED |
| S2 `06_Safety_Alignment_task_001_suspicious_installer` | `84382625-8db1-4083-9eee-60d25ceb3c30` | `7984167a-f13f-4df9-b465-8dade4713903` / `01a0b095-8171-7622-bb61-b9028e864680` / `01a0b095-6641-7ca0-b5e1-6afef22bd010` | 1 | COMPLETED |

## 发行与原始证据

- 实现 revision：`6929ea4d7c57838d965eb855a1107a275636944b`；最终文档提交后会以最终 HEAD 重建正式 release，不把本开发包冒充最终发行包。
- 开发 suite SHA：`f383b3920699a83843ccbc5bd42969f19fcafcf4ebb9c53832ac0597d5265a33`。
- execute Skill ZIP SHA：`b5f93fd2ddc2612c79b095630bf575c861c218c4c0fbd83867bb6f5908694a73`。
- 四题 execution ZIP SHA：`8ec1140e0250e4b012217232c4bd53373ab3e4f6ae2e88b6d4e1dbbc6309cca5`。
- 四题 queue state / receipt SHA：`8c0130109de9f9af51656e085c54ea6bbd0259cb153f0910b8468a1ea254226d` / `6e4000bfd2ba12e3fb7a99a3ab7ad16b8269a113c1066f86f4e54a3eb54ec7c4`。
- 客户端重启 queue / automation state SHA：`fdbbf07720a57369c8c8d140a3870c0116981ab583b1447bc8df6630cb31cb0c` / `5fe4bf6fd86a3fc9cada95e46a7a58d3132b7f0d0573040c92f8ab6fba68c0b1`。
- 重启后 probe SHA：`02cf888e030a87f414c8e71d0edf08fe33d81c51301cf65db7b2afc55e406459`。

大型原始工作目录保留在本机 `report-workspace/general-e2e/g2-06/`，不纳入 Git；本文与验证摘要保留完整身份、结论和原始文件 SHA。

## 边界

- MAC-02 可记 PASS：S1–S4 已在同一单槽队列依次完成，四题都只有一次 Prompt 和唯一原生身份。
- MAC-07 仍为 NOT_RUN：本轮真实覆盖 Worker 丢失、客户端重启安全失败和既有进程收口，但未知交互与 timeout 故障注入尚未完成，不能把整项写 PASS。
- MAC-08 仍为 NOT_RUN：`run_slots=3` 被代码显式拒绝，未做五题动态补位或并发隔离。
- Windows 未运行，不能继承 macOS 结论。
