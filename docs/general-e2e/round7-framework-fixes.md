# Round7 暴露问题的框架修复

本次同步以原仓库ffae2d2c为基线，将生产中验证过的7582b1f0、0a69d734、9fc9117c、9f1f2c6e、ac0458f7和ee86fb5e提交保留原谱系同步到共享仓库，并将原先独立的操作工具接入Skill标准流程。历史冻结发行、round7输入/候选/执行/评分/回传/报告/管理员ZIP不改写；本次只做代码、回归、只读制品回放与新发行构建，不再执行round7任务或创建Judge。

## 问题、原因与处理

| 触发问题 | 直接原因与边界 | 通用修复 |
| --- | --- | --- |
| 自定义模型已配置High，生产探针却拒绝 | 新UI显示“自定义”徽标，显示名与配置模型名是有证明的映射，不能按内置模型正则识别 | 只读回读同账号custom config、execution revision、显式reasoning、连通测试及原生provider绑定；发送前再次检查。只输出白名单字段和账号SHA，不输出凭据，不推断服务端权重/实际high内部行为 |
| 新建任务控件不识别、草稿使导航无效，后续题级联失败 | 新UI aria-label使用“任务”；非空未发送草稿下global new task可能无操作。最初弹窗的具体内容没有完整保留，不推断其原因 | 同时识别明确的task/chat控件；非空草稿立即给出可定位阻断。队列停止补位并观察已受理任务，不因continue-on-terminal-failure把准备故障扩散到后续任务 |
| 原生日志完整但正式归档失败 | 客户端清理provider运行库投影，原采集入口只认库投影；首版适配漏了三个metric来源绑定 | 显式bound-native-provider-log profile，精确绑定SDK、原生保留日志和身份，保留差异与旧失败；archive/resource/finalize/verify-only均验证完整binding引用闭包。不是按“最近日志”选源，也不伪造DB序号 |
| 中间回复被冻结成终稿 | 执行器查询最后一条非流式assistant消息，未按completed turn指明的assistant_message_id绑定；最初临时读取快照未保留，不能进一步断言底层时序或DB损坏 | 新观察器只取completed turn明确指定的同thread/turn非流式终稿；未落盘继续观察同一turn，不冻结commentary或重发。已冻结历史错误只能走显式授权的严格终稿补采profile，保留旧state/record/reply与三源证明 |
| 裁判file URL导航被安全门禁拒绝，整题null | 属于裁判验证环境，没有证明候选缺陷 | Score Skill分发禁网HTML字节观察脚本，Orchestrate v7在创建HTML题Judge前执行原runtime锁与公开fixture预检并冻结环境。独立裁判选操作、看真实截图，仍按原Rubric判分；不改URL策略、不启动服务器/CDP，不声称OS网络隔离。治理策略仍拒绝时不绕行 |
| 实际Prompt一致，却被字面审计误报 | 原生桥XML转义了环境说明中的尖括号，直接substring不再匹配完整Prompt | 标准verify-native-context严格解析codex_delegation/input后比对完整冻结文本/SHA，同时检查thread/cwd/唯一workspace root/model/effort和完成区间。保留原误报，不使用模糊匹配或导出思考正文 |
| 单题重评分后只有一个新submission，无法作为完整60题回传 | 独立rescore编排刻意只含获授权题目；直接拿它替代全量会缩小范围 | compose-rescore-selection验证原/新锁定submission及谱系，保持原题序、执行身份、候选和其余分数，显式选择新attempt，生成独立完整范围选择目录。只做verify-score归档校验，不跑规则、Judge或按高分挑选，不伪造新COMPLETED编排 |
| 管理员接收现有成绩却被要求历史scoring ZIP | 完整生产init会验证原manifest声明的生产输入，接收结果不应初始化该run | prepare-imported-source复制原manifest/report-config后严格import/select，生成本机source/task索引和只读JSON回放argv。不删原制品锁、不伪造包或阶段，不改版本/模型/分数 |

## 版本与标准入口

prepare0.3.2、execute0.14.6（driver0.4.12、queue worker0.1.3）、collect0.11.3（资源组件1.3.3）、orchestrate0.11.10、score0.10.9、run0.7.6、report0.8.10。源码仓库更新不会改变历史已冻结的suite；后续评测必须构建、验证并安装新发行，冻结新catalog/Skill/ZIP SHA。

1. 新任务模型/账号/High回读失败时暂停发送，不换模型或降档。
2. 已知零发送草稿使用execute的prepare_astronstudio_zero_send_ui.mjs：全局原生空闲、唯一原Prompt/Workspace、当前state仍满足零发送契约、原生pristine thread均须证明；先写原件审计，再用Backspace清除并复核。未知、已受理、不确定、外来草稿不处理。
3. 采集原生日志/终稿修复使用collect对应显式profile。新入口不是自动授权；本轮授权不能继承到下轮的证据修复。
4. 新v7 HTML评分任务在preflight验证judge-environment.json。hybrid从规则阶段取得专用runtime；纯语义HTML显式提供browser-runtime-python。公共预检不读候选/GT、不产生分数。
5. 新原生评分聊天就绪后及COMPLETED后调用verify-native-context；初始SDK头未到齐时只等待原thread。allow-running不能证明完成。
6. 明确授权的重评分完成后，用compose-rescore-selection生成完整范围选择，再走run record-submission/package-return及管理员import/select/report。选择目录没有伪造的orchestration-state，不能对它调用编排status。
7. 管理员只接收原成绩时使用prepare-imported-source；跨批次、同unit ID、历史digest/材料签名差异仍需独立严格审计和报告层映射。报告/研发输出继续保留null、真实零分、原记录和补采谱系；规范ZIP为字节权威。

详细操作见各Skill的SKILL.md，以及score的offline-browser-validation、orchestrate的submission-and-rescore与codex-orchestration、run的flow-and-return。

## 证据与验证边界

生产采用的原始审计留在round7外部私有控制根及标准return/研发包。最终原评分选择为60 valid、0 evaluation_error、0 unscored、完整均分94.5715/100；此前null及人工授权修复原件保留。同步仓库不改变这些历史结果。

回归覆盖自定义映射/账号/High漂移、零发送/已受理/不确定草稿、准备失败不级联且在途收尾、completed消息未落盘/streaming/错turn/空终稿、原生日志和终稿补采绑定闭包、XML完整Prompt解码及错模型/根目录拒绝、公开浏览器预检与观察文件漂移、完整范围选择和原身份导入。浏览器集成只跑公开合成fixture；制品集成仅只读验证、复制和JSON复算，不运行候选、规则Worker或Judge。

评分core、rule_worker、评分runtime锁和已审核证据政策的15个保护文件保持原SHA；不修改GT、Rubric、权重或准入例外。新浏览器运行环境不是操作系统隔离证明。未重做真实全60题，也不能凭单机回归保证未来任意客户端/服务端变化均兼容；未知原生形状、配置/身份/引用漂移仍应失败关闭并留下证据。

本次完整 General 回归为 Python 318/318、Node 686/686；另外完成公开 Chromium fixture 预检、真实原生 SDK XML Prompt 元数据回放、完整60题的59原分+1已授权新分选择回放，以及原身份异地导入/JSON报告复算。只读复算均分仍为0.945715，未调用候选、规则Worker或Judge。开发测试使用Python3.11、Node24和仓库requirements.txt声明的依赖；本机冻结runtime缺少的python-dotenv只放入独立测试依赖目录，不改生产runtime锁或全局环境。

在依赖已准备的开发环境复现完整回归：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 python -X utf8 -m unittest discover -s tests/general_e2e
node --test tests/general_e2e/*.test.mjs
```

涉及runtime锁的测试须使用满足冻结score runtime版本的专用Python与Playwright/browser缓存；不能用控制Python替代或为了测试放宽版本校验。首次失败日志、修正后的完整回归日志及制品只读回放证明留在本轮私有审计目录，不把实际候选/分数或SDK正文提交到代码仓库。
