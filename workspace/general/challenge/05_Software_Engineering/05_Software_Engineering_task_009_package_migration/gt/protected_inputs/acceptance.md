# H049 src迁移与离线兼容合同 v1

完成batchstamp-h049 2.0.0的src布局迁移。仅可修改/按许可删除或填充mutable_paths.json中的源码和pyproject；required_sources必须交付。所有资源、测试、输入、LICENSE、锁定offline_wheels及工具保护不变。允许不同内部实现/资源API，不匹配参考代码或固定SQL/目录示例代替运行。

安装包须由project/src/batchstamp和src/legacy_stamp.py构建；保留batchstamp新console、stamp-old旧console、python -m batchstamp、python -m legacy_stamp以及legacy_stamp.run/main导入。旧flag --source/--settings与新--input/--config等价。仓库legacy_cli.py从任意cwd也须可运行，可按脚本__file__定位本项目src；安装后的所有模块/资源须实际来自临时target，不可读取原源码或依赖cwd偶然存在。

run(records,config=None)返回JSON对象ids(按id排序)、total、label、config(规范化后含未知键)、banner。包资源defaults.json为默认配置，banner.txt为原样文字去末尾换行。threshold→min_amount、prefix→label、allow_null→include_null_region；同一配置已出现新键即使0/False/空串/None仍胜出，旧键移除。被新键遮蔽的旧无效值忽略。默认与配置浅覆盖；未知键保留，不改records/config。min_amount可非bool有限数字或None(None=不设阈值)，scale为非bool有限数字(0有效)，label为str，include_null_region为bool；无效配置/记录抛ValueError。保留amount>=min_amount且(region非None或include_null_region)的记录，total为amount和乘scale。记录id为唯一非空str，amount为非bool有限数字，region为str或None。

CLI正常退出0，仅stdout一条上述JSON；错误输入/配置退出2，stderr一条{"error":"invalid_input"}，不输出成功JSON。输入UTF-8、路径可含空格/中文，配置与记录只读。无网络、真实数据、账号或系统配置访问。

必须实际在预置Python3.11和3.12各自构建、临时安装并从异cwd/非ASCII路径核新旧入口、资源与配置。offline_wheels包含本机已有的原始pip24/setuptools79 wheel，SHA与所有许可证/厂商声明保留；工具只解压构建工具到本题临时目录，并将待测wheel安装到本题target，无外部依赖、宿主pip安装或联网。禁止editable安装、安装到当前全局环境或以PYTHONPATH指回checkout蒙混。

执行python -B tools/verify_install.py（可显式--python311/--python312指定已存在解释器），生成results/install_matrix.json，保留构建/安装/入口命令、cwd/returncode/stdout/stderr、wheel SHA、实际module origin、源码/保护输入SHA与两版事实。再写results/migration.md说明改动、兼容入口、真实验证及限制；不得假称未运行版本通过。公开tests_public只是兼容烟雾样本，不代替隔离安装。所有额外报告仅results；自动__pycache__、build、*.egg-info产物允许出现于临时副本，原输入不应被改。GT不提供给候选。
