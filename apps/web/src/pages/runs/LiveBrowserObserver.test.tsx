import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, type LiveBrowser } from "../../lib/api";
import { LiveBrowserObserver } from "./LiveBrowserObserver";

const browser: LiveBrowser = { browser_session_id: "browser-1", execution_id: "execution-1", journey_id: "journey-1", generation: 1, control_state: "agent", viewer_state: "available", journey_title: "Check registration", requesting_agent: "Persona" };
const stream = { url: "ws://localhost/api/v1/hitl-viewer", ticket: "observer-ticket" };

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  binaryType: BinaryType = "blob";
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  readonly sent: string[] = [];

  constructor(readonly url: string) {
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  async frame() {
    await act(async () => this.onmessage?.({ data: new Blob(["frame"], { type: "image/jpeg" }) } as MessageEvent<Blob>));
  }
}

const create = vi.fn();
const revoke = vi.fn();
const decode = vi.fn();
beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
  create.mockReset().mockImplementation(() => `blob:volatile-${create.mock.calls.length}`);
  revoke.mockReset();
  decode.mockReset().mockResolvedValue(undefined);
  vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: revoke });
  vi.stubGlobal("Image", class { src = ""; decode = decode; });
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("renders socket frames in watch mode without polling or sending input", async () => {
  const frames = vi.spyOn(api, "getLiveBrowserFrame");
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  expect(socket.url).toBe(stream.url);
  socket.open();
  expect(socket.sent).toEqual([JSON.stringify({ ticket: "observer-ticket" })]);
  await socket.frame();
  expect(screen.getByRole("img")).toHaveAttribute("src", "blob:volatile-1");
  expect(screen.getByRole("status")).toHaveTextContent("Read-only live view. Browser input is disabled.");
  expect(screen.getByText(/Frame delivered/)).toBeInTheDocument();
  expect(screen.queryByText(/fps/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(frames).not.toHaveBeenCalled();
});

it("switches to control chrome without restarting the stream", async () => {
  const onReturnControl = vi.fn();
  const { rerender } = render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} onReturnControl={onReturnControl} />);
  const socket = MockWebSocket.instances[0];
  socket.open();
  await socket.frame();
  rerender(<LiveBrowserObserver runId="run-1" browser={{ ...browser, control_state: "human" }} identity="owner" permitted stream={stream} onReturnControl={onReturnControl} />);
  expect(MockWebSocket.instances).toHaveLength(1);
  expect(screen.getByRole("status")).toHaveTextContent("You are controlling this browser — the test is paused");
  fireEvent.click(screen.getByRole("button", { name: "Return control" }));
  expect(onReturnControl).toHaveBeenCalledOnce();
});

it("shows the parked-for-login panel over the dimmed last frame", async () => {
  const onTakeControl = vi.fn();
  render(<LiveBrowserObserver runId="run-1" browser={{ ...browser, control_state: "human_pending" }} identity="owner" permitted stream={stream} onTakeControl={onTakeControl} />);
  const socket = MockWebSocket.instances[0];
  socket.open();
  await socket.frame();
  expect(screen.getByRole("img")).toHaveStyle({ opacity: "0.45" });
  expect(screen.getByText("The tester needs you to log in")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Take control and log in" }));
  expect(onTakeControl).toHaveBeenCalledOnce();
});

it("shows the waiting, error and protected states with the exact copy", async () => {
  const { rerender } = render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  expect(screen.getByRole("status")).toHaveTextContent("Waiting for the first live frame.");
  const socket = MockWebSocket.instances[0];
  act(() => socket.onerror?.(new Event("error")));
  expect(screen.getByRole("status")).toHaveTextContent("Browser frame temporarily unavailable; the test can continue.");
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  rerender(<LiveBrowserObserver runId="run-1" browser={{ ...browser, control_state: "human", viewer_state: "suppressed" }} identity="owner" permitted stream={stream} />);
  expect(screen.getByText("Read-only observation is hidden during protected human interaction.")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("pauses the live view while the tab is hidden", async () => {
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  socket.open();
  await socket.frame();
  expect(screen.getByRole("img")).toBeInTheDocument();
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Live view paused while this tab is hidden.");
});
