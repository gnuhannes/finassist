import { apiDelete, apiRequest } from "./client";

export async function restoreSqlite(file: File): Promise<void> {
  const formData = new FormData();
  formData.append("file", file);
  await apiRequest<{ ok: boolean }>("/api/restore/sqlite", {
    method: "POST",
    body: formData,
    // A restore recreates the DB file; give it room.
    timeoutMs: 120_000,
  });
}

export function deleteTransactions(): Promise<{ deleted: number }> {
  return apiDelete<{ deleted: number }>("/api/data/transactions");
}

export function wipeAllData(): Promise<{ deleted: number }> {
  return apiDelete<{ deleted: number }>("/api/data");
}
