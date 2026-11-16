# Olist 电商经营决策 AI Web 应用 —— 可选部署方式（官方未强制，作为复现加分项）
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

# 直接调用 uvicorn，不经过 启动后端.py。原因有两条，都是容器环境特有的：
#   1) 该脚本是给人在本机双击用的，内含 input() 交互提示（密码错误时等输入、
#      出错时「按回车键退出」），容器里没有 TTY，一旦走到分支就抛 EOFError 退出；
#   2) 它固定绑 127.0.0.1，容器内回环地址对外不可达，端口映射 8000 会连不上。
# 因此这里显式绑 0.0.0.0，并关掉 reload（生产/演示不需要热重载）。
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
