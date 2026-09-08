import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Suggestions from "../../src/pages/Suggestions";

const train = { mutate: vi.fn(), isPending: false };

vi.mock("../../src/hooks/useMl", () => ({
  useSuggestions: () => ({
    data: [
      {
        transaction_id: 1,
        category_id: 3,
        category_name: "Groceries",
        confidence: 0.95,
        payee: "REWE",
        purpose: "Food",
        amount: "-12.34",
        booking_date: "2026-01-01",
      },
    ],
    isLoading: false,
    isError: false,
  }),
  useTrainModel: () => train,
  useAcceptSuggestion: () => ({ mutate: vi.fn() }),
}));

describe("Suggestions page", () => {
  it("renders a high-confidence suggestion", () => {
    render(
      <MemoryRouter>
        <Suggestions />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /suggestion/i })).toBeInTheDocument();
    expect(screen.getByText("REWE")).toBeInTheDocument();
  });

  it("retrains on button click", () => {
    render(
      <MemoryRouter>
        <Suggestions />
      </MemoryRouter>,
    );
    const btn = screen
      .getAllByRole("button")
      .find((b) => /train|retrain/i.test(b.textContent ?? ""));
    btn?.click();
    expect(train.mutate).toHaveBeenCalled();
  });
});
