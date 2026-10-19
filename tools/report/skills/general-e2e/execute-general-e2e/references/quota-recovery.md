# 人工恢复额度后接续原队列

默认额度故障仍暂停等待人工。没有授权的普通 `--resume` 不跳过失败、不记零分、不重发。只有人类明确确认额度恢复并授权重执行指定失败题，控制会话才可调用本入口；开发或检查恢复流程的请求不是实际重跑评测的授权。

原 queue ID、digest、任务范围/顺序、客户端、模型、权限和运行配置保持冻结。成功题复用；在途题只观察原会话，不取消或重发。在途或不确定状态尚未消解时，不开始新的额度重试。已封存轮次不使用本入口改写历史结果。

## 生成只读授权草稿

使用管理员保留的原 execution ZIP；不使用 scoring ZIP，不重建输入。脚本核对原 manifest、Prompt 和该题初始 workspace 的完整成员、SHA、大小、类型、权限及相对链接。

```text
python3 -X utf8 /绝对路径/execute-general-e2e/scripts/prepare_quota_retry.py \
  --describe-authorization --unit-root /绝对路径/原单元 \
  --queue-id 原队列ID --task-id 完整额度失败任务ID \
  --execution-package /绝对路径/原execution.zip
```

把输出保存到新的控制文件。草稿 `quota_restored`、`retry_authorized` 默认 false，操作者、授权引用和原因留空，不能直接执行。收到人类直接授权后，记录 `authorized_by`、`authorization_reference`、`authorized_at`、`reason`，再把两个开关设为 true；不能伪造或通过超时推断授权。额度确认是人的声明，不是脚本联网查询或购买额度的结果。

草稿绑定原 batch/unit/queue、queue digest、task、旧 attempt、旧状态/记录/工作区/控制清单 SHA、unit manifest SHA、run config digest、原 execution ZIP SHA及唯一新 attempt ID。不要手改绑定绕过错误，不修改已登记授权；临时 driver.lock 不纳入旧控制清单。

## 恢复同一队列

```text
node /绝对路径/execute-general-e2e/scripts/run_astronstudio_macos_batch.mjs \
  --unit-root /绝对路径/原单元 --run-config /绝对路径/原run-config.json \
  --queue-id 原队列ID --resume \
  --retry-quota-task-id 完整额度失败任务ID \
  --quota-retry-authorization /绝对路径/已获授权.json
```

其他冻结参数、并发选项和原 task-id 范围须与首次执行一致；不新建平行队列，也不与零发送准备重试混用。先持久化授权意图，再在单题/UI 锁内重新 probe 配置，确认原生旧 turn 唯一且已失败、没有活动任务。任何身份/SHA 漂移、配置变化、未知发送或非唯一原生终态都阻断。

随后完整归档旧控制记录和失败 workspace，只恢复该题初始 workspace，用原 Prompt 创建新会话及授权绑定的新 attempt。其他任务的 workspace、状态、证据、原生身份和评分不改动。旧 attempt 仍在 `tasks[].attempts` 中作为历史未选中项，新 attempt 显式选中，授权链保存在 `quota_recoveries` 和历史中。每个 attempt 最多一个发送意图，一次授权最多创建一个新 attempt。

归档在 `unit/.general-e2e/quota-recoveries/<task>/<new-attempt>/`：`failed-control/`、`failed-workspace/`、授权原字节、事务意图、逐成员清单和恢复回执。它是控制审计，不冒充标准 collect receipt。原正式 evidence 和评分不覆盖；历史队列完成回执若需替换，先按原 SHA 留存在 `receipt-history/`。移交时保留队列及这些审计目录；原始符号链接仅作为证据保存，导出/验包不能无检查地跟随。

## 中断、重复调用与后续阶段

授权一旦持久化，后续使用原参数加 `--resume` 接续，不再生成授权或 attempt。原外部授权文件丢失不影响缓存；缓存 SHA 漂移则拒绝。重复提交同一授权只恢复或返回原事务，不增加发送。

- 文件系统准备中断：由同一 journal 完成归档/恢复，不覆盖旧现场。
- 新 attempt 尚未 armed：确认 workspace 仍是初始内容后继续同一个新 attempt。
- 已 armed、已受理或发送不确定：只观察并核对原 turn，绝不再 clickSend；确认不了就停在 NEEDS_ATTENTION。
- 再次额度耗尽：旧授权已用过，须针对新的失败 attempt 重新取得人类授权。
- 新重试零发送准备失败：保留现场等待人工修复，随后用原队列 `--resume --retry-pre-send-task-id ID` 接续同一新 attempt。复用已登记额度授权，只允许已证明零发送的准备恢复，不创建第三个 attempt。

若控制 flow 的 execute 阶段为 NEEDS_HUMAN，在人类明确授权后用 run Skill 的 `set-stage --stage execute --status RUNNING` 接续原队列；完成必须经标准执行/采集验证登记，不手写 COMPLETED。本入口不调用规则或裁判，不重评分，也不覆盖已有有效评分。
