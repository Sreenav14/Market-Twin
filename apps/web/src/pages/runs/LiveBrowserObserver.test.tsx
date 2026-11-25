import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { type LiveBrowser } from "../../lib/api";
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
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL = create;
    static revokeObjectURL = revoke;
  });
  vi.stubGlobal("Image", class { src = ""; decode = decode; });
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("renders socket frames in watch mode without polling or sending input", async () => {
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  expect(socket.url).toBe(`ws://${window.location.host}/api/v1/hitl-viewer`);
  socket.open();
  expect(socket.sent).toEqual([JSON.stringify({ ticket: "observer-ticket" })]);
  await socket.frame();
  expect(screen.getByRole("img")).toHaveAttribute("src", "blob:volatile-1");
  expect(screen.getByRole("status")).toHaveTextContent("Read-only live view. Browser input is disabled.");
  expect(screen.getByText(/Frame delivered/)).toBeInTheDocument();
  expect(screen.queryByText(/fps/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});

it("shows completed frames during a burst and decodes only the newest queued frame", async () => {
  let finishFirst!: () => void;
  let finishNext!: () => void;
  decode.mockReset()
    .mockImplementationOnce(() => new Promise<void>((resolve) => { finishFirst = resolve; }))
    .mockImplementationOnce(() => new Promise<void>((resolve) => { finishNext = resolve; }));
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  await socket.frame();
  await socket.frame();
  await socket.frame();
  expect(decode).toHaveBeenCalledTimes(1);
  await act(async () => { finishFirst(); });
  expect(screen.getByRole("img")).toHaveAttribute("src", "blob:volatile-1");
  expect(decode).toHaveBeenCalledTimes(2);
  await act(async () => { finishNext(); });
  expect(screen.getByRole("img")).toHaveAttribute("src", "blob:volatile-2");
  expect(create).toHaveBeenCalledTimes(2);
  expect(revoke).toHaveBeenCalledWith("blob:volatile-1");
});

it("fits mobile and desktop frames without enlarging narrow viewports", async () => {
  let width = 320;
  vi.stubGlobal("Image", class {
    src = "";
    naturalWidth = width;
    naturalHeight = 900;
    decode = decode;
  });
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  await socket.frame();
  expect(screen.getByRole("img").parentElement?.style.maxWidth).toContain("320px");
  expect(screen.getByText("320 × 900 browser view")).toBeInTheDocument();
  width = 1280;
  await socket.frame();
  expect(screen.getByRole("img").parentElement?.style.maxWidth).toContain("1280px");
  expect(screen.getByText("1280 × 900 browser view")).toBeInTheDocument();
});

it("moves the agent overlay without decoding another JPEG and clears it on protected control", async () => {
  const { rerender } = render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  await socket.frame();
  const point = async (pointer: unknown) => act(async () => {
    socket.onmessage?.({ data: JSON.stringify({ type: "agent_pointer", pointer }) } as MessageEvent);
  });
  await point({ x: 0.25, y: 0.5 });
  expect(screen.getByLabelText("Agent action target")).toHaveStyle({ left: "25%", top: "50%" });
  await point({ x: 0.75, y: 0.1 });
  expect(screen.getByLabelText("Agent action target")).toHaveStyle({ left: "75%", top: "10%" });
  expect(decode).toHaveBeenCalledTimes(1);
  await point({ x: 2, y: 0 });
  expect(screen.queryByLabelText("Agent action target")).not.toBeInTheDocument();
  await point({ x: 0.25, y: 0.5 });
  rerender(<LiveBrowserObserver runId="run-1" browser={{ ...browser, control_state: "human" }} identity="owner" permitted stream={stream} />);
  expect(screen.queryByLabelText("Agent action target")).not.toBeInTheDocument();
});

it("attaches the viewer socket to the page host so the session cookie is sent", async () => {
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={{
    url: "ws://localhost:5173/api/v1/hitl-viewer", ticket: "observer-ticket",
  }} />);
  expect(MockWebSocket.instances[0].url).toBe(`ws://${window.location.host}/api/v1/hitl-viewer`);
});

it("refreshes a single-use ticket before each attach", async () => {
  const onReconnect = vi.fn().mockResolvedValue({ url: stream.url, ticket: "fresh-ticket" });
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} onReconnect={onReconnect} />);
  await act(async () => { await Promise.resolve(); });
  expect(onReconnect).toHaveBeenCalledOnce();
  const socket = MockWebSocket.instances[0];
  socket.open();
  expect(socket.sent).toEqual([JSON.stringify({ ticket: "fresh-ticket" })]);
});

it("does not restart a fresh stream when the grant query finishes updating props", async () => {
  const onReconnect = vi.fn().mockResolvedValue({ ...stream, ticket: "fresh-ticket" });
  const { rerender } = render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted onReconnect={onReconnect} />);
  await act(async () => { await Promise.resolve(); });
  await MockWebSocket.instances[0].frame();
  rerender(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={{ ...stream, ticket: "fresh-ticket" }} onReconnect={onReconnect} />);
  expect(onReconnect).toHaveBeenCalledOnce();
  expect(MockWebSocket.instances).toHaveLength(1);
  expect(screen.getByRole("img")).toBeInTheDocument();
});

it("keeps the last frame and reattaches after a stream closes", async () => {
  vi.useFakeTimers();
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  socket.open();
  await socket.frame();
  act(() => socket.onclose?.(new CloseEvent("close")));
  expect(screen.getByRole("img")).toBeInTheDocument();
  await act(async () => { vi.advanceTimersByTime(1000); });
  expect(MockWebSocket.instances).toHaveLength(2);
  vi.useRealTimers();
});

it("surfaces a closed socket that never delivered a frame", async () => {
  vi.useFakeTimers();
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  act(() => socket.onclose?.(new CloseEvent("close")));
  expect(screen.getByRole("status")).toHaveTextContent("The viewer could not connect.");
  await act(async () => { vi.advanceTimersByTime(1000); });
  expect(MockWebSocket.instances).toHaveLength(2);
});

it("retries an initial grant failure instead of waiting forever", async () => {
  vi.useFakeTimers();
  const onReconnect = vi.fn().mockRejectedValueOnce(new Error("Not ready"))
    .mockResolvedValue({ ...stream, ticket: "recovered" });
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted onReconnect={onReconnect} />);
  await act(async () => { await Promise.resolve(); });
  expect(MockWebSocket.instances).toHaveLength(0);
  await act(async () => { vi.advanceTimersByTime(1000); });
  expect(MockWebSocket.instances).toHaveLength(1);
  MockWebSocket.instances[0].open();
  expect(MockWebSocket.instances[0].sent).toEqual([JSON.stringify({ ticket: "recovered" })]);
});

it("reconnects when a socket opens but never supplies the first frame", async () => {
  vi.useFakeTimers();
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  MockWebSocket.instances[0].open();
  await act(async () => { vi.advanceTimersByTime(10000); });
  expect(MockWebSocket.instances[0].readyState).toBe(3);
  expect(screen.getByRole("status")).toHaveTextContent("The viewer could not connect.");
  await act(async () => { vi.advanceTimersByTime(1000); });
  expect(MockWebSocket.instances).toHaveLength(2);
});

it("refreshes the stream when the same browser is rebound to another execution", async () => {
  const { rerender } = render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  await MockWebSocket.instances[0].frame();
  rerender(<LiveBrowserObserver runId="run-1" browser={{ ...browser, execution_id: "next-execution", journey_id: "next-journey" }} identity="owner" permitted stream={stream} />);
  expect(MockWebSocket.instances[0].readyState).toBe(3);
  expect(MockWebSocket.instances).toHaveLength(2);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
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
  expect(screen.getByRole("status")).toHaveTextContent("The viewer could not connect.");
  expect(screen.getByRole("button", { name: "Retry viewing" })).toBeInTheDocument();
  rerender(<LiveBrowserObserver runId="run-1" browser={{ ...browser, control_state: "human", viewer_state: "suppressed" }} identity="owner" permitted stream={stream} />);
  expect(screen.getByText("Read-only observation is hidden during protected human interaction.")).toBeInTheDocument();
  rerender(<LiveBrowserObserver runId="run-1" browser={{ ...browser, viewer_state: "suppressed" }} identity="owner" permitted stream={stream} />);
  expect(screen.queryByText("Read-only observation is hidden during protected human interaction.")).not.toBeInTheDocument();
  expect(screen.getByText(/Live observation is temporarily unavailable for this execution/)).toBeInTheDocument();
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

it("ends the viewing session without reconnecting when authority is revoked", async () => {
  vi.useFakeTimers();
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  socket.open();
  await socket.frame();
  act(() => socket.onclose?.(new CloseEvent("close", { code: 1008, reason: "authority_revoked" })));
  expect(screen.getByRole("status")).toHaveTextContent("This viewing session has ended");
  await act(async () => { vi.advanceTimersByTime(30000); });
  expect(MockWebSocket.instances).toHaveLength(1);
  vi.useRealTimers();
});

it("reconnects with the interrupted message after a stream failure close", async () => {
  vi.useFakeTimers();
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  socket.open();
  await socket.frame();
  act(() => socket.onclose?.(new CloseEvent("close", { code: 1011, reason: "stream_error" })));
  expect(screen.getByRole("status")).toHaveTextContent("Live view interrupted — reconnecting");
  await act(async () => { vi.advanceTimersByTime(1000); });
  expect(MockWebSocket.instances).toHaveLength(2);
  vi.useRealTimers();
});

it("reconnects with the interrupted message after a lease expiry close", async () => {
  vi.useFakeTimers();
  render(<LiveBrowserObserver runId="run-1" browser={browser} identity="owner" permitted stream={stream} />);
  const socket = MockWebSocket.instances[0];
  socket.open();
  await socket.frame();
  act(() => socket.onclose?.(new CloseEvent("close", { code: 1008, reason: "lease_expired" })));
  expect(screen.getByRole("status")).toHaveTextContent("Live view interrupted — reconnecting");
  await act(async () => { vi.advanceTimersByTime(1000); });
  expect(MockWebSocket.instances).toHaveLength(2);
  vi.useRealTimers();
});


import { closeDisposition } from "./LiveBrowserObserver";

it("maps each connect-refusal class to its own message (T-P5-V4)", () => {
  expect(closeDisposition(1008, "ticket_consumed")).toEqual({
    message: "This viewing link was already used — reopen Watch to get a fresh one",
    reconnect: false,
  });
  expect(closeDisposition(1008, "lease_expired")).toEqual({
    message: "This viewing session has ended — reopen Watch",
    reconnect: false,
  });
  expect(closeDisposition(1008, "owner_gone")).toEqual({
    message: "The run's browser has closed",
    reconnect: false,
  });
  expect(closeDisposition(1008, "authority_unmet")).toEqual({
    message: "Viewing isn't available for this run right now",
    reconnect: false,
  });
});

it("keeps the legacy dispositions for every other close (T-P5-V4)", () => {
  // The unauthenticated path never carries a class: an unknown or
  // empty reason keeps exactly the pre-enum behaviour.
  expect(closeDisposition(1008, "authority_revoked")).toEqual({
    message: "This viewing session has ended",
    reconnect: false,
  });
  expect(closeDisposition(1008, "")).toEqual({
    message: "Live view interrupted — reconnecting",
    reconnect: true,
  });
  expect(closeDisposition(1011, "stream_error")).toEqual({
    message: "Live view interrupted — reconnecting",
    reconnect: true,
  });
});
