import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type IngestionEntry, type KnowledgeFileContent } from "../../lib/api";
import { KnowledgeEntryPage } from "./KnowledgeEntryPage";

afterEach(() => vi.restoreAllMocks());

const emptyPreview = {
  source: { name: "pricing-guide.pdf", source_item_count: 5, processed_item_count: 5 },
  application_knowledge: [],
  artifacts: [],
  skills: [],
  extraction_issues: [],
  evidence: [],
};

const fileEntry: IngestionEntry = {
  id: "entry",
  workspace_id: "workspace",
  name: "Pricing guide",
  source_name: "pricing-guide.pdf",
  status: "draft",
  roles: ["product_knowledge"],
  created_at: "2026-10-03T12:00:00Z",
  approved_at: null,
  knowledge_count: 0,
  artifact_count: 0,
  skill_count: 0,
  issue_count: 0,
  file_count: 2,
  preview: emptyPreview,
  files: [
    {
      id: "file-1",
      slug: "pricing",
      title: "Pricing",
      description: "Plan prices and the annual-discount exception.",
      token_count: 420,
      sha256: "aaa",
      version: 1,
      status: "generated",
    },
    {
      id: "file-2",
      slug: "refunds",
      title: "Refunds",
      description: "Refund windows and exceptions.",
      token_count: 180,
      sha256: "bbb",
      version: 1,
      status: "generated",
    },
  ],
};

const pricingMarkdown = `---
title: Pricing
description: Plan prices and the annual-discount exception.
source_entry: entry
source_name: pricing-guide.pdf
file_version: 1
---

# Pricing

## Plans
The Basic plan costs **$10 per month**. The Team plan costs **$25 per month**.

> **Exception:** the annual discount does not apply to the Team plan.

## Uncertainties
- The guide does not say whether prices include tax. (Evidence 5)

## Source references
- Evidence 3 — pricing-guide.pdf, page 2
- Evidence 5 — pricing-guide.pdf, page 4
`;

const refundsMarkdown = `# Refunds

## Windows
Refunds are available within **30 days** of purchase.

## Uncertainties
- None recorded.

## Source references
- Evidence 3 — pricing-guide.pdf, page 2
`;

const fileContents: Record<string, KnowledgeFileContent> = {
  pricing: {
    slug: "pricing",
    title: "Pricing",
    description: "Plan prices and the annual-discount exception.",
    markdown: pricingMarkdown,
    evidence: [
      {
        ordinal: 3,
        evidence_type: "text",
        content_text: "Basic plan: $10 per month. Team plan: $25 per month.",
        content_json: null,
        source_locator: { page_start: 2, page_end: 2 },
        extractor_name: "pypdf",
        extractor_version: "6",
      },
      {
        ordinal: 5,
        evidence_type: "text",
        content_text: "Annual billing carries a 20% discount on the Basic plan.",
        content_json: null,
        source_locator: { page_start: 4, page_end: 4 },
        extractor_name: "pypdf",
        extractor_version: "6",
      },
    ],
  },
  refunds: {
    slug: "refunds",
    title: "Refunds",
    description: "Refund windows and exceptions.",
    markdown: refundsMarkdown,
    evidence: [],
  },
};

function renderReview(knowledge: IngestionEntry, role = "member") {
  vi.spyOn(api, "getIngestion").mockResolvedValue(knowledge);
  vi.spyOn(api, "getKnowledgeSourceAccess").mockResolvedValue({ url: "https://example.com/source" });
  vi.spyOn(api, "listApplications").mockResolvedValue([]);
  vi.spyOn(api, "getKnowledgeFile").mockImplementation(
    async (_workspaceId: string, _entryId: string, slug: string) => fileContents[slug],
  );
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/knowledge/review/entry"]}>
        <Routes>
          <Route element={<Outlet context={{ user: { id: "user" }, workspace: { id: "workspace", role } }} />}>
            <Route path="/knowledge/review/:entryId" element={<KnowledgeEntryPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("knowledge file review", () => {
  it("lists the entry's files with title, description and token count", async () => {
    renderReview(fileEntry);
    expect(await screen.findByRole("button", { name: /^Pricing/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Refunds/ })).toBeInTheDocument();
    expect(screen.getByText("Plan prices and the annual-discount exception.")).toBeInTheDocument();
    expect(screen.getByText("Refund windows and exceptions.")).toBeInTheDocument();
    expect(screen.getByText(/420 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/180 tokens/)).toBeInTheDocument();
    expect(screen.queryByText("Generated summary")).not.toBeInTheDocument();
  });

  it("renders the selected file's markdown, uncertainties and source-reference evidence", async () => {
    renderReview(fileEntry);
    expect(await screen.findByRole("heading", { name: "Plans" })).toBeInTheDocument();
    expect(screen.getByText("$10 per month")).toBeInTheDocument();
    expect(screen.getByText(/annual discount does not apply to the Team plan/)).toBeInTheDocument();
    expect(screen.getByText(/does not say whether prices include tax/)).toBeInTheDocument();
    const chip = screen.getAllByRole("link", { name: "Evidence 3" })[0];
    expect(chip).toHaveAttribute("href", "#evidence-3");
    expect((await screen.findAllByText(/Pages 2/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/Basic plan: \$10 per month/)).toBeInTheDocument();
  });

  it("loads another file when it is selected in the list", async () => {
    renderReview(fileEntry);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /^Refunds/ }));
    expect(await screen.findByRole("heading", { name: "Windows" })).toBeInTheDocument();
    expect(screen.getByText("30 days")).toBeInTheDocument();
    expect(api.getKnowledgeFile).toHaveBeenCalledWith("workspace", "entry", "refunds");
  });

  it("approves the file set through the unchanged approval flow", async () => {
    const approve = vi
      .spyOn(api, "approveIngestion")
      .mockResolvedValue({ ...fileEntry, status: "approved" });
    renderReview(fileEntry);
    const user = userEvent.setup();
    expect(await screen.findByText("Files: 2 ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve knowledge" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Approve knowledge" }));
    expect(await screen.findByText("Available for tests")).toBeInTheDocument();
    expect(approve).toHaveBeenCalledWith("workspace", "entry");
  });

  it("shows an honest empty state when a finished entry has no files", async () => {
    renderReview({ ...fileEntry, files: [], file_count: 0 });
    expect(await screen.findByText("No knowledge files yet")).toBeInTheDocument();
    expect(screen.getByText("This source produced no knowledge to approve.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve knowledge" })).toBeDisabled();
    expect(api.getKnowledgeFile).not.toHaveBeenCalled();
  });
});
