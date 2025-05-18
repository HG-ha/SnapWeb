FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 创建并激活虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制依赖文件
COPY requirements.txt .
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple
RUN pip config set install.trusted-host mirrors.aliyun.com
RUN pip install --upgrade pip
# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装Playwright浏览器
RUN python -m playwright install chromium --with-deps

# 复制应用程序代码
COPY . .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_CHROMIUM_NO_SANDBOX=1
ENV PLAYWRIGHT_FORCE_SYSTEM_FONTS=1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "run.py"]