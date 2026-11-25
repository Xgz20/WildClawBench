# 独立配置 Prompt 插件引用

插件替换负责调整环境中的文件版本，Prompt 插件引用负责提示客户端使用某个插件。两者独立，均默认关闭。AStudio 的通用和 Web 用例都可引用已经安装的插件，不需要为了点名插件而上传替换包。

## 平台与框架输入

平台发起执行时，引用位于配置单元的独立字段：

```json
{
  "profile_id": "<AStudio 配置单元>",
  "model": "spark-x2.6",
  "reasoning_effort": "high",
  "prompt_directives": {
    "default": ["sites-skills"],
    "overrides": {"<不希望引用的用例编号>": []}
  }
}
```

框架计划使用相同的 `prompt_directives`，配置单元另外按原协议填写 `harness: astronstudio`、模型及模板。插件名不包含 `@`；平台界面允许粘贴 `@sites-skills` 并规范化为插件名。最多引用 12 个不同插件。

- 没有逐题覆盖：继承单元默认引用。
- 逐题设为 `[]`：本题不追加引用；恢复继承则删除该覆盖键。
- 关闭或跳过预处理：只影响预处理方案，不清空引用。
- 已配置插件替换时，可把替换目标作为快捷候选，也可以引用另一个预装插件。
- 未配置引用时，原题 Prompt 字节、摘要与上传内容保持不变；原题自己包含的文本也不会被删除。

Web 仍追加原有的 `[评测环境插件]` / `可用 Web 插件：@名称` 文本，通用场景使用 `可用插件：@名称`。这属于显式提示，实际是否调用插件仍以原生轨迹为准。

## 可用性与版本见证

执行顺序为基础准备、可选预处理、材料上传、引用插件核验、轨迹基线、派发。

引用核验不执行插件安装或替换。它定位当前 AStudio 的实际 ACode Home，查询插件目录及启用配置，并记录名称、市场、清单版本、缓存版本、来源路径和源码摘要。清单版本与缓存槽版本分别记录，避免把同身份替换后仍保留的缓存槽误当成实际插件版本。

独立 app-server 无法继承桌面的目录登录时，远程缓存身份与启用配置作为有明确标签的回退证据：`availability_evidence=remote-cache-and-config`，`runtime_observed=false`；缺少显式开关时标记 `enabled_source=cache-default`，不声称已观察到模型使用插件。接口明确显示未安装或禁用时不会通过缓存覆盖该状态。

未安装、禁用、身份不一致、同名多来源或多个无法确定的缓存版本都会给出明确错误，题目不派发。当前支持可定位安装目录的插件；没有可核验安装目录的远程应用来源返回“不支持此来源”，不会伪装成已验证。

执行结束后再次核对版本、来源和源码摘要。Python 生成的 `__pycache__/*.pyc` 不计入源码变化，其他文件保持检查。发生漂移时保留派发前记录与观察结果，不生成可评分的就绪回执。引用核验预算计入准备阶段，原生任务时限不包含这部分时间。

核验记录保存在 `metadata/prompt-plugins-before.json` 和 `metadata/prompt-plugins.json`；执行详情显示结果。新就绪回执绑定核验文件 SHA-256，恢复、评分交接及导出继续验证该来源。

## 历史兼容

新能力标识为 `execution-independent-plugin-mentions-v1`。旧的 `unit.preprocessing.prompt_directives` 输入仍可读取；同时提交新旧字段且不一致时拒绝请求。内部冻结仍复用 `preprocessing.json`，并用 `prompt_plugin_validation: installed-plugin-v1` 标识新语义，不要求存在预处理动作或附件。

旧执行器仅有 `execution-prompt-plugin-mentions-v1` 时，平台保留原先的 Web 方案候选模式；独立引用预装插件会提示升级执行器。旧冻结批次没有新标识，不追补新核验记录，也不改变原已发送 Prompt。
