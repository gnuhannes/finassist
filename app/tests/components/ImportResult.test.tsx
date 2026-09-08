import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ImportResult } from "../../src/components/ImportResult";
import type { ImportResult as ImportResultType } from "../../src/lib/api";

const successResult: ImportResultType = {
  total_rows: 10,
  created: 8,
  skipped: 0,
  duplicates: 2,
  failed: 0,
  errors: [],
  errors_truncated: false,
};

const resultWithErrors: ImportResultType = {
  total_rows: 5,
  created: 2,
  skipped: 0,
  duplicates: 1,
  failed: 2,
  errors: [
    {
      row: 3,
      field: "booking_date",
      raw_value: "not-a-date",
      message: "Invalid ISO date: 'not-a-date'",
      hint: "Try switching the date format to DMY (dd.mm.yyyy).",
      unexpected: false,
    },
    {
      row: 5,
      field: "amount",
      raw_value: null,
      message: "Missing column 'amount/Betrag'",
      hint: "Add one of these header names to the CSV.",
      unexpected: false,
    },
  ],
  errors_truncated: false,
};

describe("ImportResult", () => {
  it("renders all KPI values", () => {
    render(<ImportResult result={successResult} />);

    expect(screen.getByText("Total rows")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("Duplicates")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("does not render error list when there are no errors", () => {
    render(<ImportResult result={successResult} />);

    expect(screen.queryByText("Row errors:")).not.toBeInTheDocument();
  });

  it("renders error list when there are errors", () => {
    render(<ImportResult result={resultWithErrors} />);

    expect(screen.getByText("Row errors:")).toBeInTheDocument();
    expect(screen.getByText("Invalid ISO date: 'not-a-date'")).toBeInTheDocument();
    expect(screen.getByText("Missing column 'amount/Betrag'")).toBeInTheDocument();
  });

  it("renders field and hint details", () => {
    render(<ImportResult result={resultWithErrors} />);

    expect(screen.getByText("booking_date")).toBeInTheDocument();
    expect(
      screen.getByText("Try switching the date format to DMY (dd.mm.yyyy)."),
    ).toBeInTheDocument();
  });

  it("renders raw value when present", () => {
    render(<ImportResult result={resultWithErrors} />);

    expect(screen.getByText('"not-a-date"')).toBeInTheDocument();
  });
});
