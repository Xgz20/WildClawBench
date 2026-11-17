# AgentCube 相关源码定位

涉及 AgentCube、wgui 或 Windows 沙箱的端到端评测开发与排查时，先读取本机
`~/Tool/AStudioEval/context/source-map.md`，再阅读本仓库的
`docs/guides/agentcube-source-navigation.md`。

地图中的路径只供源码定位，不是执行器运行配置。地图缺失或路径不存在时，先使用
本仓库导航，并报告具体缺失项；不要猜用另一台 Mac 的路径或全盘搜索。

引用外部仓库默认用于只读排查。记录相关 checkout 的 HEAD 和工作区状态，并核对
实际执行器、控制器及镜像版本；未经当前任务授权，不修改、切换或部署外部仓库。
