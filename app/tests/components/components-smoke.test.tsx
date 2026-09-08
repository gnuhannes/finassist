import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { renderApp } from "../render";

// jsdom doesn't implement <dialog>.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close ??= function () {
    this.open = false;
  };
});

vi.mock("../../src/hooks/useAccounts", () => ({
  useAccounts: () => ({
    data: [{ id: 1, name: "Main", currency: "EUR" }],
    isLoading: false,
    error: null,
  }),
}));

vi.mock("../../src/hooks/useCsvProfiles", () => ({
  useCsvProfiles: () => ({
    profiles: {
      data: [
        {
          id: 1,
          name: "DKB Giro",
          delimiter: ";",
          date_format: "dmy",
          decimal_comma: true,
          column_map: {},
        },
      ],
    },
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn() },
  }),
}));

vi.mock("../../src/hooks/useImportCsv", () => ({
  useImportCsv: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
}));

const emptyQuery = { data: [], isLoading: false, isError: false };
vi.mock("../../src/hooks/useWatchFolder", () => ({
  useWatchSettings: () => ({ data: { root_path: "data/watch" } }),
  useUpdateWatchSettings: () => ({ mutate: vi.fn(), isPending: false }),
  useWatchConfigs: () => emptyQuery,
  useCreateWatchConfig: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateWatchConfig: () => ({ mutate: vi.fn() }),
  useDeleteWatchConfig: () => ({ mutate: vi.fn() }),
}));

import { CategorySelect } from "../../src/components/CategorySelect";
import { CsvProfileManager } from "../../src/components/CsvProfileManager";
import { ImportDialog } from "../../src/components/ImportDialog";
import { WatchFolderPanel } from "../../src/components/WatchFolderPanel";

const CATS = [
  { id: 1, name: "Groceries", parent_id: null, cost_type: null },
  { id: 2, name: "Rent", parent_id: null, cost_type: null },
];

describe("component smoke tests", () => {
  it("CategorySelect opens its list on click", () => {
    renderApp(<CategorySelect categories={CATS} value={null} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Groceries")).toBeInTheDocument();
    expect(screen.getByText("Rent")).toBeInTheDocument();
  });

  it("CsvProfileManager lists existing profiles", () => {
    renderApp(<CsvProfileManager onClose={vi.fn()} />);
    expect(screen.getByText("DKB Giro")).toBeInTheDocument();
  });

  it("ImportDialog renders when open", () => {
    renderApp(<ImportDialog open onClose={vi.fn()} />);
    expect(screen.getByRole("heading", { name: /import/i })).toBeInTheDocument();
  });

  it("WatchFolderPanel renders its subfolder section", () => {
    renderApp(<WatchFolderPanel />);
    expect(screen.getByText("Subfolder mappings")).toBeInTheDocument();
  });
});
