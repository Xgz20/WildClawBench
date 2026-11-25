# 异常沙箱现场保留

平台新批次默认将 `failure_retention_seconds=1800` 写入冻结计划。正常完成仍在采集、封存后回收；已创建沙箱的执行异常，在证据封存后保留30分钟。设置0可立即回收。取消不触发现场保留，证据不完整或远端状态不明仍进入待处理，不伪造成功回执。

旧批次缺少此字段时沿用立即回收策略，不修改历史计划、执行器或原始证据。新平台遇到缺少 `failed-sandbox-retention-v1` 能力的旧执行器，会拒绝启用保留的新计划并提示升级或设置为0。

## 现场与证据

异常时先尽力保存主屏幕PNG、尺寸和SHA-256，再停止本次客户端进程并采集证据。截图失败有明确日志，但不阻止其余失败证据收集。原报错窗口不保证仍打开，文件现场可在保留期间进入Windows查看；截图仅用于调试，不冒充正式评分检查点证据。

封存成功后，在批次控制SQLite中原子记录失败终态与保留记录。倒计时从封存时开始，使用UTC绝对截止时间。执行耗时在此收口，不包含后续30分钟等待。人工进入虚拟机后的改动不会回写到已经封存的执行包。

## 调度与资源

- `resource_held` 保持真实的沙箱资源占用，包含正在保留的失败实例。
- `execution_resources_held` 只统计阻塞执行、评分或重跑的资源。
- `retained_sandboxes_held` 和 `retained_sandboxes` 独立展示保留实例，包含用例重跑后旧尝试的现场。

失败保留不占执行并发。保留实例仍消耗AgentCube平台配额，因此同时存活的虚拟机可以多于执行并发数。新计划预检将保留时间加入TTL预算；不足时明确提示调整创建配置。不要通过把 `resource_held` 改成0来隐藏真实占用。

## 回收与恢复

平台启动独立回收线程，扫描包括执行已结束的批次。到期调用原执行尝试绑定的AgentCube配置，仅删除原session；回收前再次核验已封存备份。每个尝试独立文件锁，服务重启、并发操作和重复请求不会重新派题或误删新尝试。

HTTP202等未确认删除保留为回收中，错误显示回收失败，并按持久化重试时间继续处理；只有确切成功或该精确session已不存在才显示已回收。控制端凭据不写入公开结果。平台页面可复制完整session、查看异常截图、打开配置的控制台、按尝试提前销毁，操作受批次租户权限约束。

独立CLI使用者应另行运行回收观察器，或周期性执行同一回收命令；平台部署自动托管，不需要人工运行：

```sh
python eval/run_e2e.py --api-version 1 retention-reap \
  --workspace-root /path/to/workspace --batch-id batch-id \
  --agentcube-config /path/to/private-config.json --watch
```

提前回收必须明确指定执行尝试，不能用force笼统销毁整个批次：

```sh
python eval/run_e2e.py --api-version 1 retention-reap \
  --workspace-root /path/to/workspace --batch-id batch-id \
  --agentcube-config /path/to/private-config.json --attempt-id exec-id --force
```
