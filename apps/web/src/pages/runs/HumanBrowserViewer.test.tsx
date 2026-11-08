import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";

import { HumanBrowserViewer } from "./HumanBrowserViewer";

const viewerUrl = `ws://${window.location.host}/api/v1/hitl-viewer`;

class MockPointerEvent extends MouseEvent {
  readonly pointerId: number;
  readonly isPrimary: boolean;
  constructor(type: string, options: PointerEventInit = {}) {
    super(type, options);
    this.pointerId = options.pointerId ?? 1;
    this.isPrimary = options.isPrimary ?? true;
  }
}

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

  message(value: unknown) {
    act(() => this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent<string>));
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
    vi.stubGlobal("PointerEvent", MockPointerEvent);
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
    expect(document.getElementById("viewer-keyboard-help")?.textContent).toContain("Press Shift+Escape to leave browser keyboard control.");
    expect(document.querySelectorAll("#viewer-keyboard-help kbd.kbd")).toHaveLength(2);
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
    expect(JSON.parse(socket.sent[1])).toEqual({ sequence: 1, event: "pointer_down", x: 640, y: 360 });
    fireEvent.pointerUp(canvas, { clientX: 330, clientY: 200 });
    expect(JSON.parse(socket.sent[2])).toEqual({ sequence: 2, event: "pointer_up", x: 640, y: 360 });
    bounds.mockReturnValue({ left: 10, top: 20, width: 320, height: 180 } as DOMRect);
    fireEvent.pointerDown(canvas, { clientX: 90, clientY: 65 });
    expect(JSON.parse(socket.sent[3])).toEqual({ sequence: 3, event: "pointer_down", x: 320, y: 180 });
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

  it("ignores letterboxes and maps contained image coordinates before delivering a drag", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    const canvas = screen.getByLabelText("Live protected browser") as HTMLCanvasElement;
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 10, top: 20, width: 640, height: 640 } as DOMRect);
    const capture = vi.fn(), release = vi.fn();
    canvas.setPointerCapture = capture;
    canvas.hasPointerCapture = vi.fn().mockReturnValue(true);
    canvas.releasePointerCapture = release;
    fireEvent.pointerDown(canvas, { clientX: 330, clientY: 100 });
    expect(socket.sent).toHaveLength(1);
    fireEvent.pointerDown(canvas, { clientX: 330, clientY: 340, pointerId: 4 });
    fireEvent.pointerMove(canvas, { clientX: 490, clientY: 340, pointerId: 4 });
    fireEvent.pointerUp(canvas, { clientX: 570, clientY: 340, pointerId: 4 });
    expect(socket.sent.slice(1).map((message) => JSON.parse(message))).toEqual([
      { sequence: 1, event: "pointer_down", x: 640, y: 360 },
      { sequence: 2, event: "pointer_move", x: 960, y: 360 },
      { sequence: 3, event: "pointer_up", x: 1120, y: 360 },
    ]);
    expect(capture).toHaveBeenCalledWith(4);
    expect(release).toHaveBeenCalledWith(4);
    fireEvent.click(canvas);
    expect(socket.sent).toHaveLength(4);
  });

  it("limits moves, ignores additional pointers and cancels held input exactly once", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    const canvas = screen.getByLabelText("Live protected browser");
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 1280, height: 720 } as DOMRect);
    fireEvent.pointerDown(canvas, { clientX: 100, clientY: 100 });
    fireEvent.pointerDown(canvas, { clientX: 200, clientY: 100, pointerId: 2, isPrimary: false });
    fireEvent.click(screen.getByRole("button", { name: "Scroll live website down" }));
    fireEvent.keyDown(canvas, { key: "Tab" });
    fireEvent.change(screen.getByLabelText("Type into the protected browser"), { target: { value: "synthetic" } });
    expect(socket.sent).toHaveLength(2);
    for (let index = 0; index < 100; index++) {
      fireEvent.pointerMove(canvas, { clientX: 200 + index, clientY: 100 });
      act(() => vi.advanceTimersByTime(10));
    }
    expect(socket.sent.map((message) => JSON.parse(message)).filter((message) => message.event === "pointer_move").length)
      .toBeLessThanOrEqual(15);
    fireEvent.pointerCancel(canvas, { clientX: 300, clientY: 100 });
    fireEvent.pointerUp(canvas, { clientX: 300, clientY: 100 });
    const events = socket.sent.slice(1).map((message) => JSON.parse(message).event);
    expect(events.filter((event) => event === "pointer_down")).toHaveLength(1);
    expect(events.at(-1)).toBe("pointer_cancel");
    expect(events).not.toContain("pointer_up");
    expect(events).not.toContain("click");
  });

  it("clears held pointer state when the socket disconnects and ignores later pointer events", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    const view = render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    const canvas = screen.getByLabelText("Live protected browser") as HTMLCanvasElement;
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 1280, height: 720 } as DOMRect);
    canvas.hasPointerCapture = vi.fn().mockReturnValue(true);
    canvas.releasePointerCapture = vi.fn();
    fireEvent.pointerDown(canvas, { clientX: 100, clientY: 100 });
    act(() => socket.disconnect());
    fireEvent.pointerMove(canvas, { clientX: 200, clientY: 100 });
    fireEvent.pointerUp(canvas, { clientX: 200, clientY: 100 });
    expect(socket.sent).toHaveLength(2);
    expect(canvas.releasePointerCapture).toHaveBeenCalledWith(1);
    expect(screen.queryByLabelText("Input delivery")).not.toBeInTheDocument();
    view.unmount();
  });

  it("does not let an older asynchronous frame overwrite the newest displayed frame", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    let resolveOld!: (value: ImageBitmap) => void;
    let resolveNew!: (value: ImageBitmap) => void;
    vi.stubGlobal("createImageBitmap", vi.fn()
      .mockImplementationOnce(() => new Promise<ImageBitmap>((resolve) => { resolveOld = resolve; }))
      .mockImplementationOnce(() => new Promise<ImageBitmap>((resolve) => { resolveNew = resolve; })));
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    await socket.frame();
    const newer = { width: 800, height: 600, close: vi.fn() } as unknown as ImageBitmap;
    const older = { width: 1280, height: 720, close: vi.fn() } as unknown as ImageBitmap;
    await act(async () => resolveNew(newer));
    await act(async () => resolveOld(older));
    const canvas = screen.getByLabelText("Live protected browser") as HTMLCanvasElement;
    expect(canvas.width).toBe(800);
    expect(canvas.getContext("2d")?.drawImage).toHaveBeenCalledExactlyOnceWith(newer, 0, 0);
    expect(older.close).toHaveBeenCalledOnce();
    expect(newer.close).toHaveBeenCalledOnce();
  });

  it("releases local capture and closes the viewer when unmounted during a drag", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    const view = render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    const canvas = screen.getByLabelText("Live protected browser") as HTMLCanvasElement;
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 1280, height: 720 } as DOMRect);
    canvas.hasPointerCapture = vi.fn().mockReturnValue(true);
    canvas.releasePointerCapture = vi.fn();
    fireEvent.pointerDown(canvas, { clientX: 100, clientY: 100 });
    view.unmount();
    expect(socket.readyState).toBe(3);
    expect(socket.sent).toHaveLength(2);
    expect(canvas.releasePointerCapture).toHaveBeenCalledWith(1);
  });

  it("reports delayed delivery until the current input is acknowledged without claiming login success", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    fireEvent.click(screen.getByRole("button", { name: "Scroll live website down" }));
    expect(screen.getByLabelText("Input delivery")).toHaveTextContent("Connection active");
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByLabelText("Input delivery")).toHaveTextContent("Input delayed");
    await socket.frame();
    socket.message({ accepted_sequence: 99 });
    socket.message({ accepted_sequence: 0 });
    expect(screen.getByLabelText("Input delivery")).toHaveTextContent("Input delayed");
    socket.message({ accepted_sequence: 1 });
    expect(screen.getByLabelText("Input delivery")).toHaveTextContent("Connection active");
    expect(screen.queryByText(/captcha verified|login verified|authenticated successfully/i)).not.toBeInTheDocument();
  });

  it("shows only fixed bounded network notices and clears expired diagnostics", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer autoConnect url={viewerUrl} ticket="one-use" />);
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    await socket.frame();
    socket.message({ network_diagnostics: [
      { reason: "captcha_resource_denied", destination: "known_provider", count: 2, url: "https://secret.invalid/token" },
      { reason: "dns_resolution_failed", destination: "authorized_target", count: 1 },
      { reason: "secret-login-payload", destination: "unknown_third_party", count: 1 },
    ] });
    expect(screen.getByRole("note", { name: "Connection diagnostics" })).toHaveTextContent("blocked by network policy");
    expect(screen.getByRole("note")).toHaveTextContent("could not be resolved");
    expect(screen.queryByText(/secret.invalid|secret-login-payload/)).not.toBeInTheDocument();
    socket.message({ network_diagnostics: [] });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

});
