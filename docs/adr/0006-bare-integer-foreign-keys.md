# ADR 0006: Bare integer foreign keys, no SQLModel `Relationship()`

Date: 2026-09-08
Status: Accepted

***

## Context

Every model in `api/my_private_finances/models/` stores its foreign keys as
plain integer columns:

```python
class Transaction(TransactionBase, table=True):
    account_id: int = Field(foreign_key="account.id", index=True)
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")
```

There is no `Relationship()` anywhere — no `Transaction.account`,
`Category.children`, `Budget.category`. Route and service code that needs a
related row loads it explicitly (`await session.get(Account, tx.account_id)`),
and joins in the reporting layer are written against model columns / the
`services.reporting.table(Model).c.*` helper, not relationship attributes.

The architecture review (2026-09-08, finding A4) flagged this as worth writing
down: it is a deliberate choice with a real, recurring cost, and a new
contributor will otherwise assume relationships were simply forgotten.

## Decision

**Keep foreign keys as bare integer columns. Do not add SQLModel /
SQLAlchemy `Relationship()` attributes.**

Related data is loaded explicitly where it is needed:

- single parent → `await session.get(Model, fk_id)`
- batch → `select(Model).where(Model.id.in_(ids))` then a dict lookup
  (see `routes/transfers.py::_load_related`, `routes/budgets.py`)
- aggregate joins → explicit `select(...).join(...)` /
  `select_from(table(A).outerjoin(table(B), ...))` in `services/reporting.py`

## Rationale

1. **Async lazy-load is a foot-gun.** With an `AsyncSession`, touching an
   unloaded relationship attribute (`tx.account.name`) raises
   `MissingGreenlet` at runtime rather than lazy-loading. Avoiding it requires
   remembering `selectinload` / `joinedload` on every query, and forgetting is
   a production error, not a test failure. Bare FKs make the I/O explicit and
   impossible to trigger by accident.
2. **`expire_on_commit=False`** (our session config, needed so response
   serialization can read attributes after `commit()`) interacts badly with
   relationships — stale collections after a commit are easy to produce.
3. **The object graph is shallow.** The deepest chain is
   `Transaction → Category → parent Category`. The explicit-load boilerplate is
   bounded and lives in a handful of `_load_related`-style helpers.
4. **Queries stay legible.** Reporting SQL is already explicit Core-style
   `select`s; relationships would not simplify them.
5. **FKs are still enforced.** `PRAGMA foreign_keys=ON` is set per connection
   (`db.py`), and `ON DELETE` semantics are being made explicit separately
   (#117). Referential integrity does not depend on ORM relationships.

## Consequences

**Cost (accepted):**

- Every "give me the related row" needs an explicit query. N+1 is possible if a
  loop calls `session.get` per item — the mitigation is the batch-load helper
  pattern, which must be used consciously.
- No cascade-on-delete via the ORM `cascade=` option; delete ordering is
  hand-written (`routes/data_management.py::wipe_all_data` deletes in FK-safe
  order). #117 moves the cascade decision to the database.
- Tooling that introspects relationships (some admin / GraphQL generators)
  won't see them.

**Benefit:**

- No `MissingGreenlet` class of bug.
- Data access is grep-able: every DB read is a visible `select` / `session.get`.
- Models are plain data; no query-strategy decisions embedded in them.

## Revisit if

- The object graph deepens materially (3+ hops used across many call sites), or
- We adopt a sync read-path (e.g. a reporting worker) where lazy-load is safe,
  making selective `Relationship()` use low-risk.
