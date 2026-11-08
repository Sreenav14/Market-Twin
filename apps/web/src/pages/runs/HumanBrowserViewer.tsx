import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

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

function browserCoordinates(canvas: HTMLCanvasElement, clientX: number, clientY: number) {
  const bounds = canvas.getBoundingClientRect();
  const scale = Math.min(bounds.width / canvas.width, bounds.height / canvas.height);
  if (!Number.isFinite(scale) || scale <= 0) return null;
  const left = bounds.left + (bounds.width - canvas.width * scale) / 2;
  const top = bounds.top + (bounds.height - canvas.height * scale) / 2;
  const x = Math.floor((clientX - left) / scale);
  const y = Math.floor((clientY - top) / scale);
  return x >= 0 && y >= 0 && x < canvas.width && y < canvas.height ? { x, y } : null;
}

const diagnosticReasons = new Set([
  "target_origin_denied", "captcha_resource_denied", "unsafe_destination_ip",
  "dns_resolution_failed", "upstream_connection_failed", "browser_transport_failed",
]);
const diagnosticDestinations = new Set(["authorized_target", "known_provider", "unknown_third_party"]);

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
  const ackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const acceptedSequenceRef = useRef(0);
  const pointerRef = useRef<{ id: number; x: number; y: number; lastMove: number; canvas: HTMLCanvasElement } | null>(null);
  const [status, setStatus] = useState("Viewer not connected. Connect to begin browser control.");
  const [delivery, setDelivery] = useState("");
  const [networkNotice, setNetworkNotice] = useState("");

  const canvasWrapRef = useRef<HTMLDivElement>(null);

  const clearPointer = () => {
    const pointer = pointerRef.current;
    pointerRef.current = null;
    const canvas = pointer?.canvas;
    if (pointer && canvas?.hasPointerCapture?.(pointer.id)) canvas.releasePointerCapture(pointer.id);
  };
  const clearInputState = () => {
    clearPointer();
    if (ackTimerRef.current) clearTimeout(ackTimerRef.current);
    ackTimerRef.current = null;
    acceptedSequenceRef.current = 0;
  };

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const socket = socketRef.current;
      socketRef.current = null;
      connectingRef.current = false;
      readyRef.current = false;
      clearInputState();
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
      send({ event: "scroll", delta });
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
    clearInputState();
    setDelivery("");
    setNetworkNotice("");
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
      clearInputState();
      setDelivery("");
      setNetworkNotice("");
      if (readyTimerRef.current) clearTimeout(readyTimerRef.current);
      setStatus(message);
      socket.close(1000, "viewer unavailable");
    };
    readyTimerRef.current = setTimeout(() => {
      fail("No live browser frame arrived. Reconnect, or choose Skip if assistance is unavailable.");
    }, 15_000);
    socket.onopen = () => {
      if (socketRef.current !== socket) return;
      socket.send(JSON.stringify({ ticket: grant.viewer_ticket }));
      setStatus("Authenticating viewer; waiting for the first live browser frame…");
    };
    let newestFrame = 0;
    socket.onmessage = (event: MessageEvent<Blob | string>) => {
      if (socketRef.current !== socket || failure) return;
      if (typeof event.data === "string") {
        if (event.data.length > 4096) return;
        try {
          const reply: unknown = JSON.parse(event.data);
          if (!reply || typeof reply !== "object" || Array.isArray(reply)) return;
          if ("accepted_sequence" in reply && Number.isSafeInteger(reply.accepted_sequence)
              && typeof reply.accepted_sequence === "number"
              && reply.accepted_sequence > acceptedSequenceRef.current
              && reply.accepted_sequence <= sequenceRef.current) {
            acceptedSequenceRef.current = reply.accepted_sequence;
            if (reply.accepted_sequence === sequenceRef.current) {
              if (ackTimerRef.current) clearTimeout(ackTimerRef.current);
              ackTimerRef.current = null;
              if (readyRef.current) setDelivery("Connection active");
            }
          }
          if ("network_diagnostics" in reply && Array.isArray(reply.network_diagnostics)
              && reply.network_diagnostics.length <= 18) {
            const reasons = new Set<string>();
            for (const item of reply.network_diagnostics) {
              if (item && typeof item === "object" && diagnosticReasons.has(item.reason)
                  && diagnosticDestinations.has(item.destination)
                  && Number.isSafeInteger(item.count) && item.count > 0 && item.count <= 100_000) {
                reasons.add(item.reason);
              }
            }
            setNetworkNotice([
              [...reasons].some((reason) => ["target_origin_denied", "captcha_resource_denied", "unsafe_destination_ip"].includes(reason))
                ? "Some browser resources were blocked by network policy." : "",
              reasons.has("dns_resolution_failed") ? "Some browser resources could not be resolved." : "",
              reasons.has("upstream_connection_failed") || reasons.has("browser_transport_failed")
                ? "Some browser resources could not connect." : "",
            ].filter(Boolean).join(" "));
          }
        } catch { /* Ignore unrecognized control messages without exposing their payload. */ }
        return;
      }
      const frame = ++newestFrame;
      void createImageBitmap(event.data).then((image) => {
        try {
          const canvas = canvasRef.current;
          if (!canvas || socketRef.current !== socket || failure || frame !== newestFrame) return;
          canvas.width = image.width;
          canvas.height = image.height;
          canvasWrapRef.current?.style.setProperty("--viewer-aspect-ratio", `${image.width} / ${image.height}`);
          const context = canvas.getContext("2d");
          if (!context) {
            fail("The live browser frame could not be displayed. Reconnect to try again.");
            return;
          }
          context.drawImage(image, 0, 0);
          if (!readyRef.current) setDelivery("Connection active");
          readyRef.current = true;
          connectingRef.current = false;
          if (readyTimerRef.current) clearTimeout(readyTimerRef.current);
          setStatus("Connected. Browser frames and input are not saved.");
        } finally { image.close(); }
      }).catch(() => {
        if (frame === newestFrame) fail("The live browser frame could not be displayed. Reconnect to try again.");
      });
    };
    socket.onerror = () => fail("The protected browser connection failed. Reconnect to try again.");
    socket.onclose = () => {
      if (socketRef.current !== socket) return;
      socketRef.current = null;
      connectingRef.current = false;
      readyRef.current = false;
      clearInputState();
      setDelivery("");
      setNetworkNotice("");
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
    if (pointerRef.current && !["pointer_move", "pointer_up", "pointer_cancel"].includes(String(payload.event))) return false;
    const socket = socketRef.current;
    if (readyRef.current && socket?.readyState === WebSocket.OPEN) {
      sequenceRef.current += 1;
      try {
        socket.send(JSON.stringify({ sequence: sequenceRef.current, ...payload }));
      } catch {
        readyRef.current = false;
        clearInputState();
        setDelivery("");
        setNetworkNotice("");
        setStatus("The protected browser connection failed. Reconnect to try again.");
        socket.close(1000, "viewer unavailable");
        return false;
      }
      if (!ackTimerRef.current) {
        ackTimerRef.current = setTimeout(() => {
          ackTimerRef.current = null;
          if (socketRef.current === socket && readyRef.current
              && acceptedSequenceRef.current < sequenceRef.current) setDelivery("Input delayed");
        }, 2000);
      }
      return true;
    }
    return false;
  };

  const finishPointer = (event: ReactPointerEvent<HTMLCanvasElement>, cancelled: boolean) => {
    const pointer = pointerRef.current;
    if (!pointer || event.pointerId !== pointer.id) return;
    const coordinates = browserCoordinates(event.currentTarget, event.clientX, event.clientY);
    send({ event: cancelled || !coordinates ? "pointer_cancel" : "pointer_up",
      ...(coordinates ?? { x: pointer.x, y: pointer.y }) });
    clearPointer();
    event.preventDefault();
  };

  const sendText = (value: string) => {
    if (value) send({ event: "text", text: value });
  };

  return (
    <div className="human-browser-viewer evidence-stage">

      {/* ── Top toolbar: status line + connect/reconnect button ── */}
      <div className="hbv-toolbar">
        <p role="status" className="hbv-status">{status}</p>
        {delivery ? <span aria-label="Input delivery">{delivery}</span> : null}
        {!socketRef.current
          ? <button type="button" className="secondary-button hbv-connect-btn" onClick={() => void connect()}>
              {attemptedRef.current ? "Reconnect to protected browser" : "Connect to protected browser"}
            </button>
          : null}
      </div>
      {networkNotice ? <p role="note" aria-label="Connection diagnostics">{networkNotice}</p> : null}

      {/* ── Full-width canvas; CSS gives it a tall aspect-ratio box so the browser frame is large ── */}
      <div className="hbv-viewport">
      <div ref={canvasWrapRef} className="hbv-canvas-wrap" data-ready={readyRef.current}>
        <canvas
          ref={canvasRef}
          aria-label="Live protected browser"
          aria-describedby="viewer-keyboard-help"
          onPointerDown={(event) => {
            if (!readyRef.current || pointerRef.current || event.isPrimary === false || event.button !== 0) return;
            const coordinates = browserCoordinates(event.currentTarget, event.clientX, event.clientY);
            if (!coordinates || !send({ event: "pointer_down", ...coordinates })) return;
            pointerRef.current = { id: event.pointerId, ...coordinates, lastMove: -Infinity, canvas: event.currentTarget };
            event.currentTarget.setPointerCapture?.(event.pointerId);
            event.currentTarget.focus();
            event.preventDefault();
          }}
          onPointerMove={(event) => {
            const pointer = pointerRef.current;
            if (!pointer || event.pointerId !== pointer.id) return;
            const coordinates = browserCoordinates(event.currentTarget, event.clientX, event.clientY);
            if (!coordinates) return;
            pointer.x = coordinates.x;
            pointer.y = coordinates.y;
            if (Date.now() - pointer.lastMove < 1000 / 15) return;
            pointer.lastMove = Date.now();
            send({ event: "pointer_move", ...coordinates });
            event.preventDefault();
          }}
          onPointerUp={(event) => finishPointer(event, false)}
          onPointerCancel={(event) => finishPointer(event, true)}
          onLostPointerCapture={(event) => finishPointer(event, true)}
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
        <button type="button" className="hbv-scroll-button" aria-label="Scroll live website up" disabled={!readyRef.current}
          onClick={() => send({ event: "scroll", delta: -400 })}>↑</button>
        <span aria-hidden="true">Scroll</span>
        <button type="button" className="hbv-scroll-button" aria-label="Scroll live website down" disabled={!readyRef.current}
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
        When connected, browser Tab navigation is forwarded to the test page. Press <kbd className="kbd">Shift</kbd>+<kbd className="kbd">Escape</kbd> to leave browser keyboard control. When disconnected, Tab moves through workspace controls.
      </p>
    </div>
  );
}
