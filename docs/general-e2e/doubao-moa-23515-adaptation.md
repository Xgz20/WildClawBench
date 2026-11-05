# DoubaoWork 2.35.15 MOA 原生适配

2026-11-05真机预检发现，客户端从2.34.4自动升级到2.35.15并启用MOA JSRuntime。
旧后台页工具服务按原配置不再初始化；不能把它当空闲，也不能仅改前端类名后发送题目。

## 入口与身份

管理员通过正常应用退出后，用已安装客户端的原生参数启动，不改模型、权限或后端开关：

```text
open -na /Applications/DoubaoWork.app --args --remote-debugging-address=127.0.0.1 --remote-debugging-port=9260 --jsruntime-debugging-port=entry-moa:9261
```

只支持本次验证的2.35.15、上述loopback端口和`entry-moa`。
原生`neotix.jsRuntime.enableDebuggingPort`在聊天页被来源限制拒绝，不伪造来源重试。
启动参数由已安装二进制核实；原生日志及实际监听证明该参数只为entry-moa开启调试。

每次调用同时核验：UI CDP目标ID、唯一预期浏览器监听者、JSRuntime子进程的可执行路径/
父PID/启动身份/命令SHA、127.0.0.1监听、Inspector目标PID和实时执行脚本SHA。
不能用磁盘文件或版本字符串替代实时脚本验证。当前实时入口为：

```text
https://resource.sandbox.invalid/local_webcontents/apps/entry-moa/main.js
SHA256 d7fb756b89560ae2fc8e0939d3afc1478c05bbfa5d1ed890927b731d6cbe5e42
```

只定位已初始化且唯一的ToolCallManager、上下文表与LocalToolSSE。
只调用经源级核对的只读getter，不调用初始化、工具、权限或上传函数。
安装原有派发/拒绝回执包装及独立入口订阅，原函数仅委派一次，保留原返回值。
原生uploaded账本、同cwd/会话/调用/参数及拒绝结果逐项对账，沿用30分钟TTL、容量、
完整性和孤立交付门禁。未知新版本/来源/关系仍拒绝，不回退为有效零次工具调用。

## 前端与时钟

新版前端使用`chunk_@flow-web/desktop`，旧命名空间继续支持，多个候选时拒绝猜测。
模型流仍克隆实际匹配Prompt及Workspace的响应，不修改请求、响应、工具输入或原完成决定。
新版SDK实际以`Math.floor(performance.now()+performance.timeOrigin)`产生receiveTimestamp；
固定同步/异步生产函数及该时钟函数的源码SHA，不把它标成服务端时间或旧Date.now实现。

新MOA来源SHA仅与完整后台身份证明一起准入。跨来源轨迹继续不继承旧emitter的时间排序边界。
缺失资源保持null/partial；本题源码、执行素材、GT、检查点、权重及旧60题七维映射不变。

## 验收边界

本轮在专用空项目上验证观察器安装、零消息采样和原函数恢复，未向该项目发送模型消息。
Node回归覆盖旧SSE、新入口、来源/PID/目录拒绝及原始事件守恒。
这只说明派发前门禁和观察器就绪；三路真实执行、正式采集、独立评分和回传仍须以本轮实际产物验收。
