import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type IngestionEntry } from "../../lib/api";
import { IngestionPage } from "./IngestionPage";
import { KnowledgeReviewPage } from "./KnowledgeReviewPage";
import { ReviewKnowledgePage } from "./ReviewKnowledgePage";

afterEach(() => vi.restoreAllMocks());

const entry: IngestionEntry = {
  id: "entry", workspace_id: "workspace", name: "Product context", source_name: "source.txt",
  status: "draft", roles: ["product_knowledge"], created_at: "2026-10-03T12:00:00Z", approved_at: null,
  knowledge_count: 1, artifact_count: 0, skill_count: 0, issue_count: 0,
  preview: {
    source: { name: "source.txt", source_item_count: 1, processed_item_count: 1 },
    application_knowledge: [{ name: "A documented feature", content: "The product supports a documented feature.", evidence_ordinals: [1], grounding_confidence: "high", warnings: [] }],
    artifacts: [], skills: [], extraction_issues: [],
    evidence: [{ ordinal: 1, evidence_type: "text", content_text: "A documented feature.", content_json: null, source_locator: { page_start: 3, page_end: 5 }, extractor_name: "test", extractor_version: "1" }],
  },
};

function renderPage(role = "member", path = "/ingestion", knowledge = entry) {
  vi.spyOn(api, "listIngestion").mockResolvedValue([]);
  vi.spyOn(api, "getIngestion").mockResolvedValue(knowledge);
  vi.spyOn(api, "getKnowledgeSourceAccess").mockResolvedValue({ url: "https://example.com/source" });
  vi.spyOn(api, "listApplications").mockResolvedValue([]);
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route element={<Outlet context={{ user: { id: "user" }, workspace: { id: "workspace", role } }} />}>
          <Route path="/ingestion" element={<IngestionPage />} />
          <Route path="/knowledge/review/:entryId" element={<KnowledgeReviewPage />} />
          <Route path="/knowledge/review" element={<ReviewKnowledgePage />} />
        </Route></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function selectSource() {
  const user = userEvent.setup();
  await user.upload(await screen.findByLabelText("Source file"), new File(["source"], "source.txt", { type: "text/plain" }));
  await user.selectOptions(screen.getByLabelText("Source purpose"), "product_knowledge");
  // jsdom does not validate a FileList populated by userEvent; real clicks are covered by Playwright.
  await act(async () => {
    fireEvent.submit(screen.getByRole("button", { name: "Ingest knowledge" }).closest("form")!);
  });
  return user;
}

describe("workspace ingestion", () => {
  it("uploads a source, navigates to review, and requires review confirmation before approval", async () => {
    const ingest = vi.spyOn(api, "ingestKnowledge").mockResolvedValue(entry);
    const approve = vi.spyOn(api, "approveIngestion").mockResolvedValue({ ...entry, status: "approved" });
    renderPage();
    const user = await selectSource();
    expect(ingest).toHaveBeenCalledWith("workspace", expect.any(File), "source", ["product_knowledge"]);
    expect(await screen.findByText("A documented feature")).toBeInTheDocument();
    expect(screen.getByText("No testable Skills found in this source.")).toBeInTheDocument();
    expect(screen.getByText(/Pages 3–5/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve knowledge" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Approve knowledge" }));
    expect(await screen.findByText("Available for tests")).toBeInTheDocument();
    expect(approve).toHaveBeenCalledWith("workspace", "entry");
  });

  it("keeps the selected file available for retry after upload failure", async () => {
    const ingest = vi.spyOn(api, "ingestKnowledge").mockRejectedValue(new Error("Knowledge processing is unavailable."));
    renderPage();
    const user = await selectSource();
    expect(await screen.findByRole("alert")).toHaveTextContent("Knowledge processing is unavailable.");
    expect(screen.getByRole("button", { name: "Ingest knowledge" })).toBeEnabled();
    await act(async () => {
      fireEvent.submit(screen.getByRole("button", { name: "Ingest knowledge" }).closest("form")!);
    });
    expect(ingest).toHaveBeenCalledTimes(2);
  });

  it("does not offer upload to a read-only workspace member", async () => {
    renderPage("viewer");
    expect(await screen.findByText("Read-only workspace")).toBeInTheDocument();
    expect(screen.queryByLabelText("Source file")).not.toBeInTheDocument();
  });

  it("lets an approved set be deleted after confirmation, with errors remaining retryable", async () => {
    const remove = vi.spyOn(api, "deleteIngestion")
      .mockRejectedValueOnce(new Error("Temporary API failure."))
      .mockResolvedValue(undefined);
    renderPage("member", "/knowledge/review/entry", { ...entry, status: "approved" });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete knowledge: Product context" }));
    expect(screen.getByText(/Existing tests keep their saved knowledge and source history/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(remove).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete knowledge: Product context" }));
    await user.click(screen.getByRole("button", { name: "Delete knowledge" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Temporary API failure.");
    await user.click(screen.getByRole("button", { name: "Delete knowledge" }));
    expect(await screen.findByText("No knowledge to review")).toBeInTheDocument();
    expect(remove).toHaveBeenLastCalledWith("workspace", "entry");
    expect(remove).toHaveBeenCalledTimes(2);
  });

  it("does not offer knowledge deletion to a read-only member", async () => {
    renderPage("viewer", "/knowledge/review/entry", { ...entry, status: "approved" });
    expect(await screen.findByText("Available for tests")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete knowledge/ })).not.toBeInTheDocument();
  });

  it("opens progress immediately and shows the completed result after navigating away and back", async () => {
    const queued: IngestionEntry = { ...entry, processing_status: "queued", knowledge_count: 0 };
    vi.spyOn(api, "ingestKnowledge").mockResolvedValue(queued);
    renderPage();
    vi.mocked(api.listIngestion).mockResolvedValue([queued]);
    vi.mocked(api.getIngestion).mockResolvedValue({ ...queued, processing_status: "processing" });
    const user = await selectSource();
    await waitFor(() => expect(screen.getByRole("progressbar", { name: "Ingestion progress" })).toHaveAttribute("value", "50"));
    expect(screen.getByText(/You can leave this page/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve knowledge" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Back to review knowledge" }));
    expect(await screen.findByRole("link", { name: /Review\s+Product context/ })).toBeInTheDocument();
    vi.mocked(api.getIngestion).mockResolvedValue({ ...entry, processing_status: "ready" });
    await user.click(screen.getByRole("link", { name: /Review\s+Product context/ }));
    expect(await screen.findByText("A documented feature")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve knowledge" })).toBeDisabled();
  });

  it("renames a saved set and attaches approved knowledge to an application", async () => {
    const approved = { ...entry, status: "approved" as const, application_ids: [] };
    const rename = vi.spyOn(api, "renameIngestion").mockResolvedValue({ ...approved, name: "Shared product rules" });
    const attach = vi.spyOn(api, "attachIngestion").mockResolvedValue({ ...approved, name: "Shared product rules", application_ids: ["app"] });
    renderPage("member", "/knowledge/review/entry", approved);
    vi.mocked(api.listApplications).mockResolvedValue([{ id: "app", workspace_id: "workspace", created_by_user_id: "user", name: "Demo application", description: null, status: "active" }]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Rename" }));
    await user.clear(screen.getByLabelText("Knowledge set name"));
    await user.type(screen.getByLabelText("Knowledge set name"), "Shared product rules");
    await user.click(screen.getByRole("button", { name: "Save name" }));
    expect(await screen.findByRole("heading", { name: "Shared product rules" })).toBeInTheDocument();
    expect(rename).toHaveBeenCalledWith("workspace", "entry", "Shared product rules");
    await user.click(await screen.findByRole("checkbox", { name: "Demo application" }));
    expect(screen.queryByRole("link", { name: /Create test/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save applications" }));
    expect(attach).toHaveBeenCalledWith("workspace", "entry", ["app"]);
    expect(await screen.findByRole("link", { name: /Create test/ })).toHaveAttribute("href", "/applications/app/runs/new");
  });
});
