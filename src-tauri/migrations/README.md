# Migrations

The authoritative SQL migrations for this application live with the component
that owns the schema:

```
forensic-engine/wfs_engine/migrations/
  0001_init.sql        core tables, provenance tables, FTS5 virtual table + triggers
  0002_embeddings.sql  optional local vector index for semantic retrieval
```

They are applied by the Python engine on every start (`db.migrate()`, tracked in
`schema_migrations`), which is why they are not duplicated here: two copies of a
schema is a drift bug waiting to happen.

The Rust shell intentionally has no schema responsibilities — it never opens the
database. This folder documents that boundary so the required `src-tauri/`
structure is not mistaken for a second source of truth.

Adding a migration:

1. create `forensic-engine/wfs_engine/migrations/000N_name.sql`;
2. append it to the ordered list in `wfs_engine/db.py`;
3. add a migration test in `forensic-engine/tests/integration/`;
4. verify `python -m wfs_engine.cli migrate` on a copy of an existing database.
