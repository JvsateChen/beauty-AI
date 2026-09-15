# 采选美妆 AI · 后端（FastAPI）
# 多阶段构建：先装依赖到独立 layer，再拷贝源码，源码改动不会触发重装依赖。
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 依赖层（先复制 requirements，最大化利用构建缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 源码层
COPY . .

# 非 root 运行；数据目录需可写（SQLite / 日志）
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 存活探针走 /healthz（不查库），就绪探针走 /readyz（查库 + 数据源装配）
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

# 单 worker：价格轮询调度器是**进程内**的，多 worker 会各起一个调度器导致重复推送。
# 需要横向扩容时，把轮询拆成独立进程（POLL_ENABLED=false + 单独跑 worker 脚本），
# 再给 Web 实例加 --workers。
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
