import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderApp } from "../render";

vi.mock("../../src/hooks/useAccounts", () => ({
  useAccounts: () => ({
    data: [{ id: 1, name: "Main", currency: "EUR" }],
    isLoading: false,
    error: null,
  }),
}));

vi.mock("../../src/hooks/useRecurringPatterns", () => ({
  useRecurringPatterns: () => ({ data: [], isLoading: false, isError: false }),
  useRecurringSummary: () => ({ data: null, isLoading: false }),
}));

vi.mock("../../src/hooks/useTrends", () => ({
  useSpendingTrend: () => ({ data: undefined, isLoading: false, isError: false }),
}));

vi.mock("../../src/hooks/useAnnual", () => ({
  useAnnualReport: () => ({ data: undefined, isLoading: false, isError: false }),
}));

vi.mock("../../src/hooks/useCategories", () => ({
  useCategories: () => ({
    data: [
      { id: 1, name: "Groceries", parent_id: null, cost_type: "variable" },
      { id: 2, name: "Rent", parent_id: null, cost_type: "fixed" },
    ],
    isLoading: false,
    error: null,
  }),
}));

import AnnualOverview from "../../src/pages/AnnualOverview";
import Categories from "../../src/pages/Categories";
import Recurring from "../../src/pages/Recurring";
import SpendingTrends from "../../src/pages/SpendingTrends";

describe("page smoke tests", () => {
  it("Recurring renders its title", () => {
    renderApp(<Recurring />);
    expect(screen.getByRole("heading", { name: /recurring/i })).toBeInTheDocument();
  });

  it("SpendingTrends renders its title", () => {
    renderApp(<SpendingTrends />);
    expect(screen.getByRole("heading", { name: /spending trend/i })).toBeInTheDocument();
  });

  it("AnnualOverview renders its title", () => {
    renderApp(<AnnualOverview />);
    expect(screen.getByRole("heading", { name: /annual/i })).toBeInTheDocument();
  });

  it("Categories renders its categories", () => {
    renderApp(<Categories />);
    expect(screen.getByRole("heading", { name: /categories/i })).toBeInTheDocument();
    expect(screen.getByText("Groceries")).toBeInTheDocument();
    expect(screen.getByText("Rent")).toBeInTheDocument();
  });
});
