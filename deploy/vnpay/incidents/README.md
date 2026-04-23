# LiteLLM Gateway — Incident Library (VNPAY)

Thư mục này chứa post-mortem cho các sự cố đã xảy ra với VNPAY LiteLLM
Gateway. Mỗi file = 1 incident, được sync định kỳ vào GoClaw Knowledge Vault
qua `litellm-docs-syncer-agent` (cron 4h) và `litellm-ops-agent` / `litellm-helper-agent`
sẽ trích dẫn khi debug.

## Naming convention

`YYYY-MM-DD-<slug>.md` — ngày là ngày sự cố xảy ra (ICT), slug dùng kebab-case.

Ví dụ: `2026-04-17-postgres-initdb-data-loss.md`.

## Mandatory sections

Mỗi incident file PHẢI có đủ các section sau (cho Knowledge Vault index ổn định):

```markdown
---
title: <one-line title>
date: YYYY-MM-DD
severity: low | medium | high | critical
components: [<postgresql>, <litellm>, <pgbouncer>, ...]
tags: [<keyword>, ...]
---

# <Title>

## Summary

Một đoạn ngắn (3–5 câu) mô tả sự cố, tác động, và resolution.

## Timeline (ICT)

- `HH:MM` — observation / action

## Root Cause

Phân tích kỹ thuật nguyên nhân gốc (không chỉ triệu chứng).

## Impact

- Downtime: ...
- Data loss: ...
- Users affected: ...

## Resolution

Các bước khắc phục đã làm, theo thứ tự.

## Lessons Learned

Gạch đầu dòng các bài học và cải tiến sẽ áp dụng.

## Prevention / Follow-ups

- [ ] Task 1
- [ ] Task 2
```

## Sync vào Vault

Files ở `deploy/vnpay/incidents/*.md` sẽ được `litellm-docs-syncer-agent` rsync
vào `/app/workspace/litellm-shared/incidents/` trong goclaw pod. VaultSyncWorker
ingest qua fsnotify, tag `type=incident, scope=shared, source=litellm-repo`.

Cron trigger: mỗi 4 giờ ICT (`0 */4 * * *`). Manual sync: send message
`Run sync` tới `@LiteLLMGateway_bot` → dispatch `litellm-docs-syncer-agent`.

## Related

- Spec: `docs/superpowers/specs/2026-04-23-litellm-support-agents-design.md`
  trong repo `Agentic Framework` (nội bộ)
- Plan: `docs/superpowers/plans/2026-04-23-litellm-support-agents.md`
