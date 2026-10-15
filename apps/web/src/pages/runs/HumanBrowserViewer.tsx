import { useEffect, useRef, useState } from "react";

interface HumanBrowserViewerProps {
  url: string;
  ticket: string;
}

const permittedKeys = new Set([
  "Tab", "Shift+Tab", "Enter", "Backspace", "Delete", "Escape", "ArrowUp", "ArrowDown",
  "ArrowLeft", "ArrowRight", "Home", "End",
]);

/** Volatile, ticket-authenticated view of the worker-owned browser. */
export function HumanBrowserViewer({ url, ticket }: HumanBrowserViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const sequenceRef = useRef(0);
  const [status, setStatus] = useState("Connecting to the protected browser…");

  useEffect(() => {
    return () => {
      const socket = socketRef.current;
      socketRef.current = null;
      socket?.close(1000, "operator left viewer");
    };
  }, []);

  const connect = () => {
    if (socketRef.current) return;
    const socket = new WebSocket(url);
    socket.binaryType = "blob";
    socketRef.current = socket;
    socket.onopen = () => {
      socket.send(JSON.stringify({ ticket }));
      setStatus("Connected. Browser frames and input are not saved.");
    };
    socket.onmessage = (event: MessageEvent<Blob | string>) => {
      if (typeof event.data === "string") return;
      void createImageBitmap(event.data).then((image) => {
        const canvas = canvasRef.current;
        if (canvas) {
          canvas.width = image.width;
          canvas.height = image.height;
          canvas.getContext("2d")?.drawImage(image, 0, 0);
        }
        image.close();
      });
    };
    socket.onerror = () => setStatus("The protected browser connection failed.");
    socket.onclose = () => setStatus("Browser control ended.");
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
      {!socketRef.current ? <button type="button" className="secondary-button" onClick={connect}>Connect to protected browser</button> : null}
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
        id="human-browser-text"
        type="password"
        autoComplete="off"
        aria-label="Type into the protected browser"
        onChange={(event) => {
          sendText(event.currentTarget.value);
          event.currentTarget.value = "";
        }}
        onKeyDown={(event) => {
          const key = event.key === "Tab" && event.shiftKey ? "Shift+Tab" : event.key;
          if (permittedKeys.has(key)) {
            event.preventDefault();
            send({ event: "key", key });
          }
        }}
      />
    </div>
  );
}
