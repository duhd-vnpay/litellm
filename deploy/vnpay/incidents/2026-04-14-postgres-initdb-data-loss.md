---
title: PostgreSQL initdb trigger → toàn bộ LiteLLM data bị xóa
date: 2026-04-14
severity: critical
components: [postgresql, litellm-postgresql, helm, k8s-statefulset]
tags: [data-loss, initdb, configmap, postmortem, irrecoverable]
---

# PostgreSQL initdb trigger → toàn bộ LiteLLM data bị xóa

## Summary

Ngày 2026-04-14, trong khi apply PostgreSQL tuning cho StatefulSet
`litellm-postgresql` (namespace `litellm`), đã mount ConfigMap
`litellm-postgres-tuning` vào path `/docker-entrypoint-initdb.d/tune.sh`. Khi
pod restart, entrypoint của image Bitnami PostgreSQL phát hiện scripts mới
trong `initdb.d/` → trigger initdb path → **xóa sạch PGDATA** trước khi
chạy init scripts. Toàn bộ data production (teams, virtual keys, users, model
configs, spend logs, LLM credentials) mất. Không có WAL archiving, volume
snapshot, hoặc dump trước đó → **không thể recover**. Phải seed lại từ đầu.

## Timeline (ICT)

- `~10:00` — Thiết kế PostgreSQL tuning (shared_buffers, work_mem, wal_buffers,
  checkpoint_completion_target, ...) cho litellm DB
- `~10:30` — Tạo ConfigMap `litellm-postgres-tuning` chứa file `tune.sh` với
  các câu lệnh `ALTER SYSTEM`
- `~10:45` — Patch StatefulSet `litellm-postgresql` thêm volumeMount tới
  `/docker-entrypoint-initdb.d/tune.sh`
- `~10:47` — Pod restart do spec change
- `~10:48` — Entrypoint Bitnami phát hiện scripts mới trong `initdb.d/` →
  chạy initdb path → xóa PGDATA
- `~10:50` — Container khởi động lại với DB rỗng. Tuning scripts chạy, nhưng
  trên cluster trống
- `~11:00` — LiteLLM pods báo lỗi auth / missing schema. Phát hiện data mất
- `~11:15` — Kiểm tra: không có WAL, không có volume snapshot, không có
  `pg_dump` gần thời điểm mất. Xác nhận không thể recover
- `~11:30 – 14:00` — Bootstrap lại litellm DB từ đầu: tạo lại master key,
  teams, virtual keys, users, model configs, LLM credentials. Spend logs lịch
  sử mất vĩnh viễn

## Root Cause

Image Bitnami PostgreSQL (và nhiều base image Postgres khác) trong entrypoint
có branch:

```
if [ -n "$(ls -A /docker-entrypoint-initdb.d/ 2>/dev/null)" ] && \
   [ ! -f "$PGDATA/PG_VERSION" ]; then
  # run initdb, then replay scripts
fi
```

Tuy nhiên khi mount ConfigMap mới vào `initdb.d/`, nếu permissions trên
PGDATA bị lệch (ví dụ: mount options khác, volume remount, hoặc initContainer
`chown` lại volume), entrypoint có thể không nhìn thấy `PG_VERSION` và
re-run initdb — quy trình này **bắt đầu bằng việc xóa/reset PGDATA**.

Nguyên nhân gốc kép:
1. **Mount ConfigMap vào `docker-entrypoint-initdb.d/` là anti-pattern** — path
   này chỉ dành cho one-time bootstrap, không phải runtime config
2. **Không có backup/WAL/snapshot** trước khi patch StatefulSet production →
   zero khả năng recover

## Impact

- **Downtime:** ~3h 30m (pod không serve + thời gian re-bootstrap)
- **Data loss:** IRRECOVERABLE
  - Tất cả teams, virtual keys, users
  - Tất cả model configs + LLM credentials đã lưu trong DB
  - Spend logs lịch sử (request/response/token/spend) từ khi gateway launched
  - Audit logs, usage analytics
- **Users affected:** Toàn bộ consumer của VNPAY LiteLLM Gateway
- **Business:** Không có số liệu usage/cost history cho reporting

## Resolution

### Immediate (re-bootstrap)

1. Rollback patch StatefulSet — gỡ volumeMount `initdb.d/tune.sh`
2. Xác nhận data không thể recover (không WAL, snapshot, dump)
3. Bootstrap lại: chạy Prisma migrate để tạo schema
4. Recreate master key + admin user
5. Seed lại teams, virtual keys, user phân quyền theo danh sách nội bộ
6. Khai báo lại model configs + LLM credentials (Anthropic, OpenAI, VNPAY, ...)

### Apply tuning an toàn (KHÔNG qua initdb)

Dùng `ALTER SYSTEM` + `pg_reload_conf()` — không restart pod, không đụng
PGDATA:

```bash
kubectl exec -n litellm litellm-postgresql-0 -- psql -U litellm -d postgres -c "
  ALTER SYSTEM SET shared_buffers = '512MB';
  ALTER SYSTEM SET work_mem = '32MB';
  ALTER SYSTEM SET maintenance_work_mem = '256MB';
  ALTER SYSTEM SET effective_cache_size = '1536MB';
  ALTER SYSTEM SET wal_buffers = '16MB';
  ALTER SYSTEM SET checkpoint_completion_target = 0.9;
  ALTER SYSTEM SET random_page_cost = 1.1;
  SELECT pg_reload_conf();
"
```

## Lessons Learned

- `docker-entrypoint-initdb.d/` là **one-shot bootstrap path**, KHÔNG dùng
  cho runtime tuning. Bất kỳ mount nào vào path này trên StatefulSet
  production là nguy cơ initdb-reset.
- **Runtime PostgreSQL config → `ALTER SYSTEM` + `pg_reload_conf()`**, không
  qua restart pod. Không cần ConfigMap mount.
- **Mọi thao tác có thể restart PostgreSQL pod production PHẢI có backup
  trước** — `pg_dump` + volume snapshot (nếu CSI driver hỗ trợ) + ghi lại
  WAL position.
- **WAL archiving + PITR (Point-in-Time Recovery) là bắt buộc** cho bất kỳ DB
  production nào mang business data không reproducible.

## Prevention / Follow-ups

- [ ] Bật WAL archiving cho `litellm-postgresql` — cấu hình `archive_mode=on`,
  `archive_command` push WAL tới S3/MinIO
- [ ] Schedule daily `pg_dump` → S3 với retention 30 ngày
- [ ] Thêm CSI volume snapshot schedule (nếu storage class hỗ trợ)
- [ ] Runbook "PostgreSQL tuning" — chỉ dùng `ALTER SYSTEM`, **ban mount vào
  `initdb.d/`**
- [ ] Runbook "Trước khi restart postgres pod" — checklist: backup OK? WAL
  archive current? snapshot gần nhất?
- [ ] Monitoring: alert khi `pg_stat_archiver.last_archived_time` > 15 phút
- [ ] Seed `litellm-ops-agent` SOUL với rule: từ chối đề xuất restart postgres
  pod khi chưa confirm backup với user
