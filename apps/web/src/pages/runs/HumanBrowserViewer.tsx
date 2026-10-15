import { useEffect, useRef, useState } from "react";

interface HumanBrowserViewerProps {
  url: string;
  ticket: string;
  onReconnect?: () => Promise<{ viewer_url: string; viewer_ticket: string }>;
}

const permittedKeys = new Set([
  "Tab", "Shift+Tab", "Enter", "Backspace", "Delete", "Escape", "ArrowUp", "ArrowDown",
  "ArrowLeft", "ArrowRight", "Home", "End",
]);

/** Volatile, ticket-authenticated view of the worker-owned browser. */
export function HumanBrowserViewer({ url, ticket, onReconnect }: HumanBrowserViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const leaveControlRef = useRef<HTMLButtonElement>(null);
  const textInputRef = useRef<HTMLInputElement>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const sequenceRef = useRef(0);
  const attemptedRef = useRef(false);
  const connectingRef = useRef(false);
  const mountedRef = useRef(true);
  const [status, setStatus] = useState("Viewer not connected. Connect to begin browser control.");

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const socket = socketRef.current;
      socketRef.current = null;
      socket?.close(1000, "operator left viewer");
    };
  }, []);

  const connect = async () => {
    if (socketRef.current || connectingRef.current) return;
    connectingRef.current = true;
    let grant = { viewer_url: url, viewer_ticket: ticket };
    try {
      if (attemptedRef.current) {
        if (!onReconnect) throw new Error("A fresh viewer ticket is required.");
        grant = await onReconnect();
      }
    } catch {
      connectingRef.current = false;
      setStatus("Reconnect unavailable. The lease may have expired; check the request status.");
      return;
    }
    if (!mountedRef.current) return;
    attemptedRef.current = true;
    sequenceRef.current = 0;
    const socket = new WebSocket(grant.viewer_url);
    socket.binaryType = "blob";
    socketRef.current = socket;
    socket.onopen = () => {
      connectingRef.current = false;
      socket.send(JSON.stringify({ ticket: grant.viewer_ticket }));
      setStatus("Connected. Browser frames and input are not saved.");
    };
    socket.onmessage = (event: MessageEvent<Blob | string>) => {
      if (typeof event.data === "string") return;
      void createImageBitmap(event.data).then((image) => {
        const canvas = canvasRef.current;
        if (canvas && socketRef.current === socket) {
          canvas.width = image.width;
          canvas.height = image.height;
          canvas.getContext("2d")?.drawImage(image, 0, 0);
        }
        image.close();
      });
    };
    socket.onerror = () => setStatus("The protected browser connection failed.");
    socket.onclose = () => {
      if (socketRef.current !== socket) return;
      socketRef.current = null;
      connectingRef.current = false;
      const canvas = canvasRef.current;
      canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
      setStatus("Viewer disconnected. Reconnect while the lease is active, or release control.");
    };
    setStatus("Connecting to the protected browser…");
  };

  const send = (payload: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      sequenceRef.current += 1;
      socket.send(JSON.stringify({ sequence: sequenceRef.current, ...payload }));
    }
  };

  const sendText = (value: string) => {
    if (value) send({ event: "text", text: value });
  };

  return (
    <div className="human-browser-viewer">
      <p role="status">{status}</p>
      {!socketRef.current ? <button type="button" className="secondary-button" onClick={() => void connect()}>{attemptedRef.current ? "Reconnect to protected browser" : "Connect to protected browser"}</button> : null}
      <canvas
        ref={canvasRef}
        aria-label="Live protected browser"
        onPointerDown={(event) => {
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
        onWheel={(event) => {
          event.preventDefault();
          send({ event: "scroll", delta: Math.max(-1000, Math.min(1000, Math.trunc(event.deltaY))) });
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape" && event.shiftKey) {
            event.preventDefault();
            leaveControlRef.current?.focus();
            return;
          }
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
        style={{ display: "block", maxWidth: "100%", height: "auto", touchAction: "none" }}
      />
      <label className="visually-hidden" htmlFor="human-browser-text">Type into the protected browser</label>
      <input
        ref={textInputRef}
        id="human-browser-text"
        type="password"
        autoComplete="off"
        aria-label="Type into the protected browser"
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
          const key = event.key === "Tab" && event.shiftKey ? "Shift+Tab" : event.key;
          if (permittedKeys.has(key)) {
            event.preventDefault();
            send({ event: "key", key });
          }
        }}
      />
      <p className="viewer-keyboard-help">Browser Tab navigation is forwarded to the test page. Press Shift+Escape to leave browser keyboard control.</p>
      <button ref={leaveControlRef} type="button" className="secondary-button" onClick={() => { canvasRef.current?.blur(); textInputRef.current?.blur(); }}>
        Leave browser keyboard control
      </button>
    </div>
  );
}
