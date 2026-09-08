import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Transfers from "../../src/pages/Transfers";

const detect = { mutate: vi.fn(), isPending: false, isSuccess: false, data: [] };

vi.mock("../../src/hooks/useTransferCandidates", () => ({
  useTransferCandidates: (status: string) => ({
    data:
      status === "pending"
        ? [
            {
              id: 1,
              from_leg: {
                transaction_id: 10,
                account_id: 1,
                account_name: "Checking",
                booking_date: "2026-01-01",
                amount: "-100.00",
                payee: "Savings",
              },
              to_leg: {
                transaction_id: 11,
                account_id: 2,
                account_name: "Savings",
                booking_date: "2026-01-01",
                amount: "100.00",
                payee: "Checking",
              },
              confidence: "0.9",
              status: "pending",
            },
          ]
        : [],
    isLoading: false,
    isError: false,
  }),
  useDetectTransfers: () => detect,
  useConfirmTransfer: () => ({ mutate: vi.fn() }),
  useDismissTransfer: () => ({ mutate: vi.fn() }),
}));

describe("Transfers page", () => {
  it("renders the pending candidate and count badge", () => {
    render(
      <MemoryRouter>
        <Transfers />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /transfer/i })).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("triggers detection on button click", () => {
    const { getByRole } = render(
      <MemoryRouter>
        <Transfers />
      </MemoryRouter>,
    );
    getByRole("button", { name: /detect/i }).click();
    expect(detect.mutate).toHaveBeenCalled();
  });
});
