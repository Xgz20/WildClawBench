# G2-02 AstronStudio macOS 单题执行证据

## 结论

2026-09-17 在 AstronStudio 3.3.1、GLM-5.2、High、完全访问、macOS 26.6.2/x86_64 上真实执行 S1 与 S4。两题均只发送一次 Prompt，并绑定唯一 `thread_id / turn_id / provider session_id / cwd` 后取得原生 `completed` 终态。S1 覆盖文件修改任务；S4 覆盖不要求 Workspace 变化的纯回复任务。

G2-02 只交付单题发送和原生状态机。完整轨迹、资源指标和候选冻结属于 G2-03 至 G2-05，因此两个回执都保持 `evidence.completeness=partial`、`resource_metrics_path=null`、`candidate.drift_status=not_frozen`，不能直接进入正式评分。

## S1 文件修改任务

- batch：`general-g2-02-s1-macos-20260917-224935`
- task：`02_Code_Intelligence_task_001_temperature_cli_fix`
- attempt：`693c1c28-a78a-409b-82d7-b0dfcadb3132`
- Prompt SHA-256：`455f6e3fc79fa77d6d7ab98e43b93baee8e4f946c025bc2a118c943073c05c0b`
- thread / turn / provider session：`1fc7cf29-ec97-41ab-8264-51d23cc86bc5` / `01a0afda-4a76-79a2-887a-09cc22592523` / `01a0afda-3943-74b1-99a1-86fefb8e2f67`
- 终态与耗时：`COMPLETED / completed`，49.006 秒
- 人工操作 / 语义干预：0 / 0
- `--resume --observe-once` 前后 state、record、final response 三个 SHA 完全不变；发送计数保持 1，证明已完成 attempt 不会重发。
- [automation state](s1-automation-state.json) SHA `dbbc4d7b41586dc469d519d2d243ce24fdfe067c535a8dd3aaba09ec1c912e7d`
- [execution record](s1-execution-record.json) SHA `6d2cddb46466fa3bc743583a420d08dc56948e252865b56d975d827588f060a9`
- [final response](s1-final-response.md) SHA `8a87ee09b6cced3b50d37c01164125e106062b948d613762bcf9135686f0e91a`

## S4 纯回复任务

- batch：`general-g2-02-s4-retry1-macos-20260917-230054`
- task：`01_Productivity_Flow_task_003_retro_agenda`
- attempt：`143cdcd2-6a04-4486-ac1c-f1564b725103`
- Prompt SHA-256：`4883c97962465eb0b21ac77caf18a5c06fb29c256efa85eac5775746a1437509`
- thread / turn / provider session：`d34a6ebb-581e-452c-96bd-e9f0eb101744` / `01a0afe4-02dd-7562-8315-24dcb9cb765a` / `01a0afe3-e980-7a91-a889-1d3801846d26`
- 终态与端到端耗时：`COMPLETED / completed`，85.432 秒；原生 turn 实际在 24.589 秒内完成，较长端到端耗时包含热写 SQLite 快照失败后的恢复时间。
- 人工操作 / 语义干预：0 / 0
- 首次包在展开侧栏时发现 50 个逐项目 `new-thread-button`，执行器在发送前失败且 `dispatch_attempt_count=0`；[失败状态](s4-pre-send-failure-state.json) SHA `296fa83d3a5a85cce17b384fe39f82fc44b48d78a51b4f86e2b49bb29c85862b`。修复后优先选择唯一的全局“新建任务”动作。
- 修复后的任务只发送一次并完成身份绑定；终态轮询期间捕获一次 `database disk image is malformed`。执行器未新建 attempt、未重发 Prompt，随后使用 `--resume --observe-once` 收口同一 attempt。最终候选增加快照重试退避和轮询级恢复测试。
- [automation state](s4-automation-state.json) SHA `ba40caab885433d4b098df853f8777f16ebcd045142ed35221a5d2a39dcd2697`
- [execution record](s4-execution-record.json) SHA `c172463884a7fe64c4bb66bb44cb27c772207c5d0e08e733457987f6c513930d`
- [final response](s4-final-response.md) SHA `b436e6a776b6d320892fb53fd3cfd124170d34827ebdc6757ce21158b3992381`

## 发行候选与证据边界

- S1 使用的 suite / execute Skill / execution ZIP SHA 分别为 `2bf2c20c84c20ee0f54fadf04a20070303c96d3a3dfda9773ba637c961bcc4bc`、`bae343d575934cc80f3f7766ae84b7005379ffcce99334ab556edac5471aca83`、`25c8213fd7e999579394f795595f7e7eaaf034451b6c3d6050529d70299d4c14`。
- S4 成功运行使用的中间候选 suite / execute Skill / execution ZIP SHA 分别为 `9847fa12d90536818744830723d6897978a3894479f6a73a3842a84e5501a0da`、`6f9ea091a9696bb44870aa53d5445e2df5729b64169bfb3209bb2769f3029b84`、`8a9803fb5bc302c471187fc87b7e9a5f4e215c13c1c818edb4cdf7ef625dfa63`。
- 最终开发候选 suite 为 `g2-02-dev-final-20260917-232053`，SHA `3b1e5bcdb5440a70c5ea1b9f8533d32d72d5f37153c7d2f17cc63c4edece1bde`；其中独立 execute Skill SHA 为 `328c2e0c118751510ad900e941e3c13f6f3d29170bd8b4c066456cba99646d4a`，验包通过。该 Skill 可在 checkout 外显示帮助并从真实 AStudio 状态库唯一回读 S4 的 completed 身份。
- 以上开发发行 catalog 的 `source_revision` 为已提交基线 `17b7f178edf5c5fa90513ee784f8e1c30a324469`，但包同时包含当时尚未提交的 G2-02 候选，不能把 catalog 字段单独解释为正式发行身份。正式身份以本次 G2-02 提交和后续重建发行包为准。
- 两个 `execution-record.json` 均通过 `eval_general_e2e.contracts.validator` 的 execution-record v1 语义校验。
- 当前只真实执行 S1、S4；S2、S3 尚未运行。因此 MAC-01 可通过，MAC-02 仍只能记为部分覆盖，不能写 PASS。
