import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";

import { HumanBrowserViewer } from "./HumanBrowserViewer";

const viewerUrl = `ws://${window.location.host}/api/v1/hitl-viewer`;

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

  disconnect() {
    this.close();
    this.onclose?.(new Event("close") as CloseEvent);
  }

  async frame() {
    await act(async () => this.onmessage?.({ data: new Blob(["synthetic-frame"]) } as MessageEvent<Blob>));
  }
}

describe("HumanBrowserViewer", () => {
  it.each([
    "wss://evil.test/api/v1/hitl-viewer",
    `ws://${window.location.host}/wrong-path`,
    `ws://${window.location.host}/api/v1/hitl-viewer?ticket=leak`,
    "javascript:alert(1)",
  ])("rejects an untrusted viewer URL before sending a ticket: %s", async (url) => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer autoConnect url={url} ticket="must-stay-local" />);
    expect(MockWebSocket.instances).toHaveLength(0);
    expect(screen.getByRole("status")).toHaveTextContent("Reconnect unavailable");
  });
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage: vi.fn(), clearRect: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 1280, height: 720, close: vi.fn() }));
  });
  afterEach(() => {
    MockWebSocket.instances = [];
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("uses the one-time ticket only in the first protected websocket message", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer url={viewerUrl} ticket="single-use-ticket" />);

    expect(MockWebSocket.instances).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Connect to protected browser" }));
    const socket = MockWebSocket.instances[0];
    expect(socket.url).toBe(viewerUrl);
    expect(socket.url).not.toContain("ticket=");
    act(() => socket.open());
    expect(socket.sent).toEqual([JSON.stringify({ ticket: "single-use-ticket" })]);
    expect(screen.getByRole("status")).toHaveTextContent("waiting for the first live browser frame");
    fireEvent.change(screen.getByLabelText("Type into the protected browser"), { target: { value: "not-forwarded" } });
    expect(socket.sent).toHaveLength(1);
    await socket.frame();
    expect(screen.getByRole("status")).toHaveTextContent("Connected. Browser frames and input are not saved.");

    const input = screen.getByLabelText("Type into the protected browser");
    fireEvent.change(input, { target: { value: "synthetic-password" } });
    expect(socket.sent[1]).toBe(JSON.stringify({ sequence: 1, event: "text", text: "synthetic-password" }));
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("requests a fresh ticket after disconnect and resets input sequence", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    const reconnect = vi.fn().mockResolvedValue({
      viewer_url: viewerUrl, viewer_ticket: "fresh-ticket",
    });
    render(<HumanBrowserViewer url={viewerUrl} ticket="first-ticket" onReconnect={reconnect} />);
    fireEvent.click(screen.getByRole("button", { name: "Connect to protected browser" }));
    const first = MockWebSocket.instances[0];
    act(() => first.open());
    await first.frame();
    fireEvent.change(screen.getByLabelText("Type into the protected browser"), { target: { value: "synthetic" } });
    act(() => first.disconnect());
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Reconnect to protected browser" })));
    expect(reconnect).toHaveBeenCalledOnce();
    const second = MockWebSocket.instances[1];
    act(() => second.open());
    expect(second.sent).toEqual([JSON.stringify({ ticket: "fresh-ticket" })]);
    await second.frame();
    fireEvent.change(screen.getByLabelText("Type into the protected browser"), { target: { value: "more-synthetic" } });
    expect(JSON.parse(second.sent[1]).sequence).toBe(1);
    expect(second.sent.join("")).not.toContain("first-ticket");
  });

  it("lets a keyboard operator leave browser-page tab control and continue to Release", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    const user = userEvent.setup();
    render(<><HumanBrowserViewer url={viewerUrl} ticket="one-time" /><button>Release control for verification</button></>);
    fireEvent.click(screen.getByRole("button", { name: "Connect to protected browser" }));
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    const canvas = screen.getByLabelText("Live protected browser");
    expect(canvas).toHaveAccessibleDescription(/Press Shift\+Escape/);
    canvas.focus();
    fireEvent.keyDown(canvas, { key: "Escape", shiftKey: true });
    const leave = screen.getByRole("button", { name: "Leave browser keyboard control" });
    expect(leave).toHaveFocus();
    expect(screen.getByText(/Press Shift\+Escape to leave browser keyboard control/)).toBeInTheDocument();
    await user.tab();
    expect(screen.getByRole("button", { name: "Release control for verification" })).toHaveFocus();
  });

  it("keeps local Tab navigation available before readiness and after disconnect", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    const user = userEvent.setup();
    render(<HumanBrowserViewer url={viewerUrl} ticket="one-time" />);
    const canvas = screen.getByLabelText("Live protected browser");
    const input = screen.getByLabelText("Type into the protected browser");
    expect(input).toBeDisabled();
    canvas.focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Leave browser keyboard control" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Connect to protected browser" }));
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    expect(fireEvent.keyDown(canvas, { key: "Tab" })).toBe(true);
    expect(socket.sent).toHaveLength(1);
    await socket.frame();
    expect(input).toBeEnabled();
    expect(fireEvent.keyDown(canvas, { key: "Tab" })).toBe(false);
    expect(JSON.parse(socket.sent[1])).toEqual({ sequence: 1, event: "key", key: "Tab" });
    act(() => socket.disconnect());
    expect(input).toBeDisabled();
    canvas.focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Leave browser keyboard control" })).toHaveFocus();
    expect(socket.sent).toHaveLength(2);
  });
  it("maps pointer input to the unchanged browser viewport after responsive resize", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    vi.stubGlobal("PointerEvent", MouseEvent);
    render(<HumanBrowserViewer url={viewerUrl} ticket="synthetic-ticket" />);
    fireEvent.click(screen.getByRole("button", { name: "Connect to protected browser" }));
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    const canvas = screen.getByLabelText("Live protected browser") as HTMLCanvasElement;
    canvas.width = 1280;
    canvas.height = 720;
    const bounds = vi.spyOn(canvas, "getBoundingClientRect");
    bounds.mockReturnValue({ left: 10, top: 20, width: 640, height: 360 } as DOMRect);
    fireEvent.pointerDown(canvas, { clientX: 330, clientY: 200 });
    expect(JSON.parse(socket.sent[1])).toEqual({ sequence: 1, event: "click", x: 640, y: 360 });
    bounds.mockReturnValue({ left: 10, top: 20, width: 320, height: 180 } as DOMRect);
    fireEvent.pointerDown(canvas, { clientX: 90, clientY: 65 });
    expect(JSON.parse(socket.sent[2])).toEqual({ sequence: 2, event: "click", x: 320, y: 180 });
  });

  it("connects immediately after an explicit control claim, without claiming readiness on socket open", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    expect(MockWebSocket.instances).toHaveLength(1);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    expect(screen.getByRole("status")).not.toHaveTextContent(/^Connected\./);
    await socket.frame();
    expect(screen.getByRole("status")).toHaveTextContent(/^Connected\./);
  });

  it("times out a connection with no first frame and never enables input", () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    act(() => vi.advanceTimersByTime(15_000));
    expect(screen.getByRole("status")).toHaveTextContent("No live browser frame arrived");
    expect(socket.readyState).toBe(3);
    fireEvent.change(screen.getByLabelText("Type into the protected browser"), { target: { value: "not-forwarded" } });
    expect(socket.sent).toHaveLength(1);
  });

  it("does not claim a connection is ready when a frame cannot be decoded", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("Invalid image")));
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    expect(screen.getByRole("status")).toHaveTextContent("could not be displayed");
    expect(socket.readyState).toBe(3);
  });

  it("isolates wheel input exactly once while ready and exposes compact scroll controls", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    const canvas = screen.getByLabelText("Live protected browser");
    const down = screen.getByRole("button", { name: "Scroll live website down" });
    expect(down).toBeDisabled();
    const offline = new WheelEvent("wheel", { deltaY: 90, bubbles: true, cancelable: true });
    canvas.dispatchEvent(offline);
    expect(offline.defaultPrevented).toBe(false);
    act(() => socket.open());
    await socket.frame();
    expect(down).toBeEnabled();
    const wheel = new WheelEvent("wheel", { deltaY: 3, deltaMode: 1, bubbles: true, cancelable: true });
    canvas.dispatchEvent(wheel);
    expect(wheel.defaultPrevented).toBe(true);
    expect(socket.sent.map((item) => JSON.parse(item))).toEqual([
      { ticket: "one-use" }, { sequence: 1, event: "scroll", delta: 48 },
    ]);
    fireEvent.click(down);
    expect(JSON.parse(socket.sent[2])).toEqual({ sequence: 2, event: "scroll", delta: 400 });
    expect(canvas.parentElement?.style.getPropertyValue("--viewer-aspect-ratio")).toBe("1280 / 720");
    act(() => socket.disconnect());
    const disconnected = new WheelEvent("wheel", { deltaY: 90, bubbles: true, cancelable: true });
    canvas.dispatchEvent(disconnected);
    expect(disconnected.defaultPrevented).toBe(false);
    expect(down).toBeDisabled();
  });

});
