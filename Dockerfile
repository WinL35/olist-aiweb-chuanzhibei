# Olist 电商经营决策垂直大模型 —— 可选部署方式（官方未强制，作为复现加分项）
#
# 构建：docker build -t olist-llm .
# 运行：见 docker-compose.yml（一键起 MySQL + 应用）
#
# 注意：镜像内不含 128MB 的 cleaned/*.csv 与原始数据。
# 首次使用需在容器里执行导入脚本（见 README「③ 导数据」）。

FROM python:3.12-slim

ENV PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先只装依赖，利用层缓存：代码改动不会触发重新装包
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码（.dockerignore 已排除 .env、cleaned、算法 CSV、__pycache__、.git）
COPY . .

EXPOSE 8000

# 健康检查：容器就绪判定用 /api/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["python", "启动后端.py"]
