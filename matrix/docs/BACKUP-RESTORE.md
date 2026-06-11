# Backup and Restore

## Back up

Run from `matrix/`:

```bash
tar -czf backup-synapse-$(date +%F).tar.gz data/synapse data/postgres
```

This captures Synapse state and Postgres data volumes.

## Restore

1. Stop stack:

```bash
docker compose down
```

2. Restore files:

```bash
tar -xzf backup-synapse-YYYY-MM-DD.tar.gz
```

3. Start stack:

```bash
bash ../scripts/stack-up.sh
```

4. Validate:

```bash
./scripts/healthcheck.sh
```
