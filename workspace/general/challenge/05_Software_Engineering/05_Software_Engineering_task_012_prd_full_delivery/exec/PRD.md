# 成员管理需求

按 R01→R02/R03→R04/R05→R06/R07/R08/R09→R10/R11→R12 的依赖顺序完成。权限、并发和事务同属后端约束。

## R01 P0 迁移与持久化

PRAGMA user_version=2，重复启动不丢旧成员；真实SQLite提交后跨连接/进程重启保持。

## R02 P1 列表和会话

GET /session使用服务器当前成员角色；GET /members支持q/status/role过滤，稳定id顺序，total等于完整结果。

## R03 P0 创建与规范化

管理员创建；id/email/name/role验证；email规范化后全库唯一（含停用记录），新成员active/version1。

## R04 P0 编辑与权限

管理员可编辑name/email/role，manager只可改active非admin的name，viewer不能写；body中的role不能提权。

## R05 P0 服务器权限

未知actor401，inactive actor403，所有写请求查真实DB角色；审计读取仅admin；UI隐藏按钮不能代替后端拒绝。

## R06 P0 停用与管理员保护

停用为软删除，version+1；停用或降级最后一名active admin返回409 LAST_ADMIN，其他信息不变。

## R07 P0 并发版本

编辑/停用必须给整数version，原子比较当前版本；过期409 VERSION_CONFLICT，无覆盖/审计/receipt。

## R08 P0 幂等与重试

actor+request_key范围内相同规范命令只成功一次，重放返回原data/status/code但replayed=true；改payload409 KEY_REUSE；失败不占key。

## R09 P0 事务审计

每次新成功写入仅追加一条audit，失败/拒绝/重放不追加；成员/审计/receipt原子提交，注入审计失败必须完全回滚。

## R10 P1 前端真实数据与操作

client createController使用transport访问/session及/members，snapshot包含实际rows/actor/form/error/loading；动作能力据角色与行状态。

## R11 P1 前端反馈与安全文本

提交真实POST/PATCH后按服务器结果刷新；失败保持原form并显示code，成功清空；render生成table行和disabled按钮，所有用户文本HTML转义。

## R12 P1 兼容入口与验收

保留GET /health和/legacy-export，启动不依赖cwd；12项追踪、实际tests.txt和handoff绑定最终四源码，不只输出计划。
