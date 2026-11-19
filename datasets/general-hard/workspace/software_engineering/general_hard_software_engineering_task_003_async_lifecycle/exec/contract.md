# 并发处理器公开契约

修复 `project/worker.py`。该文件已有真实实现：正常批次可以运行，但取消、截止、发布错误与清理的交互存在缺陷。不要以改写测试或资源计数器来掩盖故障。仅该源码文件可修改；`project/resources.py`、`project/__init__.py`、`tests_public/`、本契约与`runtime.json`是保护输入。可以在worker.py中自由重构、添加内部函数和状态，不能把它替换成只匹配给定数据的脚本。测试产生的`__pycache__`不作为业务产物。

## 接口与工作语义

保留可导入的`BatchTimeoutError`（`TimeoutError`的子类）和异步接口：

`run_batch(items, pool, work, sink, *, concurrency=2, deadline=None)`

- `items`是唯一字符串的可迭代对象，允许Unicode。完整成功返回与输入顺序一致的work返回值列表，不能按完成先后排序。相同标识可用于后续独立批次；不同批次不得互相取消或共享终态。
- `concurrency`为正整数，限制同一批次未释放资源的上限；非法并发值或重复/非字符串items在触碰provider前抛`ValueError`。空批次返回`[]`，不触碰provider。
- `pool.acquire(item)`为异步，成功返回不透明lease。`work(item, lease)`为异步，返回业务值或抛出异常。只能释放实际取得的lease；每份lease必须恰好调用一次`pool.release(lease)`并等其完成。资源模块是演示provider，不保证隐藏验证使用相同类或属性；应通过上述公开方法工作。
- `sink.emit(item, status, *, value=None, error=None)`是异步终态提交。成功取得lease的item至多调用一次emit：work成功用`succeeded`及其原值；work失败用`failed`及原异常；在work完成前被取消用`cancelled`。未成功取得lease的item不得伪造终态或释放资源。
- emit的调用本身就是一次不可重试的提交尝试。provider可能在记录终态后才等待ack，也可能拒绝提交并抛错；不得因ack期间取消/出错再提交另一个终态。已提交的成功值不回滚，也不意味着整个批次成功。
- 完整成功时每个item恰有一次终态；失败或取消批次中，已经完成的item可保留终态，其余已取得lease的item依其实际路径结束。排队item是否已在故障被观察前开始允许合法调度差异，不按固定启动/完成顺序评分。

## 取消、截止与回收

- 外部取消必须向调用方传播`asyncio.CancelledError`，不能返回`None`、部分列表或伪装成功。单个work或provider错误须使批次失败，保留原异常类型，停止并收口本批次其余工作，不能只抛错却把兄弟任务留在后台。
- `deadline`是调用方持有的`asyncio.Event`，表示离线调度器发出的“已到期”信号，并非要求候选访问时钟或真实定时服务。非空批次开始前已置位时不应取得资源；运行中置位时应取消/收口本批次并抛`BatchTimeoutError`或等价`TimeoutError`。不存在须满足的机器相关毫秒性能阈值。
- pool.release本身可能异步挂起。取消（包括清理期间再次取消）不能把回收中断后直接结束；必须等待该次释放完成，不能调用第二次release来“补救”。取消期间已完成的终态也不能重复提交。
- `run_batch`返回或向调用方抛出最终异常时，它创建的工作、deadline观察和清理任务都应已结束，无活动lease或遗留业务/提交调用。所有provider均为内存fixture；无需网络、真实服务、账号、外部进程或安装依赖。
- 同时发生的独立故障/到期可选择任一已经观察到的失败原因，不要求固定的内部任务结构或调度顺序；不得因此报告成功或遗留资源。

## 交付和验证记录

- 修复后的`project/worker.py`是主要交付。不要修改保护输入，也不要把所有异常一律吞掉。
- `results/tests.txt`：可读的实际验证记录，列出实际命令、退出结果、覆盖路径及未验证项，并包含最终worker.py完整SHA256（例如用`python -c`/`hashlib`计算）。不限定记录排版；未运行的命令不能写成已运行。
- `results/lifecycle.md`：简要解释原始故障、成功/错误/取消/截止与清理交互，以及验证边界。不得无依据承诺真实服务可用性或性能。
- 可执行公开检查：`PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests_public -v`。使用统一预置的Python3.11+，无需任何额外包。评分侧将对冻结的候选源码进行独立离线执行，绑定实际源码/测试/命令/returncode；自述成功不能替代实际结果。
