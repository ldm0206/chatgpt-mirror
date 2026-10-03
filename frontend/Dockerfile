# 网关镜像（闭源）里自带的是上游那份旧前端，这里把本仓库构建出的管理台覆盖进去。
# 构建前需先在 frontend/ 执行 `npm ci && npm run build`，产物会落在 gateway/static。
ARG BASE_IMAGE=lisa666520/chatgpt-mirror-django:frontend
FROM ${BASE_IMAGE}

# 合并而不是整体替换，保留基础镜像里可能存在的其他静态文件
COPY gateway/static/. /app/static/
