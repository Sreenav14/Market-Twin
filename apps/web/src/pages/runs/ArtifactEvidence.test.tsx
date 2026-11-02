import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { api, type ArtifactAccess } from "../../lib/api";
import { ArtifactEvidence } from "./FindingDetailPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("never displays the previous test's artifact grant when the evidence context changes", async () => {
  let complete!: (grant: ArtifactAccess) => void;
  vi.spyOn(api, "getArtifactAccess").mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
  const { rerender } = render(<ArtifactEvidence runId="first" artifactId="artifact" />);
  await userEvent.click(screen.getByRole("button", { name: "View evidence" }));
  rerender(<ArtifactEvidence runId="second" artifactId="artifact" />);
  expect(screen.getByRole("button", { name: "View evidence" })).toBeEnabled();
  await act(async () => complete({ artifact_id: "artifact", artifact_type: "screenshot", content_type: "image/png",
    url: "https://fixture.invalid/old-test.png", expires_in_seconds: 60 }));
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
