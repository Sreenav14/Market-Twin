import { useEffect, useRef, useState } from "react";

interface HumanBrowserViewerProps {
  url: string;
  ticket: string;
  autoConnect?: boolean;
  onReconnect?: () => Promise<{ viewer_url: string; viewer_ticket: string }>;
}

const permittedKeys = new Set([
  "Tab", "Shift+Tab", "Enter", "Backspace", "Delete", "Escape", "ArrowUp", "ArrowDown",
  "ArrowLeft", "ArrowRight", "Home", "End",
]);

function safeViewerUrl(value: string): string {
  const target = new URL(value);
  const expectedProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  if (target.protocol !== expectedProtocol || target.host !== window.location.host
      || target.pathname !== "/api/v1/hitl-viewer" || target.search || target.hash
      || target.username || target.password) {
    throw new Error("Untrusted browser viewer address.");
  }
  return target.href;
}

/** Volatile, ticket-authenticated view of the worker-owned browser. */
export function HumanBrowserViewer({ url, ticket, onReconnect, autoConnect = false }: HumanBrowserViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const leaveControlRef = useRef<HTMLButtonElement>(null);
  const textInputRef = useRef<HTMLInputElement>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const sequenceRef = useRef(0);
  const attemptedRef = useRef(false);
  const connectingRef = useRef(false);
  const mountedRef = useRef(true);
  const readyRef = useRef(false);
  const readyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [status, setStatus] = useState("Viewer not connected. Connect to begin browser control.");

  const canvasWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const socket = socketRef.current;
      socketRef.current = null;
      connectingRef.current = false;
      readyRef.current = false;
      if (readyTimerRef.current) clearTimeout(readyTimerRef.current);
      socket?.close(1000, "operator left viewer");
    };
  }, []);

  // A native non-passive listener isolates remote scrolling while input is ready.
  useEffect(() => {
    const wrap = canvasWrapRef.current;
    if (!wrap) return;
    const onWheel = (e: WheelEvent) => {
      if (!readyRef.current || socketRef.current?.readyState !== WebSocket.OPEN) return;
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? wrap.clientHeight : 1;
      const delta = Math.max(-1000, Math.min(1000, Math.trunc(e.deltaY * unit)));
      if (!delta) return;
      e.preventDefault();
      e.stopPropagation();
      sequenceRef.current += 1;
      socketRef.current.send(JSON.stringify({ sequence: sequenceRef.current, event: "scroll", delta }));
    };
    wrap.addEventListener("wheel", onWheel, { passive: false });
    return () => wrap.removeEventListener("wheel", onWheel);
  }, []);


  const connect = async () => {
    if (socketRef.current || connectingRef.current) return;
    connectingRef.current = true;
    let grant = { viewer_url: url, viewer_ticket: ticket };
    let viewerUrl: string;
    try {
      if (attemptedRef.current) {
        if (!onReconnect) throw new Error("A fresh viewer ticket is required.");
        grant = await onReconnect();
      }
      viewerUrl = safeViewerUrl(grant.viewer_url);
    } catch {
      connectingRef.current = false;
      setStatus("Reconnect unavailable. The lease may have expired; check the request status.");
      return;
    }
    if (!mountedRef.current) return;
    attemptedRef.current = true;
    sequenceRef.current = 0;
    readyRef.current = false;
    let socket: WebSocket;
    try {
      socket = new WebSocket(viewerUrl);
    } catch {
      connectingRef.current = false;
      setStatus("The protected browser connection failed. Reconnect to try again.");
      return;
    }
    socket.binaryType = "blob";
    socketRef.current = socket;
    let failure: string | null = null;
    const fail = (message: string) => {
      if (socketRef.current !== socket) return;
      failure = message;
      readyRef.current = false;
      if (readyTimerRef.current) clearTimeout(readyTimerRef.current);
      setStatus(message);
      socket.close(1000, "viewer unavailable");
    };
    readyTimerRef.current = setTimeout(() => {
      fail("No live browser frame arrived. Reconnect, or choose Skip if assistance is unavailable.");
    }, 15_000);
    socket.onopen = () => {
      socket.send(JSON.stringify({ ticket: grant.viewer_ticket }));
      setStatus("Authenticating viewer; waiting for the first live browser frame…");
    };
    socket.onmessage = (event: MessageEvent<Blob | string>) => {
      if (typeof event.data === "string") return;
      void createImageBitmap(event.data).then((image) => {
        const canvas = canvasRef.current;
        if (canvas && socketRef.current === socket && !failure) {
          canvas.width = image.width;
          canvas.height = image.height;
          canvasWrapRef.current?.style.setProperty("--viewer-aspect-ratio", `${image.width} / ${image.height}`);
          const context = canvas.getContext("2d");
          if (!context) {
            image.close();
            fail("The live browser frame could not be displayed. Reconnect to try again.");
            return;
          }
          context.drawImage(image, 0, 0);
          readyRef.current = true;
          connectingRef.current = false;
          if (readyTimerRef.current) clearTimeout(readyTimerRef.current);
          setStatus("Connected. Browser frames and input are not saved.");
        }
        image.close();
      }).catch(() => fail("The live browser frame could not be displayed. Reconnect to try again."));
    };
    socket.onerror = () => fail("The protected browser connection failed. Reconnect to try again.");
    socket.onclose = () => {
      if (socketRef.current !== socket) return;
      socketRef.current = null;
      connectingRef.current = false;
      readyRef.current = false;
      if (readyTimerRef.current) clearTimeout(readyTimerRef.current);
      const canvas = canvasRef.current;
      canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
      setStatus(failure ?? "Viewer disconnected. Reconnect while the lease is active, or release control.");
    };
    setStatus("Connecting to the protected browser…");
  };

  useEffect(() => {
    if (autoConnect) void connect();
  }, [autoConnect]);

  const send = (payload: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (readyRef.current && socket?.readyState === WebSocket.OPEN) {
      sequenceRef.current += 1;
      socket.send(JSON.stringify({ sequence: sequenceRef.current, ...payload }));
    }
  };

  const sendText = (value: string) => {
    if (value) send({ event: "text", text: value });
  };

  return (
    <div className="human-browser-viewer">

      {/* ── Top toolbar: status line + connect/reconnect button ── */}
      <div className="hbv-toolbar">
        <p role="status" className="hbv-status">{status}</p>
        {!socketRef.current
          ? <button type="button" className="secondary-button hbv-connect-btn" onClick={() => void connect()}>
              {attemptedRef.current ? "Reconnect to protected browser" : "Connect to protected browser"}
            </button>
          : null}
      </div>

      {/* ── Full-width canvas; CSS gives it a tall aspect-ratio box so the browser frame is large ── */}
      <div className="hbv-viewport">
      <div ref={canvasWrapRef} className="hbv-canvas-wrap" data-ready={readyRef.current}>
        <canvas
          ref={canvasRef}
          aria-label="Live protected browser"
          aria-describedby="viewer-keyboard-help"
          onPointerDown={(event) => {
            if (!readyRef.current) return;
            const bounds = event.currentTarget.getBoundingClientRect();
            const scaleX = event.currentTarget.width / bounds.width;
            const scaleY = event.currentTarget.height / bounds.height;
            send({
              event: "click",
              x: Math.max(0, Math.floor((event.clientX - bounds.left) * scaleX)),
              y: Math.max(0, Math.floor((event.clientY - bounds.top) * scaleY)),
            });
            event.currentTarget.focus();
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape" && event.shiftKey) {
              event.preventDefault();
              leaveControlRef.current?.focus();
              return;
            }
            if (!readyRef.current) return;
            const key = event.key === "Tab" && event.shiftKey ? "Shift+Tab" : event.key;
            if (permittedKeys.has(key)) {
              event.preventDefault();
              send({ event: "key", key });
            } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
              event.preventDefault();
              sendText(event.key);
            }
          }}
          tabIndex={0}
          style={{ display: "block", width: "100%", height: "100%", touchAction: "none" }}
        />
      </div>
      <div className="hbv-scroll-controls" role="group" aria-label="Live website scrolling">
        <button type="button" aria-label="Scroll live website up" disabled={!readyRef.current}
          onClick={() => send({ event: "scroll", delta: -400 })}>↑</button>
        <span aria-hidden="true">Scroll</span>
        <button type="button" aria-label="Scroll live website down" disabled={!readyRef.current}
          onClick={() => send({ event: "scroll", delta: 400 })}>↓</button>
      </div>
      </div>

      {/* ── Bottom toolbar: text input + leave-control button (all in one strip) ── */}
      <div className="hbv-toolbar hbv-toolbar--bottom">
        <label className="visually-hidden" htmlFor="human-browser-text">Type into the protected browser</label>
        <input
          ref={textInputRef}
          id="human-browser-text"
          type="password"
          placeholder="Type here to send keystrokes…"
          disabled={!readyRef.current}
          autoComplete="off"
          aria-label="Type into the protected browser"
          aria-describedby="viewer-keyboard-help"
          className="hbv-text-input"
          onChange={(event) => {
            sendText(event.currentTarget.value);
            event.currentTarget.value = "";
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape" && event.shiftKey) {
              event.preventDefault();
              leaveControlRef.current?.focus();
              return;
            }
            if (!readyRef.current) return;
            const key = event.key === "Tab" && event.shiftKey ? "Shift+Tab" : event.key;
            if (permittedKeys.has(key)) {
              event.preventDefault();
              send({ event: "key", key });
            }
          }}
        />
        <button
          ref={leaveControlRef}
          type="button"
          className="secondary-button hbv-leave-btn"
          onClick={() => { canvasRef.current?.blur(); textInputRef.current?.blur(); }}
        >
          Leave browser keyboard control
        </button>
      </div>

      <p className="viewer-keyboard-help" id="viewer-keyboard-help">
        When connected, browser Tab navigation is forwarded to the test page. Press Shift+Escape to leave browser keyboard control. When disconnected, Tab moves through workspace controls.
      </p>
    </div>
  );
}
