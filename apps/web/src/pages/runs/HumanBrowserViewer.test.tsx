import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HumanBrowserViewer } from "./HumanBrowserViewer";

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
}

describe("HumanBrowserViewer", () => {
  afterEach(() => {
    MockWebSocket.instances = [];
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("uses the one-time ticket only in the first protected websocket message", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    render(<HumanBrowserViewer url="wss://local.test/api/v1/hitl-viewer" ticket="single-use-ticket" />);

    expect(MockWebSocket.instances).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Connect to protected browser" }));
    const socket = MockWebSocket.instances[0];
    expect(socket.url).toBe("wss://local.test/api/v1/hitl-viewer");
    expect(socket.url).not.toContain("ticket=");
    act(() => socket.open());
    expect(socket.sent).toEqual([JSON.stringify({ ticket: "single-use-ticket" })]);

    const input = screen.getByLabelText("Type into the protected browser");
    fireEvent.change(input, { target: { value: "synthetic-password" } });
    expect(socket.sent[1]).toBe(JSON.stringify({ sequence: 1, event: "text", text: "synthetic-password" }));
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("requests a fresh ticket after disconnect and resets input sequence", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const reconnect = vi.fn().mockResolvedValue({
      viewer_url: "wss://local.test/api/v1/hitl-viewer", viewer_ticket: "fresh-ticket",
    });
    render(<HumanBrowserViewer url="wss://local.test/api/v1/hitl-viewer" ticket="first-ticket" onReconnect={reconnect} />);
    fireEvent.click(screen.getByRole("button", { name: "Connect to protected browser" }));
    const first = MockWebSocket.instances[0];
    act(() => first.open());
    fireEvent.change(screen.getByLabelText("Type into the protected browser"), { target: { value: "synthetic" } });
    act(() => first.disconnect());
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Reconnect to protected browser" })));
    expect(reconnect).toHaveBeenCalledOnce();
    const second = MockWebSocket.instances[1];
    act(() => second.open());
    expect(second.sent).toEqual([JSON.stringify({ ticket: "fresh-ticket" })]);
    fireEvent.change(screen.getByLabelText("Type into the protected browser"), { target: { value: "more-synthetic" } });
    expect(JSON.parse(second.sent[1]).sequence).toBe(1);
    expect(second.sent.join("")).not.toContain("first-ticket");
  });
});
