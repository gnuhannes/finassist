import { ApiError } from "./client";

export async function restoreSqlite(file: File): Promise<void> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch("/api/restore/sqlite", {
    method: "POST",
    body: formData,
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body);
  }
}

export async function deleteTransactions(): Promise<{ deleted: number }> {
  const res = await fetch("/api/data/transactions", {
    method: "DELETE",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<{ deleted: number }>;
}

export async function wipeAllData(): Promise<{ deleted: number }> {
  const res = await fetch("/api/data", {
    method: "DELETE",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<{ deleted: number }>;
}
