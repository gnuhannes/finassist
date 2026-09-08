import type { components } from "./schema";

/**
 * Shorthand for the backend's OpenAPI component schemas (#112).
 *
 * `schema.d.ts` is generated from `api/openapi.json` by `make openapi`; CI's
 * `check-openapi` fails if it drifts. Prefer `Schemas["FooRead"]` over a
 * hand-written type in `src/lib/api/*.ts`.
 */
export type Schemas = components["schemas"];
