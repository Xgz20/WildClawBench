# ChatGPT Windows 沙箱评分运行适配验收

日期：2026-11-22。使用本地平台 `http://xgz.eval.local:8080/wildclawbench/task-runs`，复用批次 #18 的 `07_Website_Generation_task_023_important_day_countdown` 原执行产物；本轮没有重跑被测端。

## 评分 Skill 与实现

继续使用冻结的 `score-web-e2e 4.5.5`，目录摘要 `1d0d68f08b43c9a60cbcd2da1d4f66b65d85f0e787744edecad81a7bd9ae27f3`；Skill、静态服务器、受管运行时和截图接收器与原冻结包一致。ChatGPT 评分执行器校验摘要后交付工作区副本，由 Prompt 明确读取；不依赖全局 Skill 自动发现，也不通过用户环境预处理改变 Skill。

修复集中在框架和控制层：

- 派发提示按 Skill 区分已有静态构建和动态项目。静态构建使用已有 `start-static` 入口，动态工程继续使用运行时副本；移除对静态产物强制使用通用 `start --url` 的冲突指引。
- 控制器和框架支持客户端对字面 HTTP(S) URL 冒号的确定性 Markdown 转义。由原请求生成可接受表示，不对任意原生文本做宽松反转义；更改网址、文件名或追加指令仍拒绝绑定。
- 框架识别 `ImageView` 镜像事件。既有规范化工具调用及未知事件完整性检查保留。
- 截图验证识别同一原生 JavaScript 上下文中的异步截图函数复用。回执记录定义与调用的关联；上下文隔离、重绑定失效、重复回执和字节摘要校验均有回归覆盖。

框架运行发行 `febf5ed5a2cd55c3ff5e811d8cb126b382e04f7c`；WGUI 运行源码 `37fa332a3a2c360406e7b830c5b0036582346ed7`。框架 30 项、WGUI 31 项定向回归通过。

## 模板

模板：`agentcube-windows/winarena-pc-20261122-193046-chatgpt-pro-37fa332a-v5`，平台登记 #9、ChatGPT 评分默认。

镜像 digest：`sha256:9d1ed1857fd5d53bad502723633d3f0cd46d3f29f52e1957457b42bf716d69b3`。沿用 90 GiB 母盘，SHA-256 为 `87d00ec4a8e785006d8db7b36bcafcd6a3724d3662825434e388c2641384632f`；本轮只更新控制器层。镜像内 `/wgui` 和 `/shared/wgui` 的四个对应源码文件均已回读校验。

## 已完成的实机和重放验证

- 独立 Windows 验证实例使用同一 Skill 启动静态候选，完成表单交互、JPEG 视口截图回传（HTTP 201）和 SHA-256 核对，随后精确停止进程并清理；候选 32 文件冻结摘要保持一致。原控制器因网址转义漏认终态而超时，原生 `task_complete`、证据和失败回执均保留。
- v5 新实例的带 URL 发题通过 WGUI 正常入口完成。回读 `gpt-6.2-sol / high / never / danger-full-access`，输出唯一标识，原生身份绑定通过；会话 `26d605f8-4cfa-4455-a02a-f78059d42236` 已释放。见 `v5-native-probe.json` 和 `v5-native-binding-verification.json`。
- 平台 #114 的原生评分完成，但旧发行在 `ImageView` 处拒绝准入，平台仍保留 `evaluation_error` 和空分。修复后对相同原始轨迹重放，44 个规范化调用完整，9 张引用截图全部通过原生回执与字节校验；这不是对历史评分记录的改写。

## 正式单题闭环

平台 #115：`gpt-6.2-sol High`、评分并发 1、原生评分时限 7200 秒，已完成且准入有效。平台汇总为 `valid=1 / evaluation_error=0 / containers_held=0`。

- 有效总分 **90.91/100**（平台统一归一化字段为 `0.9091`），11 个检查点。美观度 **87.46/100**，按原契约单列，不计入总分。
- C10 窄屏布局项未通过：375×812 下正常输入的 17 字纪念日名称出现省略号；短名称对照完整显示。原生操作、公开状态回读和 `mobile-card.jpg` 支持该判定。这是候选页面扣分，不是评分环境异常。
- 规范化与原生轨迹准入通过，6 张引用截图均有原生调用、接收回执和文件摘要证明。
- 主环境四类文本预览（score、audit、trace、native_trace）均 HTTP 200；6 张截图逐个读取均 HTTP 200，MIME 与字节签名正确，并与证据包内 `native-visual-verification.json` 的 SHA-256 一致。评分详情接口返回 11 个检查点。
- 评分会话 `ff8a0e6c-5dc4-48e2-85b0-aad874c38b63` 已释放；与 v5 前置探针、#114 会话一起再次查询，平台均返回对应 session 不存在。独立构建验证 VM 已停止。

验收入口：`http://xgz.eval.local:8080/wildclawbench/e2e/batches/18`，选择评分 #115。浏览器现有登录已过期，因此本轮文件预览核验通过已授权的主环境 API 完成，没有把登录页当作 UI 按钮验收通过。

主要回执：`platform-score-operation-v5.json`、`platform-score-details.json`、`platform-preview-verification.json`、`final-release-verification.json`。原失败 #114 和冻结发行保持不变，#115 是新评分尝试。本次闭环验收范围为这一道自建 Web 用例，不扩展为全部场景或并发验收的结论。

本机回执位于源码地图所列调试工作根下的 `receipts/chatgpt-pro-platform-release-Q4lkVc/runtime-compat/`。其中 `platform-preview-*.jpg` 是通过主环境接口读取并核验摘要的图片副本；完整原生资料仍按各次评分尝试独立保留。
