# 浏览器交互评分与误判防护

本指引用于评分 Agent 操作候选站点时降低工具误判。它不提供固定 checker，也不替代题目中的 Prompt、Expected Behavior 和 LLM Judge Rubric。最终通过与否仍只由当前 criterion 的 Rubric 决定。

## 基本判定边界

- 必须通过候选站点公开的页面和浏览器行为验证结果。可以读取候选源码确认控件类型、事件模型或定位失败原因，但不能只凭源码给通过分，也不能直接调用应用内部 store、组件方法或业务函数制造通过状态。
- 每个 criterion 都以自身的“预设状态”为起点。若前一项操作改变了数据、筛选、路由、视口或浏览器存储，先恢复当前项要求的预设状态；只有预设兼容且不会污染结果的检查点才可共享状态。
- 首次操作无效不能直接证明候选功能失败。若页面存在相应控件或源码存在对应事件处理，必须按本指引至少换一种适合该控件的操作方式，并回读操作前、提交前、提交后的公开状态。
- 替代操作仍然只能作用于真实 DOM 控件和标准浏览器事件。不得改写候选源码、localStorage 业务数据、IndexedDB 业务记录或框架内部状态来绕过页面操作。
- 评分目录是执行结果的隔离副本。Rubric 要求删除、清空、重置或覆盖时必须实际验证取消与确认分支，不能因担心数据不可恢复而跳过。需要重测时重新构造预设状态。
- 若评分工具确实无法完成或观测 Rubric 必需的操作，且所有适用替代路径都失败，应记录 `evaluation_error`，不能把“工具无法操作/无法取证”写成候选站点的 0 分理由。

## 单个检查点的操作顺序

1. 恢复并核对预设状态，记录关键初值。
2. 在点击或提交前布置对话框、下载、瞬时状态等监听。
3. 优先使用语义点击、真实键盘或真实指针操作页面。
4. 同时回读控件原始值、可见文案、计数、样式或目标对象位置；不能只看操作命令是否返回成功。
5. 若操作未被应用接收，按控件类型使用下文的标准事件替代路径，然后重新回读。
6. 在干净的同等预设状态下复现关键失败；保留动作前后证据。
7. 最后按 Rubric 判定。0 分理由应描述候选页面在正确操作后的可观察不一致，而不是只写“没有捕获到”“无法点击”或“没有截图”。

## 受控输入框：日期、时间、清空、取色与滑块

HTML 原生控件要求匹配格式：`date` 使用 `YYYY-MM-DD`，`month` 使用 `YYYY-MM`，`time` 使用 `HH:mm`，`datetime-local` 使用 `YYYY-MM-DDTHH:mm`。分段键盘输入只要有一段未完成，控件可能看起来已有文字，但 `value` 仍为空且 `validity.badInput=true`；不能据此判定应用不支持目标值。

语义填充、全选删除、键盘或指针未触发应用更新时，如果评分浏览器支持页面上下文脚本，应对真实输入控件使用原生原型 setter，并派发冒泡的 `input` 与 `change`，必要时再失焦：

```js
const input = document.querySelector('input[type="datetime-local"]');
const setter = Object.getOwnPropertyDescriptor(
  HTMLInputElement.prototype,
  'value'
).set;
setter.call(input, '2026-03-09T09:30');
input.dispatchEvent(new Event('input', { bubbles: true }));
input.dispatchEvent(new Event('change', { bubbles: true }));
input.blur();
```

清空文本、页码范围、日期或时间时把目标值设为 `""`，再派发同样事件。`color`、`range` 等控件也适用原型 setter，但优先补做一次真实指针或键盘操作；有些站点只在 `input` 时实时更新，有些在 `change` 或失焦后结算，所以两类事件和最终 UI 都要核对。

每次至少记录三层结果：控件 `value`/`validity`、页面绑定的可见值或预览、提交或刷新后的持久结果。仅“控件画面显示目标值”不等于业务状态已经收到；仅直接执行 `element.value = ...` 后无变化也不能证明候选失败，因为框架可能劫持实例属性。

## HTML5 拖放与坐标操作

先识别站点使用的是 HTML5 `draggable`/`DragEvent`、Pointer Events 还是自定义拖拽库。普通 `mousedown → mousemove → mouseup` 不一定会触发 HTML5 `dragstart`/`drop`。

对标准 HTML5 拖放，真实鼠标路径失败后，如果评分浏览器支持页面上下文脚本，使用同一个 `DataTransfer` 依次派发完整事件序列：

```js
const source = document.querySelector('[draggable="true"]');
const target = document.querySelector('[data-drop-target]');
const data = new DataTransfer();
const fire = (element, type) => element.dispatchEvent(new DragEvent(type, {
  bubbles: true,
  cancelable: true,
  dataTransfer: data,
}));
fire(source, 'dragstart');
fire(target, 'dragenter');
fire(target, 'dragover');
fire(target, 'drop');
fire(source, 'dragend');
```

实际定位器按页面结构选择，不能照抄示例选择器。目标在滚动区、弹层或布局切换后，先滚入视口并重新读取边界框；不得继续使用旧截图坐标。拖放后必须从公开 UI 核对卡片所在容器、列计数和联动结果。若 Rubric 明确要求拖拽，状态下拉等替代入口只能用于诊断业务规则，不能替代拖拽本身得分。

## 原生对话框和自定义确认层

- 原生 `alert`、`confirm`、`prompt` 不属于页面 DOM，也通常不会出现在网页截图中。必须在触发点击前让评分浏览器准备接收下一次对话框；先取消并验证状态保留，再重新触发、确认并验证状态变化。
- 工具返回的对话框类型、文案和 accept/dismiss 结果属于有效交互证据；自定义弹层则使用页面截图与 DOM 文案取证。
- 首次点击后数据立即变化且未观测到对话框时，在干净预设状态下先布置监听再重试一次。只有重试后仍没有原生事件或自定义确认层，才能判定缺少确认流程。
- Rubric 只要求“出现确认并可取消”时，不要因为原生对话框无法进入页面截图而扣分；Rubric 要求精确文案时必须从工具事件中读取文案，不能猜测。

## 下载和导出

下载监听必须在点击前建立。点击后按 Rubric 接受的证据范围核对：浏览器下载事件、可点击下载链接、生成的成品、明确的成功提示，或者下载元素的目标文件名。Rubric 只允许真实下载时，页面 toast 不能替代下载事件；Rubric 明确列出多种可接受结果时，不得擅自收紧为“必须捕获 download”。

需要验证文件名时，同时核对可见名称、链接的 `download` 属性或下载事件返回的文件名。浏览器拦截下载 UI 不等于候选导出失败；若既无事件，也无 Rubric 允许的页面反馈或成品，才记录未达成。

## 瞬时加载、进度和自动消失状态

监听必须先于触发动作。可使用评分浏览器的快速采样、录像能力，或在页面上下文中提前注册 `MutationObserver`，记录目标文案、进度值、ARIA 属性或状态类的出现时间，再执行点击。点击完成后才开始截图，容易只看到完成态，不能据此认定中间状态不存在。

瞬时证据应同时包含“曾出现的状态”和最终结果；观察器只用于记录公开 DOM 变化，不能修改页面或延长候选状态。

## 响应式、滚动和视觉测量

- 先设置 Rubric 指定的精确视口，关闭无关弹层，等待布局稳定，再测量 `documentElement.clientWidth`、文档级 `scrollWidth` 和实际 `window.scrollX`。
- 区分整页横向溢出与表格、代码块、图表等局部滚动容器。Rubric 只禁止整页横向滚动时，局部容器可滚动本身不能直接记 0；Rubric 同时要求元素不截断或局部容器不超出视口时，再按原文检查局部边界。
- 不以单个离屏、隐藏、动画中或固定定位元素的边界框直接代表整页溢出。对 1px 级舍入差异要在相同视口复测，并结合实际滚动与可见裁切描述事实，不能自设比 Rubric 更严格的阈值。
- 切换视口、展开菜单、滚动或打开弹层后重新定位元素和截图，避免用过期坐标造成“点不中”。

## 截图二进制落盘

Codex Desktop 内置 Browser 的 `tab.getScreenshot({ emit: false })` 返回二进制，不应通过剪贴板、聊天文本或手工 Base64 分片转存。每张图都使用评分 Skill 内置的一次性接收器；它只监听 `127.0.0.1`，只允许写入当前题的 `private-scoring/evidence/`，上传一张合法图片后自动退出：

```bash
node <score-web-e2e-skill-dir>/scripts/screenshot_receiver.mjs \
  start --task-root . --filename desktop-main.jpg
```

`start` 是后台启动，成功后立即返回 JSON，其中 `upload_url` 带一次性随机令牌。不要把该 URL 写进评分结果或长期日志。当前 Desktop Browser 截图通常是 JPEG，但仍要让扩展名、请求 `Content-Type` 和真实二进制签名一致。取得截图后，在桌面 Browser 的持久 JavaScript 会话中直接上传二进制：

```js
let desktopMain = await tab.getScreenshot({ emit: false });
let uploadResponse = await fetch("<start 返回的 upload_url>", {
  method: "POST",
  headers: { "content-type": "image/jpeg" },
  body: desktopMain,
});
nodeRepl.write({
  status: uploadResponse.status,
  result: await uploadResponse.text(),
  bytes: desktopMain.length,
});
```

只有 HTTP `201` 才表示落盘成功。随后单独运行：

```bash
node <score-web-e2e-skill-dir>/scripts/screenshot_receiver.mjs \
  status --task-root .
```

要求状态为 `COMPLETED`，并核对 `output.path`、字节数和 SHA-256。下一张图使用新的安全文件名重新执行 `start`。接收器拒绝覆盖、目录穿越、MIME/签名不一致和超限内容；默认最多 20 MiB、5 分钟超时。若 Browser 或控制任务异常，运行 `stop --task-root .`，它只会在 PID、进程组、启动时间、命令和 cwd 全部匹配时终止已记录接收器。不存在状态文件时 `status` 返回 `NOT_STARTED`；不得用 `pkill` 清理。

若二进制头是 PNG 签名 `89 50 4E 47 0D 0A 1A 0A`，改用 `.png` 和 `image/png`。如果无法取得二进制、上传始终失败或状态不能进入可信终态，按评分基础设施错误处理，不能伪造截图或把它记为候选零分。

## 媒体与非截图证据

视频播放应在用户点击后核对 `currentSrc`、`readyState`、暂停状态和 `currentTime` 是否变化；浏览器自动播放限制不能直接算候选故障。对原生对话框、下载、瞬时状态、控件原始值等截图无法完整表达的事实，可在 `private-scoring/evidence/` 保存 Markdown 或 JSON 观察记录，并在 criterion 的 evidence 中引用；同时保留适用的动作前后截图。

## 提交前的零分复核

在运行 `finalize_score.mjs` 前逐条检查所有 0 分理由。出现以下表述时必须暂停并复核：无法输入、真实鼠标拖动无效、未捕获下载、没有看到瞬时状态、原生弹窗无截图、为避免删除而未执行、无法验证。

复核后只有两种合法结论：

1. 使用正确交互后，公开 UI 仍与 Rubric 不符：保留 0 分，写清正确动作、回读值和实际页面结果；
2. 评分工具仍无法可靠完成或观测必要操作：记录 `evaluation_error`，不得伪装为候选功能失败。
