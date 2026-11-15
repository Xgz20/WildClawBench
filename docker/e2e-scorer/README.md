# 无头评分运行时

基础镜像按冻结 Score Skill 创建独立 Python 3.11 环境，再使用**同一解释器**
安装其对应的 Chromium。仅安装 Playwright Python 包或 install-deps 不包含浏览器。
构建会运行公开合成 HTML 的离线浏览器预检：点击、键盘、窄窗口、减少动画、
页面网络阻断和截图均须通过，不读取候选或调用模型。

既有运行镜像缺浏览器时，使用独立标签追加修复层：

    docker build --build-arg SCORER_BASE_IMAGE=已冻结的评分镜像 \
      -f browser-runtime.Dockerfile -t 新评分镜像标签 .

保留旧标签及镜像。新评分操作按镜像 ID 冻结配置；已有操作继续使用原配置。
新镜像的 /opt/scoring-browser-preflight/observations.json 保留实际预检记录。
Office 能力由 native-office.Dockerfile 单独提供；正式评分仍执行任务对应的
原生 Office/浏览器预检，环境失败保留为评测异常，不计能力零分。
