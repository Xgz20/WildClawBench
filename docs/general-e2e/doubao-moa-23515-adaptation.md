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

观察器只定位已初始化且唯一的ToolCallManager、上下文表与LocalToolSSE，
不调用初始化、工具、权限或上传函数。真实题目确认2.35.15的工具走原生SDK；
这个旧兼容路线的零交付仅作为原件保留，不能据此宣称本题工具调用为零。
旧SSE评测继续沿用原消费/派发/上传账本、30分钟TTL和完整性门禁。

## 原生SDK协议与素材

General collector显式准入当前MOA SDK协议。唯一会话及main agent目录必须通过原始IM、
完整Prompt、项目/Workspace和一次发送的绑定，且普通目录链与源文件SHA均通过检查。
`system/assignment.md`的唯一用户指派全文必须匹配冻结Prompt；创建时间仅作为原件元数据，
不参与执行耗时计算。工具轨迹原件按调用ID核对参数、返回及顺序，缺失/重复/冲突均拒绝。
SDK原件是工具计数和模型实际可见返回的来源；搜索和阅读卡片只核对输入多重集，
不将界面预览代替工具返回，也不为重复输入猜测单个卡片与结果的映射。

`image_link_list`保留调用ID和原返回行。采集器只下载声明的受限HTTPS来源，验证每次
重定向、图片类型和文件字节，记录原链接摘要、下载时间和图片SHA后纳入封存包。
macOS只复用原已开启的loopback系统HTTPS代理，不修改网络设置。离线复算重新核对
原协议、assignment、全部图片摘要和规范轨迹，不依赖候选文件推断调用或回填内容。
图片无法取得时不发布虚假的完整轨迹，也不将其变成模型能力零分。

## 前端与时钟

新版前端使用`chunk_@flow-web/desktop`，旧命名空间继续支持，多个候选时拒绝猜测。
模型流仍克隆实际匹配Prompt及Workspace的响应，不修改请求、响应、工具输入或原完成决定。
新版SDK实际以`Math.floor(performance.now()+performance.timeOrigin)`产生receiveTimestamp；
固定同步/异步生产函数及该时钟函数的源码SHA，不把它标成服务端时间或旧Date.now实现。

新MOA来源SHA仅与完整后台身份证明一起准入。跨来源轨迹继续不继承旧emitter的时间排序边界。
缺失资源保持null/partial；本题源码、执行素材、GT、检查点、权重及旧60题七维映射不变。

## 验收边界

空项目验证了观察器安装、零消息采样及原函数恢复。真实题目另验证了三路同时活动，
以及SDK调用/返回、独立assignment和多模态链接的原件关联。
Node回归覆盖旧SSE、新入口、来源/PID/目录拒绝、协议守恒及缺失/漂移拒绝。
正式采集、全部图片封存、独立评分和回传仍须以本轮各阶段实际产物验收。
