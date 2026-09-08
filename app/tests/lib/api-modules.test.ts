import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getAccounts, createAccount, updateAccount } from "../../src/lib/api/accounts";
import { getAnnualReport } from "../../src/lib/api/annual";
import { getBudgets, createBudget, updateBudget, deleteBudget } from "../../src/lib/api/budgets";
import { getCategories, deleteCategory } from "../../src/lib/api/categories";
import { importCsv } from "../../src/lib/api/imports";
import { getNetWorth } from "../../src/lib/api/netWorth";
import { getRecurringPatterns, getRecurringSummary } from "../../src/lib/api/recurringPatterns";
import { getMonthlyReport, getBudgetVsActual, getFixedVsVariable } from "../../src/lib/api/reports";
import { deleteTransactions, wipeAllData } from "../../src/lib/api/settings";
import { getSpendingTrend } from "../../src/lib/api/trends";
import { getTransactions, updateTransactionCategory } from "../../src/lib/api/transactions";
import { getTransferCandidates, confirmTransfer } from "../../src/lib/api/transfers";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status });
}

function lastCall(): [string, RequestInit] {
  const calls = vi.mocked(fetch).mock.calls;
  return calls[calls.length - 1] as [string, RequestInit];
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(jsonResponse({}))),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("query-string builders", () => {
  it("getMonthlyReport omits account_id for 'all'", async () => {
    await getMonthlyReport({ accountId: "all", month: "2026-02" });
    expect(lastCall()[0]).toBe("/api/reports/monthly?month=2026-02");

    await getMonthlyReport({ accountId: 3, month: "2026-02" });
    expect(lastCall()[0]).toBe("/api/reports/monthly?month=2026-02&account_id=3");
  });

  it("getBudgetVsActual / getFixedVsVariable build the right path", async () => {
    await getBudgetVsActual({ accountId: 1, month: "2026-03" });
    expect(lastCall()[0]).toContain("/api/reports/budget-vs-actual?month=2026-03");
    await getFixedVsVariable({ accountId: "all", month: "2026-03" });
    expect(lastCall()[0]).toBe("/api/reports/fixed-vs-variable?month=2026-03");
  });

  it("getTransactions only includes set params", async () => {
    await getTransactions({ accountId: "all", limit: 25, q: "rewe" });
    const url = lastCall()[0];
    expect(url).toContain("limit=25");
    expect(url).toContain("q=rewe");
    expect(url).not.toContain("account_id");
    expect(url).not.toContain("offset");
  });

  it("getSpendingTrend / getAnnualReport / getNetWorth", async () => {
    await getSpendingTrend(6, 1, "2026-02");
    expect(lastCall()[0]).toContain("/api/reports/spending-trend?");
    expect(lastCall()[0]).toContain("lookback_months=6");
    await getAnnualReport(2025, "all");
    expect(lastCall()[0]).toBe("/api/reports/annual?year=2025");
    await getNetWorth(24);
    expect(lastCall()[0]).toBe("/api/reports/net-worth?months=24");
  });

  it("getRecurringPatterns / summary", async () => {
    await getRecurringPatterns(2, true);
    expect(lastCall()[0]).toContain("account_id=2");
    expect(lastCall()[0]).toContain("include_inactive=true");
    await getRecurringSummary(2);
    expect(lastCall()[0]).toContain("/api/recurring-patterns/summary?");
  });
});

describe("method + body", () => {
  it("createAccount POSTs JSON", async () => {
    await createAccount({ name: "Main", currency: "EUR" });
    const [url, init] = lastCall();
    expect(url).toBe("/api/accounts");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ name: "Main", currency: "EUR" }));
  });

  it("updateAccount PATCHes", async () => {
    await updateAccount(5, { opening_balance: "100.00" });
    expect(lastCall()[1].method).toBe("PATCH");
    expect(lastCall()[0]).toBe("/api/accounts/5");
  });

  it("GET helpers", async () => {
    await getAccounts();
    expect(lastCall()[0]).toBe("/api/accounts");
    await getCategories();
    expect(lastCall()[0]).toBe("/api/categories");
    await getBudgets();
    expect(lastCall()[0]).toBe("/api/budgets");
  });

  it("budget mutations", async () => {
    await createBudget({ category_id: 1, amount: "50" });
    expect(lastCall()[1].method).toBe("POST");
    await updateBudget(1, { amount: "60" });
    expect(lastCall()[1].method).toBe("PATCH");
    await deleteBudget(1);
    expect(lastCall()[1].method).toBe("DELETE");
    expect(lastCall()[0]).toBe("/api/budgets/1");
  });

  it("deleteCategory / updateTransactionCategory / transfers", async () => {
    await deleteCategory(9);
    expect(lastCall()[0]).toBe("/api/categories/9");
    expect(lastCall()[1].method).toBe("DELETE");
    await updateTransactionCategory(3, 7);
    expect(lastCall()[1].body).toBe(JSON.stringify({ category_id: 7 }));
    await getTransferCandidates("pending");
    expect(lastCall()[0]).toContain("status=pending");
    await confirmTransfer(4);
    expect(lastCall()[0]).toBe("/api/transfers/candidates/4/confirm");
  });

  it("settings deletes hit the guarded endpoints", async () => {
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse({ deleted: 2 })));
    await deleteTransactions();
    expect(lastCall()[0]).toBe("/api/data/transactions");
    expect((lastCall()[1].headers as Headers).get("X-Requested-With")).toBe("XMLHttpRequest");
    await wipeAllData();
    expect(lastCall()[0]).toBe("/api/data");
  });

  it("importCsv sends FormData without a JSON Content-Type", async () => {
    vi.mocked(fetch).mockImplementation(() =>
      Promise.resolve(jsonResponse({ total_rows: 0, created: 0 })),
    );
    const file = new File(["a,b\n1,2\n"], "x.csv", { type: "text/csv" });
    await importCsv({ file, accountId: 1, delimiter: ";" });
    const [url, init] = lastCall();
    expect(url).toContain("/api/imports/csv?account_id=1");
    expect(url).toContain("delimiter=%3B");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Headers).has("Content-Type")).toBe(false);
  });
});
