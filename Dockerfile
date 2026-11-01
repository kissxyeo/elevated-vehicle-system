FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

# OpenCV / torch 运行所需的系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装 CPU 版 torch（与本地已验证版本一致），避免拉取 CUDA 版本
RUN pip install torch==2.14.1 torchvision==0.29.1 \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt && pip install gunicorn==23.0.0

COPY . .

RUN mkdir -p static/uploads

EXPOSE 7860

# 必须单 worker：视频识别任务是进程内后台作业，多 worker 会查不到任务
CMD gunicorn -w 1 -k gthread --threads 8 --timeout 300 \
    -b 0.0.0.0:${PORT:-7860} app:app
