import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, api, type LiveBrowser } from "../../lib/api";
import { LiveBrowserObserver } from "./LiveBrowserObserver";

const browser: LiveBrowser = { browser_session_id: "browser-1", execution_id: "execution-1", journey_id: "journey-1", generation: 1, control_state: "agent", viewer_state: "available", journey_title: "Check registration", requesting_agent: "Persona" };
const decode = vi.fn();
const create = vi.fn();
const revoke = vi.fn();
beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  create.mockReset().mockImplementation(() => `blob:volatile-${create.mock.calls.length}`);
  revoke.mockReset(); decode.mockReset().mockResolvedValue(undefined);
  vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: revoke });
  vi.stubGlobal("Image", class { src = ""; decode = decode; });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
async function flush() { await act(async () => { await Promise.resolve(); }); }

it.each(["agent", "human_pending"])("shows volatile passive frames during %s without acquiring control or exposing input", async (control_state) => {
  const frames = vi.spyOn(api, "getLiveBrowserFrame").mockResolvedValue(new Blob(["frame"], { type: "image/jpeg" }));
  const claim = vi.spyOn(api, "claimHumanAction");
  const { unmount } = render(<LiveBrowserObserver runId="run-1" browser={{ ...browser, control_state }} identity="owner-workspace" permitted />);
  await flush();
  expect(screen.getByRole("img")).toHaveAttribute("src", "blob:volatile-1");
  expect(screen.getByRole("status")).toHaveTextContent("Browser input is disabled");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /control|approve/i })).not.toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole("img"), { key: "a" });
  fireEvent.pointerDown(screen.getByRole("img"));
  expect(claim).not.toHaveBeenCalled();
  expect(frames).toHaveBeenCalledOnce();
  unmount();
  expect(revoke).toHaveBeenCalledWith("blob:volatile-1");
});

it("aborts and clears on generation change, rejects a late response, and clears on human claim", async () => {
  let finishOld: ((blob: Blob) => void) | undefined;
  const frames = vi.spyOn(api, "getLiveBrowserFrame")
    .mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }))
    .mockResolvedValue(new Blob(["new frame"]));
  const { rerender } = render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted />);
  const oldSignal = frames.mock.calls[0][2];
  rerender(<LiveBrowserObserver runId="run-1" browser={{ ...browser, generation: 2 }} identity="owner" permitted />);
  await flush();
  expect(oldSignal.aborted).toBe(true);
  expect(screen.getByRole("img")).toHaveAttribute("src", "blob:volatile-1");
  await act(async () => finishOld?.(new Blob(["old frame"])));
  expect(create).toHaveBeenCalledOnce();
  rerender(<LiveBrowserObserver runId="run-1" browser={{ ...browser, generation: 3, control_state: "human", viewer_state: "suppressed" }} identity="owner" permitted />);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(revoke).toHaveBeenCalledWith("blob:volatile-1");
  expect(frames).toHaveBeenCalledTimes(2);
});

it("clears pixels and stops polling after permission denial", async () => {
  const frames = vi.spyOn(api, "getLiveBrowserFrame").mockResolvedValueOnce(new Blob(["frame"]))
    .mockRejectedValue(new ApiError("Denied", 403));
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted />);
  await flush();
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Check your workspace permissions");
  await act(async () => vi.advanceTimersByTimeAsync(10000));
  expect(frames).toHaveBeenCalledTimes(2);
});

it("stops fetching and clears frames while hidden, then resumes once visible", async () => {
  const frames = vi.spyOn(api, "getLiveBrowserFrame").mockResolvedValue(new Blob(["frame"]));
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted />);
  await flush();
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  await act(async () => vi.advanceTimersByTimeAsync(10000));
  expect(frames).toHaveBeenCalledOnce();
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  await flush();
  expect(frames).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("img")).toBeInTheDocument();
});

it("never displays a malformed image or a frame after role loss", async () => {
  vi.spyOn(api, "getLiveBrowserFrame").mockResolvedValue(new Blob(["not an image"]));
  decode.mockRejectedValue(new Error("Invalid image"));
  const { rerender } = render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted />);
  await flush();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(revoke).toHaveBeenCalledWith("blob:volatile-1");
  rerender(<LiveBrowserObserver runId="run-1" browser={browser} identity="viewer" permitted={false} />);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByText(/requires an owner or administrator role/)).toBeInTheDocument();
});
