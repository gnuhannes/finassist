import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Budgets from "../../src/pages/Budgets";

vi.mock("../../src/hooks/useBudgets", () => ({
  useBudgets: () => ({
    data: [{ id: 1, category_id: 5, category_name: "Groceries", amount: "300.00" }],
    isLoading: false,
    error: null,
  }),
}));

vi.mock("../../src/hooks/useCategories", () => ({
  useCategories: () => ({
    data: [
      { id: 5, name: "Groceries", parent_id: null },
      { id: 6, name: "Transport", parent_id: null },
    ],
    isLoading: false,
    error: null,
  }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Budgets />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Budgets page", () => {
  it("renders the existing budget row", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /budget/i })).toBeInTheDocument();
    expect(screen.getByText("Groceries")).toBeInTheDocument();
    expect(screen.getByText(/300/)).toBeInTheDocument();
  });
});
