# 合成校园导出服务：修复合同 v1

这是无网络、无数据库、无真实凭据的本地Python练习。fixtures/users.json是可深复制的内存db示例；测试也会传入不同ID、用户名、角色/资源分布的同schema对象。不得写死本夹具名称或以全部拒绝代替修复。保持现有三个模块的公开函数/参数及异常类，可自由重构其内部。

## 账户与会话
- auth.login(db,sessions,username,password)返回非空不重复的不透明字符串token，向sessions添加会话；auth.resolve_session(db,sessions,token)返回**当前db中的用户**的独立dict。
- username必须字符串，去两端空白后casefold匹配；密码为非空字符串，精确比较。未知/歧义用户名、错密码、disabled(enabled非True)、当前用户名出现在同样规范化的db.blacklist内时均抛auth.AuthError。规范化只影响用户名/黑名单，不改密码、用户ID或资源ID。
- 会话保存user_id、expires_at、revoked及可选cached_user。每次导出/resolve均必须检查token真实存在、未撤销、expires_at为非bool数值且严格大于db.now、user_id仍对应唯一当前账户、账户仍启用且未入黑名单。过期、删除账户、变更角色/租户/黑名单立即生效；会话cached_user或请求identity不能授予权限。sessions是服务端存储，request是非可信请求。
- 成功登录的expires_at为db.now+db.session_ttl，revoked=False；会话user_id指向当前账户。不要求特定token格式/内部额外字段；不得覆盖现有token。

## export.export_data(db,sessions,token,resource_id,fields=None)
- 始终自行验证会话，直接调用与routes入口具有相同授权边界。资源不存在抛KeyError；无效会话抛auth.AuthError；越权抛export.ExportDenied；fields格式不合法抛ValueError。
- 所有角色都不能导出其它租户的资源。tenant_admin也只管理自身租户。资源tenant_id与当前用户tenant_id必须相同。
- student：只能导出enrolled_ids含自身id的资源，只返回student_id等于自身id的行。允许字段依次为student_id、display_name、score、feedback。
- teacher：只能导出owner_id为自身id的资源，返回该资源本租户所有行。允许字段依次为student_id、display_name、score、feedback、email。
- tenant_admin：导出本租户任一资源的本租户所有行，允许字段依次为student_id、display_name、score、feedback、email、support_tag。
- auditor与未知角色可以正常登录，但没有任何导出权限。任何角色返回的行都必须满足row.tenant_id==当前用户tenant_id（上游合并可能混入异租户行），并保持输入行顺序。
- fields=None采用本角色上列默认字段顺序；显式fields必须非空list且每项为非空字符串，按首次出现稳定去重。含未知字段、越权字段或internal_note/password_digest等内部字段时整次拒绝(ExportDenied)，不能静默丢弃。非list/空list/非字符串项为ValueError。
- 成功返回{'resource_id':原ID,'fields':有序字段列表,'rows':[仅含所选字段的字典]}。不得修改db、资源行或既有sessions；login添加新会话是唯一允许的状态写入。

## routes
- login_route(db,sessions,request)：成功status=200/body.token；任何AuthError统一401/body.error=unauthorized。
- export_route(db,sessions,request)：读token/resource_id/fields，成功200/body为上列导出对象。AuthError→401/unauthorized，ExportDenied→403/forbidden，KeyError→404/not_found，ValueError→400/bad_request。输出始终{'status':整数,'body':对象}。
- request中的identity/role/tenant_id/user_id及其它额外键不能覆盖服务端身份，也不能写sessions。请求为普通dict；不存在的token、过期与撤销返回401。不要把内部编程错误伪装为200。认证先于资源/字段判断。

## 修改与验证
只能修改project/auth.py、project/export.py、project/routes.py。project/__init__.py、fixtures、contract.md、requirements.lock、tests和tools均受保护；不安装依赖、不联网，所有报告只写results。忽略Python自动__pycache__/*.pyc；不能增添其它源码模块来扩大交付范围。

运行公开测试：python -B -m unittest discover -s tests -v。它只覆盖正常使用的烟雾样本，原工程也可能通过，不代表安全边界已正确。
生成实际结果：python -B tools/run_security_tests.py。它实际执行上述测试，将JSON格式（扩展名保留.txt）的结果写入results/security_tests.txt：schema_version、command、returncode、source_sha256、test_results、stdout、stderr。允许增加results报告。最终报告必须绑定最终三份源码SHA；改完代码后重新运行。评分侧还会在独立副本实际测试行为，不凭自述、测试数量或补丁关键词评分。
