# Database Migrations

This project uses **Alembic** to manage the SQLite schema.

## Apply migrations

Run migrations to the latest version:

```bash
cd api
make migrate
```

Equivalent:

```bash
poetry run alembic upgrade head
```

## Create a new migration (autogenerate)

1. Update the SQLModel models (tables/columns/indexes/constraints)
2. Generate a migration:
   ```bash
    cd api
    poetry run alembic revision --autogenerate -m "describe change"
    ```
3. Review the generated migration file in `api/alembic/versions/`
4. Commit it together with the model changes

## Policy: no schema drift
The repository must never contain "schema drift" between models and migrations.

CI enforces this via:
```bash
cd api
make check-migrations

```

If Alembic autogenerate would produce operations (e.g. `op.add_column`, `op.create_table`, ...),
CI fails and you must commit a real migration.

## Fresh local database (development)
If you want a clean database:
- Delete the SQLite file (location depends on your setup / DATABASE_URL)
- Recreate schema by running:
    ```bash
    cd api
    make migrate
    ```
  
## CI database isolation
CI can override the database via `DATABASE_URL` (SQLite URL), e.g.:
```bash
DATABASE_URL=sqlite+aiosqlite:///.../api/.ci/my_private_finances.sqlite
```

Alembic uses the same configuration as the app (`my_private_finances.config.Settings`):
`DATABASE_URL` if set, otherwise a SQLite file under `DATA_DIR` (default `data/`). The
`sqlalchemy.url` in `alembic.ini` is only a placeholder and is always overridden at runtime.