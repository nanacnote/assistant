# Upgrade Guide

## Before upgrade

1. Back up current data:

```bash
cd matrix
tar -czf backup-pre-upgrade-$(date +%F).tar.gz data/synapse data/postgres
```

2. Review release notes for Synapse and Postgres image changes.

## Upgrade steps

1. Pull new images:

```bash
cd matrix
docker compose pull
```

2. Restart stack with updated images:

```bash
docker compose up -d
```

3. Verify health:

```bash
./scripts/healthcheck.sh
```

4. Validate assistant login and room message flow.

## Rollback

If upgrade fails:

1. Stop containers:

```bash
docker compose down
```

2. Restore backup archive for `data/synapse` and `data/postgres`.

3. Restart stack and re-run `./scripts/healthcheck.sh`.
