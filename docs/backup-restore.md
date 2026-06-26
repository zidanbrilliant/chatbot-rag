# Backup & Restore

## What to back up

| Data | Location | Criticality |
|---|---|---|
| PostgreSQL | Docker volume `pgdata` | HIGH — users, chat history, audit logs, documents metadata |
| Qdrant vectors | Docker volume `qdrant_data` | HIGH — knowledge base embeddings |
| Uploaded files | `./data/` on host | MEDIUM — source docs (re-ingestable) |
| Environment | `.env` file | HIGH — secrets, config |

## Backup script

```bash
#!/bin/bash
# save as: scripts/backup.sh
# run daily via cron: 0 2 * * * /opt/chatbot-rag/scripts/backup.sh

set -e
BACKUP_DIR="/var/backups/chatbot/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# PostgreSQL
docker compose exec -T db pg_dump -U postgres chatbot | gzip > "$BACKUP_DIR/db.sql.gz"

# Qdrant — create snapshot via API
SNAPSHOT_NAME="backup_$(date +%s)"
curl -X POST "http://localhost:6333/collections/company_knowledge_base/snapshots" \
  -H "Content-Type: application/json" \
  -d "{\"snapshot_name\": \"$SNAPSHOT_NAME\"}"
# Snapshot file lives in qdrant_data volume
docker compose exec -T qdrant ls /qdrant/snapshots/$SNAPSHOT_NAME/ 2>/dev/null || true

# Uploaded files
tar czf "$BACKUP_DIR/data.tar.gz" ./data

# Env (secrets!)
cp .env "$BACKUP_DIR/env.backup"
chmod 600 "$BACKUP_DIR/env.backup"

# Retention: delete backups older than 30 days
find /var/backups/chatbot -type d -mtime +30 -exec rm -rf {} +

echo "Backup complete: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"
```

## Qdrant snapshot via API

```bash
# Create snapshot
curl -X POST "http://localhost:6333/collections/company_knowledge_base/snapshots" \
  -H "Content-Type: application/json" -d '{}'

# List snapshots
curl "http://localhost:6333/collections/company_knowledge_base/snapshots"

# Download snapshot
curl -O "http://localhost:6333/collections/company_knowledge_base/snapshots/<snapshot_name>.snapshot"
```

## Restore

### Full restore from backup

```bash
#!/bin/bash
# save as: scripts/restore.sh
# usage: ./restore.sh /var/backups/chatbot/20260101_020000

set -e
BACKUP_DIR="$1"
if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
  echo "Usage: $0 <backup_directory>"
  exit 1
fi

# Stop services (preserve volumes)
docker compose stop backend worker frontend

# Restore PostgreSQL
gunzip -c "$BACKUP_DIR/db.sql.gz" | docker compose exec -T db psql -U postgres chatbot

# Restore Qdrant from snapshot (upload then recover)
SNAPSHOT_FILE=$(find "$BACKUP_DIR" -name "*.snapshot" | head -1)
if [ -n "$SNAPSHOT_FILE" ]; then
  curl -X PUT "http://localhost:6333/collections/company_knowledge_base/snapshots/upload?priority=snapshot" \
    -H "Content-Type: application/octet-stream" \
    --data-binary @"$SNAPSHOT_FILE"
  curl -X POST "http://localhost:6333/collections/company_knowledge_base/snapshots/recover" \
    -H "Content-Type: application/json" -d '{}'
fi

# Restore files
tar xzf "$BACKUP_DIR/data.tar.gz" -C ./

# Restore env
cp "$BACKUP_DIR/env.backup" .env

# Restart everything
docker compose up -d
```

### Restore PostgreSQL only

```bash
docker compose stop backend worker
gunzip -c backup.sql.gz | docker compose exec -T db psql -U postgres chatbot
docker compose start backend worker
```

### Restore Qdrant only

```bash
docker compose stop backend worker
curl -X PUT "http://localhost:6333/collections/company_knowledge_base/snapshots/upload?priority=snapshot" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @snapshot.snapshot
curl -X POST "http://localhost:6333/collections/company_knowledge_base/snapshots/recover" \
  -H "Content-Type: application/json" -d '{}'
docker compose start backend worker
```

### After restore: backfill access_level

Old Qdrant points (pre-P0) lack `access_level` field. After restore:

```bash
docker exec chatbot-rag-backend-1 python /app/backfill_access_level.py
```

Idempotent. Sets `access_level: internal` on every point missing it.

## Disaster recovery checklist

- [ ] Verify backup ran in last 24h: `ls -lt /var/backups/chatbot/ | head`
- [ ] Verify backup file sizes look right (DB > 1MB, Qdrant > 10MB for typical KB)
- [ ] Verify Qdrant snapshot API responds: `curl http://localhost:6333/snapshots`
- [ ] Test restore in staging monthly
- [ ] Keep `.env` in secret manager (Vault, AWS Secrets Manager), not just on disk
- [ ] Document RTO (recovery time objective): ~30 min for full restore
- [ ] Document RPO (recovery point objective): 24h (daily backup)

## Monitoring backup health

```bash
# Cron alert if backup missing for > 26h
LAST_BACKUP=$(find /var/backups/chatbot -name "db.sql.gz" -mtime -1 | head -1)
if [ -z "$LAST_BACKUP" ]; then
  echo "ALERT: No backup in last 24h" | mail -s "Chatbot backup failed" ops@example.com
fi
```

## Off-site backup

```bash
# After local backup, sync to S3
aws s3 sync /var/backups/chatbot/ s3://chatbot-backups/ --delete

# Or rsync to remote
rsync -az /var/backups/chatbot/ backup-server:/backups/chatbot/
```
