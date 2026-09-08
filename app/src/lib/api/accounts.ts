import { apiGet, apiPatch, apiPost } from "./client";
import type { Schemas } from "./schema-helpers";

// Types generated from the backend OpenAPI schema (#112). See schema-helpers.ts.
export type Account = Schemas["AccountRead"];
export type AccountCreatePayload = Schemas["AccountCreate"];
export type AccountUpdatePayload = Schemas["AccountUpdate"];

export function getAccounts(): Promise<Account[]> {
  return apiGet<Account[]>("/api/accounts");
}

export function createAccount(data: AccountCreatePayload): Promise<Account> {
  return apiPost<Account>("/api/accounts", data);
}

export function updateAccount(id: number, data: AccountUpdatePayload): Promise<Account> {
  return apiPatch<Account>(`/api/accounts/${id}`, data);
}
