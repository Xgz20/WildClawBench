# DoubaoWork 2.35.19 原生适配

2026-11-05，新通用70题round1的原生调试启动触发客户端应用此前待安装的更新，实际运行版本从2.35.15变为2.35.19。不得继续将旧版本或旧实时脚本SHA写入执行身份。

继续使用loopback UI 9260和`--jsruntime-debugging-port=entry-moa:9261`。应用Bundle、浏览器及JSRuntime父子进程、启动身份、命令SHA和Inspector target均须逐次核验。启动成功不是执行、采集或评分验收。

## 新旧Profile

| 版本 | entry-moa实时源码SHA256 | 上下文/工具服务getter |
| --- | --- | --- |
| 2.35.15 | d7fb756b89560ae2fc8e0939d3afc1478c05bbfa5d1ed890927b731d6cbe5e42 | sE / Rh |
| 2.35.19 | e387108b1ffd23a898591d3822c37f578ebce07b52510a54e5bd25a186d03900 | sd / wv |

新版通过独立`doubaowork-moa-2.35.19-inspector/v1`和`doubaowork-native-moa-sdk-model-protocol-2.35.19/v1`绑定；版本、实时源码、observer、consumer、backend proof不能跨版本混用。旧2.35.15 Profile及原SHA保持。未知版本和未登记源码仍拒绝，不初始化工具服务，也不改变工具消费、上传或模型行为。

项目目录按实际调用的七个getter核验，新版源码SHA为`05110aa14aa5efe0d6f6c166ff58f5b11f86ef624e63aab81c4f330815ce6cbc`。仍须独立匹配UI项目ID、原生项目、当前设备、唯一主目录和冻结Workspace绝对路径；不从store读取出的路径反填期望路径。旧getter集合保留。

SDK取证仍要求唯一原始assignment与冻结Prompt、同一main agent、原调用ID和逐项返回守恒。原生空present_files回执仍为null/unknown。评分助手全文视图保留原始assistant行，声明和原始证明Profile须唯一匹配，旧视图字节不改。报告工具统计复用同一SDK校验入口，不套用旧Profile推断新版总数。

## 验证范围

真实2.35.19的只读准入已验证前台任务表初始化且空闲、ToolCallManager的pending/current/upload账本空闲，并绑定实时源码、浏览器/worker进程及Inspector证明；没有发送题目或安装取证观察器。项目getter及原生时钟源码另存SHA审计。单元测试覆盖新旧版本和来源交叉混用拒绝、未知版本拒绝、目录/设备漂移、SDK原始调用与缺返回，以及评分原始全文视图。

真实正式执行、完整采集、不可变校验、独立裁判及报告闭环仍须按轮次顺序完成，不能从只读准入或合成测试宣称已验收。round1原始冻结suite和失败记录保留，修复入口另存并锁定源码提交及制品SHA；AStudio已经运行的冻结入口不替换。
