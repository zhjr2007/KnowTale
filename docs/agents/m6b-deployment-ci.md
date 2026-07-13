# M6b: 部署增强 & CI/CD

## 目标

优化 Docker 构建流程、增强生产环境部署配置、设置 GitHub Actions 自动化 CI 流水线、添加数据备份方案。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `Dockerfile` — 应用容器定义
  - `docker-compose.yml` — 多服务编排
  - `.env.example` — 环境变量模板
  - `.gitignore` — Git 忽略规则
  - `requirements.txt` — Python 依赖
  - 需新建 `.github/workflows/ci.yml`
  - 需新建 `scripts/backup.sh`
  - 需新建 `docker-compose.prod.yml`
  - 需新建 `.dockerignore`
- **现有配置**:
  - Dockerfile: python:3.11-slim, pip install, uvicorn
  - docker-compose.yml: app + chroma + mineru
  - 开发模式无 healthcheck, restart, 多阶段构建
- **部署目标**: Linux 服务器（Docker Compose）

## 实现任务

### 1. [Docker] 多阶段构建优化

重写 `Dockerfile`：

```dockerfile
# ---- Build Stage ----
FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/login || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

新建 `.dockerignore`：

```
__pycache__
*.pyc
*.pyo
.git
.gitignore
.env
data/
uploads/*.db
README.md
NOTICE.md
docs/
public/plugins/
edu-modules/
```

### 2. [Docker] 生产环境 Compose

新建 `docker-compose.prod.yml`：

```yaml
version: "3.8"

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    depends_on:
      chroma:
        condition: service_healthy
      mineru:
        condition: service_started
    restart: unless-stopped
    networks:
      - knowtale-net
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  chroma:
    image: chromadb/chroma:latest
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - chroma_data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - CHROMA_SERVER_CORS_ALLOW_ORIGINS=["*"]
      - ANONYMIZED_TELEMETRY=FALSE
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    networks:
      - knowtale-net

  mineru:
    image: opengsg/mineru:latest
    ports:
      - "127.0.0.1:8001:8001"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped
    networks:
      - knowtale-net

volumes:
  chroma_data:

networks:
  knowtale-net:
    driver: bridge
```

注意: chromium（用于 PDF 打印）、Redis（缓存）等 非必需依赖 **不加入** compose，保持精简。

### 3. [CI] GitHub Actions 流水线

新建 `.github/workflows/ci.yml`：

```yaml
name: CI

on:
  push:
    branches: [main, feat-*]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      chroma:
        image: chromadb/chroma:latest
        ports:
          - 8000:8000

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Lint with ruff
        run: |
          pip install ruff
          ruff check app/ --output-format=github

      - name: Check import
        run: |
          python -c "from app.main import app; print('App imported OK')"
        env:
          BAILIAN_API_KEY: ${{ secrets.BAILIAN_API_KEY || '' }}
          CHROMA_HOST: localhost
          CHROMA_PORT: 8000

      - name: Build Docker image
        run: docker build -t knowtale-app .

  # 可选（需要 Docker Hub 密钥）:
  # deploy:
  #   needs: test
  #   if: github.ref == 'refs/heads/main'
  #   runs-on: ubuntu-latest
  #   steps:
  #     - name: Deploy to server
  #       run: |
  #         # SSH deploy script
```

### 4. [部署] 数据备份脚本

新建 `scripts/backup.sh`：

```bash
#!/bin/bash
# 知喻 数据备份脚本
# 用法: ./scripts/backup.sh [backup_dir]

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/knowtale_$TIMESTAMP"

mkdir -p "$BACKUP_PATH"

# 备份 SQLite 数据库
if [ -f data/knowtale.db ]; then
    cp data/knowtale.db "$BACKUP_PATH/knowtale.db"
    echo "✓ 数据库已备份"
fi

# 备份上传文件
if [ -d uploads ]; then
    cp -r uploads "$BACKUP_PATH/uploads"
    echo "✓ 上传文件已备份"
fi

# 压缩
cd "$BACKUP_DIR"
tar -czf "knowtale_$TIMESTAMP.tar.gz" "knowtale_$TIMESTAMP"
rm -rf "knowtale_$TIMESTAMP"

echo "✓ 备份完成: $BACKUP_DIR/knowtale_$TIMESTAMP.tar.gz"
```

新建 `scripts/backup.ps1`（Windows 环境）：

```powershell
param([string]$BackupDir = "./backups")
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = Join-Path $BackupDir "knowtale_$timestamp"
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
if (Test-Path "data/knowtale.db") {
    Copy-Item "data/knowtale.db" (Join-Path $backupPath "knowtale.db")
    Write-Host "✓ 数据库已备份"
}
if (Test-Path "uploads") {
    Copy-Item -Recurse "uploads" (Join-Path $backupPath "uploads\")
    Write-Host "✓ 上传文件已备份"
}
Compress-Archive -Path "$backupPath\*" -DestinationPath "$BackupDir\knowtale_$timestamp.zip"
Remove-Item -Recurse $backupPath
Write-Host "✓ 备份完成: $BackupDir\knowtale_$timestamp.zip"
```

### 5. [配置] 环境变量模板更新

更新 `.env.example`，增加注释说明生产环境配置项：

```bash
# ===== 必填 =====
BAILIAN_API_KEY=your-api-key-here

# ===== 数据库 =====
# DATABASE_URL=sqlite+aiosqlite:///./data/knowtale.db  # 开发用 SQLite
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/knowtale  # 生产用 PostgreSQL（需要额外安装）

# ===== 安全 =====
# SECRET_KEY=your-secret-key-here         # 生产环境必须修改！
# JWT_EXPIRATION_HOURS=168                # JWT 过期时间（7天）

# ===== 外部服务 =====
# CHROMA_HOST=localhost
# CHROMA_PORT=8000
# MINERU_URL=http://localhost:8001

# ===== LLM =====
# BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# LLM_MODEL=qwen-plus
# EMBEDDING_MODEL=text-embedding-v3
# RERANK_MODEL=text-rerank-v1

# ===== 应用 =====
# APP_NAME=知喻
# DEBUG=false
```

### 6. [配置] Nginx 反向代理参考（文档）

新建 `docs/nginx-example.conf`：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # 静态资源缓存
    location /static/ {
        proxy_pass http://127.0.0.1:8000;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 7. [Git] .gitignore 更新

更新 `.gitignore`，增加：

```
# 部署相关
docker-compose.override.yml

# 备份
backups/

# 运行时数据（保留 data/.gitkeep、uploads/.gitkeep）
data/*.db
data/*.db-journal
data/*.db-wal
uploads/*
!data/.gitkeep
!uploads/.gitkeep
```

## 验收标准

- [ ] Docker 多阶段构建成功，镜像体积合理（<500MB）
- [ ] `docker-compose -f docker-compose.prod.yml up -d` 启动正常
- [ ] healthcheck 正常工作（curl /login 返回 200）
- [ ] GitHub Actions CI 通过（ruff lint + import check + Docker build）
- [ ] 备份脚本可执行，备份文件正确生成
- [ ] .env.example 注释完善
- [ ] .gitignore 不遗漏运行时文件也不误 commit 敏感文件
- [ ] Nginx 配置对 SSE 有正确的 proxy_buffering off 设置

## 参考代码模式

- Docker 多阶段构建: [Docker docs multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- Docker Compose healthcheck: [Docker Compose healthcheck](https://docs.docker.com/compose/compose-file/#healthcheck)
- GitHub Actions setup-python: [actions/setup-python](https://github.com/actions/setup-python)
- Ruff lint: `ruff check app/ --output-format=github`
- Nginx SSE 代理: 需要 `proxy_buffering off; proxy_read_timeout 86400s;`
