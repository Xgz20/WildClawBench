# HTML运行时观测

任务以`scoring_runtime: {html_render: true}`显式要求评分侧浏览器，可与`office: true`并用。这个字段进入私有评分契约，不注入候选Env。候选需要理解输入图片才计多模态；评分器浏览HTML本身不改变任务的输入模态。

准备者先用可信资产建立锁，再加入既有Python Worker锁：

```bash
python score_general_e2e.py bootstrap-html \
  --node /absolute/node --playwright-core /absolute/playwright-core \
  --browser /absolute/chromium \
  --runtime-lock /absolute/python-runtime-lock.json \
  --output /absolute/combined-runtime-lock.json
```

Node与浏览器锁定程序绝对路径、可执行文件SHA和版本；Playwright core锁定完整文件树。另绑定平台、观察脚本SHA及固定视口1280×960、DPR=1、zh-CN、Asia/Shanghai、light、reducedMotion=reduce等设置。可重复`--font-file`绑定明确字体文件。该锁不封装浏览器的系统动态库，也不穷举系统回退字体；需要跨机比较版式时还应冻结系统/字体环境。旧锁和历史attempt使用原冻结入口。

任务作者把当前`html_runtime.py`和`html_observer.mjs`原样放入私有GT，再从受管Worker调用：

```python
import json, os, runpy
from pathlib import Path
root = Path(kwargs['workspace_path'])
api = runpy.run_path(str(root / 'gt/html_runtime.py'))
lock = json.loads(Path(os.environ['GENERAL_E2E_HTML_LOCK']).read_text(encoding='utf-8'))
result = api['observe_html'](
    root / 'results/report.html', lock,
    Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']) / 'report',
    probes=[{'id': 'point-a', 'x': 120, 'y': 240, 'radius': 1}],
)
observation = json.loads(Path(result['path']).read_text(encoding='utf-8'))
```

每次使用新的派生目录，不能放在公开资源根中。默认公开资源根是原HTML父目录，可显式传`resource_root`选择包含源文件的上层公共目录。资源有256文件/64MiB上限，源HTML上限5MiB，不跟随符号链接，不复制`.git/.agents/gt/private/worker/runtime`内部文件。保留原相对路径语义；HTML及资源在受控HTTP origin本地fulfill，其他请求及WebSocket阻断，使用全新headless context并禁用Service Worker。派生资源以SHA命名的`.bin`保存，避免被Office证据校验当成新原件。

观测包含可见性、原生/ARIA表格、文字及位置、SVG实际路径采样、Canvas2D笔画与文字/裁剪/清除记录、图片及frame元数据、请求和页面错误。几何探针最多512个，坐标为整页CSS像素，可按返回的形状ID限制目标。SVG使用初始化时捕获的原生几何函数；Canvas支持普通路径、Path2D、绘制时变换、DPR映射、裁剪、部分清除及尺寸重置。探针同时返回实际页面截图的RGBA，像素在另一干净页面解码。截图及Canvas位图均保存。

业务规则必须根据可见表头、图例、坐标轴及实际曲线建立检查，不能固定参考HTML的选择器、viewBox或布局，也不能只读取隐藏JSON。几何命中不等于最终可见笔画：后绘制的遮挡、合成、滤镜、mask、渐变等仍需对照实际像素和结构。Canvas的fill/drawImage/putImageData仅记录操作及位图，并显式标出向量观测缺口；WebGL、离屏转移、旋转/3D CSS变换、iframe正文等不具备通用矢量重建保证。open/closed ShadowRoot会收集。合法交付超出任务评分器已验证的支持面时应保留`evaluation_error/null`；缺图、错值等候选错误仍按任务Rubric计分。

回执绑定原HTML SHA、完整资源清单、运行时锁SHA、实际观察脚本、请求、观测、PNG和所有派生字节。评分框架只接受扎根冻结候选或私有GT原HTML的来源，语义证据目录包含运行时锁及派生文件。正常复核要求资产仍匹配；`verify-score --archived`不启动浏览器、不要求资产仍存在，但继续复核完整锁结构、源/资源及上下文绑定和文件字节。它是可复算的归档完整性检查，无法证明任意自洽重签的全套记录没有被替换。

缺锁/缺程序/资产漂移/不稳定页面/观测超限/超时都属于评测异常，不能转换为能力零分。内部超时终止Node与BrowserServer各自进程组；Node另监测Python父进程，在外层Worker取消时清理浏览器。跨平台进程清理仍需各平台原生验收。

真实浏览器协议测试需要显式提供资产，未提供时只运行锁/契约测试：

```bash
GENERAL_E2E_HTML_NODE=/absolute/node \
GENERAL_E2E_HTML_CORE=/absolute/playwright-core \
GENERAL_E2E_HTML_BROWSER=/absolute/chromium \
python -m unittest tests.general_e2e.test_html_runtime -v
```
