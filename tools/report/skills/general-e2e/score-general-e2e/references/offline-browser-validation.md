# 离线页面独立验证

此环境只提供事实观察，不增加Rubric、自动给分或修改候选。浏览器URL策略拒绝file导航是裁判环境问题；不得因此扣能力分，也不得绕过拒绝去启动服务器、使用CDP或替代浏览器导航。

新版编排v7对含HTML/HTM候选的单题先执行环境预检，再允许创建Judge。hybrid默认继承规则阶段冻结的公共runtime；纯语义HTML任务须在preflight显式传入`--browser-runtime-python ABS`，必要时同时传入`--playwright-browsers-path ABS`。控制器复用原scoring-runtime-lock与probe-runtime，不改全局PATH或依赖。预检只运行公开合成fixture，验证键盘、420px、减少动态效果、截图与页面请求阻断，不读取候选或GT。

预检成功后，单题`judge-environment.json`冻结解释器版本/SHA、浏览器位置、观察脚本SHA、runtime锁、预检事实与截图SHA。先读取并核验该文件；profile缺失、漂移或环境失败时应在原attempt修复环境，不能自动换模型、创建替代聊天、补零或声称独立实测完成。

使用profile中的绝对Python加`-X utf8`运行其中指定的`offline_browser_validate.py`，只对子进程设置profile中的PLAYWRIGHT_BROWSERS_PATH。参数：

```text
PYTHON -X utf8 SCRIPT --html CANDIDATE_HTML --expected-sha256 FROZEN_SHA --plan NEW_PLAN_JSON --output-dir NEW_OUTPUT_DIRECTORY
```

脚本读取UTF-8字节到新Chromium about:blank上下文，不导航file/HTTP URL、不启动localhost、不使用CDP、不改变URL安全策略。context offline、所有页面请求abort、service workers禁用；不声称OS网络隔离。若治理策略仍拒绝此离线方法，保留错误并停止依赖动作，不绕行。外部资源依赖保留为阻断事实，不能静默补齐或将环境限制当候选缺陷。

由独立裁判按原Rubric选择操作范围。计划是JSON数组，支持：

```json
[
  {"action":"viewport","width":1280,"height":900},
  {"action":"snapshot"},
  {"action":"press","key":"Tab"},
  {"action":"press","key":"Enter"},
  {"action":"screenshot","name":"desktop.png"},
  {"action":"viewport","width":420,"height":900},
  {"action":"reduced_motion","value":"reduce"},
  {"action":"snapshot"},
  {"action":"screenshot","name":"narrow.png"}
]
```

还支持click（selector）、wait（0–1000ms）、Space/Shift+Tab/Escape/方向键/Home/End。输出目录必须新建且在候选之外。保存observations.json和截图并实际查看；不能用自动规则分或源码代替独立实测。输出绑定原HTML SHA，候选读前/后均校验；正式评分引用继续通过query-evidence查询原候选、输入、规则等证据，说明派生观察的来源和局限。不要把公开预检fixture当作候选证据。

脚本`--probe --output-dir NEW_DIR`只检查合成环境，不是候选测试或能力评分。历史v3–v6 Prompt、旧环境附件和已完成评分不改写；重新评分须另获授权并使用新attempt。
