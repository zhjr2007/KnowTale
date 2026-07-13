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
