import { ApiError } from "./client";

export type ImportErrorDetail = {
  row?: number | null;
  field?: string | null;
  raw_value?: string | null;
  message: string;
  hint?: string | null;
  unexpected: boolean;
};

export type ImportResult = {
  total_rows: number;
  created: number;
  skipped: number;
  duplicates: number;
  failed: number;
  errors: ImportErrorDetail[];
  errors_truncated: boolean;
};

export type ImportCsvParams = {
  file: File;
  accountId: number;
  delimiter?: string;
  dateFormat?: string;
  decimalComma?: boolean;
  profileId?: number;
};

export async function importCsv(params: ImportCsvParams): Promise<ImportResult> {
  const formData = new FormData();
  formData.append("file", params.file);

  const query = new URLSearchParams({ account_id: String(params.accountId) });
  // Only send format params when they're explicitly overriding (backend treats absent = use profile default)
  if (params.delimiter !== undefined) query.set("delimiter", params.delimiter);
  if (params.dateFormat !== undefined) query.set("date_format", params.dateFormat);
  if (params.decimalComma !== undefined) query.set("decimal_comma", String(params.decimalComma));
  if (params.profileId !== undefined) query.set("profile_id", String(params.profileId));

  const res = await fetch(`/api/imports/csv?${query}`, {
    method: "POST",
    body: formData,
  });

  const body = await res.json().catch(() => null);

  if (!res.ok) {
    throw new ApiError(res.status, body);
  }

  return body as ImportResult;
}
