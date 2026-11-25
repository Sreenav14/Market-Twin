import { useEffect, useRef, useState } from "react";
import type { LiveBrowser } from "../../lib/api";

const tabIsHidden = () => document.visibilityState === "hidden";

export interface LiveBrowserStream {
  url: string;
  ticket: string;
}

/** Bind the viewer socket to the page host so the session cookie is sent.
 * Grant URLs are often `ws://localhost:...` while the UI may be opened on
 * `127.0.0.1`; those hosts do not share cookies. */
function sameOriginViewerUrl(value: string): string {
  const target = new URL(value);
  if (
    target.pathname !== "/api/v1/hitl-viewer" || target.search || target.hash
    || target.username || target.password
  ) {
    throw new Error("Untrusted browser viewer address.");
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/v1/hitl-viewer`;
}

/** Gateway close dispositions (doc 11 section 2.3): the observer loop exits
 * with a reason code carried in the WebSocket close reason. 1008 with
 * authority_revoked means the viewing grant itself has ended — reconnecting
 * would only be refused again, so the user reopens Watch. Every other
 * classified exit (lease_expired, owner_gone, stream_error) is transient:
 * a fresh observer grant is the designed recovery, so the interrupted
 * message shows and the existing backoff reconnect runs. Unclassified
 * closes keep the incumbent behaviour (empty message -> the caller's own
 * wording stands). Doc 24 section 5.2 extends this table; it does not
 * replace it. */
export const closeDisposition = (code: number, reason: string, streamed = false): { message: string; reconnect: boolean } => {
  if (code === 1008 && reason === "authority_revoked") {
    return { message: "This viewing session has ended", reconnect: false };
  }
  // Connect-path refusal classes (doc 24 section 5.3), authenticated
  // post-ticket path only: each names its own recovery, and none is
  // helped by reconnecting with the same grant.
  if (code === 1008 && reason === "ticket_consumed") {
    return { message: "This viewing link was already used — reopen Watch to get a fresh one", reconnect: false };
  }
  if (code === 1008 && reason === "lease_expired") {
    // Mid-stream expiry is transient (doc 11 section 2.3): a fresh
    // grant is the designed recovery. Only a connect-path refusal
    // (nothing streamed yet) takes the section 5.2 terminal copy.
    if (streamed) return { message: "Live view interrupted — reconnecting", reconnect: true };
    return { message: "This viewing session has ended — reopen Watch", reconnect: false };
  }
  if (code === 1008 && reason === "owner_gone") {
    if (streamed) return { message: "Live view interrupted — reconnecting", reconnect: true };
    return { message: "The run's browser has closed", reconnect: false };
  }
  if (code === 1008 && reason === "authority_unmet") {
    return { message: "Viewing isn't available for this run right now", reconnect: false };
  }
  if (code === 1008 || code === 1011) {
    return { message: "Live view interrupted — reconnecting", reconnect: true };
  }
  return { message: "", reconnect: true };
};

/** One surface, two modes. The same socket stream watches the agent work
 * and, when control passes to the human, keeps streaming under the control
 * chrome — the stream does not restart. The observer never sends input:
 * the only client message is the {ticket} handshake the viewer gateway
 * requires on connect (the HumanBrowserViewer protocol). Frames arrive as
 * binary JPEG blobs; agent_pointer JSON updates the overlay independently.
 * Other control messages are ignored because an observer sends no input. */
export function LiveBrowserObserver({ runId, browser, identity, permitted, stream, onReconnect, onReturnControl, onTakeControl }: {
  runId: string; browser: LiveBrowser | null; identity: string; permitted: boolean;
  stream?: LiveBrowserStream | null;
  onReconnect?: () => Promise<LiveBrowserStream>;
  onReturnControl?: () => void;
  onTakeControl?: () => void;
}) {
  const [grant, setGrant] = useState<LiveBrowserStream | null>(stream ?? null);
  const [frame, setFrame] = useState<{ url: string; identity: string; deliveredAt: Date; width: number; height: number } | null>(null);
  const [message, setMessage] = useState("Waiting for the first live frame.");
  const [retry, setRetry] = useState(0);
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);
  const urlRef = useRef<string | null>(null);
  const controllingRef = useRef(false);
  const controlling = browser?.control_state === "human";
  controllingRef.current = controlling;
  const parked = browser?.control_state === "human_pending";
  const allowed = permitted && browser?.viewer_state === "available" && ["agent", "human_pending", "human"].includes(browser.control_state);
  const unavailableReason = browser?.control_state === "human"
    ? "Read-only observation is hidden during protected human interaction."
    : browser?.control_state === "verifying"
      ? "The browser handoff is being verified. Live observation will return when agent control resumes."
      : browser?.control_state === "human_pending"
        ? "Browser handoff is being prepared."
        : "Live observation is temporarily unavailable for this execution. Check the recorded activity and runner status.";
  const streamIdentity = `${identity}:${runId}:${browser?.browser_session_id}:${browser?.execution_id}:${browser?.journey_id}:${browser?.generation}:${allowed}`;
  const canAttach = Boolean(grant || onReconnect);
  const shownFrame = frame?.identity === streamIdentity && allowed ? frame : null;

  useEffect(() => {
    setGrant(stream ?? null);
  }, [stream?.url, stream?.ticket]);

  const reconnect = async () => {
    setRetry((value) => value + 1);
  };

  useEffect(() => {
    let active = true;
    let newestFrame = 0;
    let decoding = false;
    let pendingFrame: Blob | null = null;
    let socket: WebSocket | undefined;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let frameTimer: ReturnType<typeof setTimeout> | undefined;
    let reconnectAttempts = 0;
    let decodeNext = () => {};
    const clear = () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
      setFrame(null);
      setPointer(null);
    };
    clear();
    if (!allowed || !browser || !canAttach) return;
    setMessage("Waiting for the first live frame.");
    const unavailable = () => {
      if (active) setMessage(newestFrame > 0
        ? "The viewer lost its connection. Showing the last received frame while reconnecting."
        : "The viewer could not connect.");
    };
    const scheduleReconnect = () => {
      if (!active || tabIsHidden() || reconnectTimer) return;
      clearTimeout(frameTimer);
      unavailable();
      reconnectTimer = setTimeout(() => {
        reconnectTimer = undefined;
        if (active && !tabIsHidden()) void connect();
      }, Math.min(1000 * 2 ** reconnectAttempts++, 10000));
    };
    const watchConnection = (currentSocket: WebSocket, milliseconds: number) => {
      clearTimeout(frameTimer);
      frameTimer = setTimeout(() => {
        if (!active || socket !== currentSocket || tabIsHidden()) return;
        currentSocket.close();
        scheduleReconnect();
      }, milliseconds);
    };
    const connect = async () => {
      // Observer tickets are single-use; refresh on every attach so remounts
      // and retries do not reuse a spent ticket.
      let activeGrant = grant;
      if (onReconnect) {
        try {
          activeGrant = await onReconnect();
          if (!active) return;
        } catch {
          scheduleReconnect();
          return;
        }
      }
      if (!activeGrant) return;
      try {
        socket = new WebSocket(sameOriginViewerUrl(activeGrant.url));
      } catch {
        scheduleReconnect();
        return;
      }
      const currentSocket = socket;
      let decodedCurrentFrame = false;
      watchConnection(currentSocket, 10000);
      socket.binaryType = "blob";
      socket.onopen = () => {
        socket?.send(JSON.stringify({ ticket: activeGrant.ticket }));
      };
      decodeNext = () => {
        if (!active || decoding || !pendingFrame) return;
        decoding = true;
        const candidate = URL.createObjectURL(pendingFrame);
        pendingFrame = null;
        const image = new Image();
        image.src = candidate;
        void image.decode().then(() => {
          if (!active || socket !== currentSocket || tabIsHidden()) {
            URL.revokeObjectURL(candidate);
            return;
          }
          const previous = urlRef.current;
          urlRef.current = candidate;
          if (previous) URL.revokeObjectURL(previous);
          setFrame({ url: candidate, identity: streamIdentity, deliveredAt: new Date(),
            width: image.naturalWidth || image.width || 0,
            height: image.naturalHeight || image.height || 0 });
          setMessage(controllingRef.current ? "You are controlling this browser — the test is paused" : "Read-only live view. Browser input is disabled.");
          reconnectAttempts = 0;
          decodedCurrentFrame = true;
          watchConnection(currentSocket, 15000);
        }).catch(() => {
          URL.revokeObjectURL(candidate);
        }).finally(() => {
          decoding = false;
          decodeNext();
        });
      };
      socket.onmessage = (event: MessageEvent<Blob | string>) => {
        if (!active || socket !== currentSocket || tabIsHidden()) return;
        if (decodedCurrentFrame) watchConnection(currentSocket, 15000);
        if (typeof event.data === "string") {
          try {
            const update = JSON.parse(event.data);
            if (update.type === "agent_pointer") {
              const point = update.pointer;
              setPointer(point && Number.isFinite(point.x) && Number.isFinite(point.y)
                && point.x >= 0 && point.x < 1 && point.y >= 0 && point.y < 1
                ? { x: point.x, y: point.y } : null);
            }
          } catch { /* Ignore malformed control messages. */ }
          return;
        }
        newestFrame += 1;
        pendingFrame = event.data;
        decodeNext();
      };
      socket.onerror = () => {
        if (socket !== currentSocket) return;
        currentSocket.close();
        scheduleReconnect();
      };
      socket.onclose = (event: CloseEvent) => {
        if (socket !== currentSocket) return;
        const disposition = closeDisposition(event.code, event.reason, decodedCurrentFrame);
        if (!disposition.reconnect) {
          // The viewing session has ended: disarm the frame watchdog and
          // any pending reconnect so nothing revives a revoked stream.
          clearTimeout(frameTimer);
          clearTimeout(reconnectTimer);
          reconnectTimer = undefined;
          if (active) setMessage(disposition.message);
          return;
        }
        scheduleReconnect();
        if (disposition.message && active) setMessage(disposition.message);
      };
    };
    void connect();
    const visibility = () => {
      if (tabIsHidden()) {
        socket?.close();
        clear();
        setMessage("Live view paused while this tab is hidden.");
      } else {
        void reconnect();
      }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => {
      active = false;
      pendingFrame = null;
      clearTimeout(reconnectTimer);
      clearTimeout(frameTimer);
      document.removeEventListener("visibilitychange", visibility);
      socket?.close();
      clear();
    };
  }, [streamIdentity, retry, canAttach]);

  const caption = controlling ? "You are controlling this browser — the test is paused" : message;
  return <section className="live-browser-surface" aria-label="Read-only test browser">
    {shownFrame ? <div style={{ position: "relative", width: "100%", margin: "0 auto",
      maxWidth: shownFrame.width > 0 && shownFrame.height > 0
        ? `min(${shownFrame.width}px, ${70 * shownFrame.width / shownFrame.height}vh)` : "100%" }}>
      <img src={shownFrame.url} alt="Current view of the selected test browser" style={parked ? { opacity: 0.45 } : undefined} onError={() => { setFrame(null); if (urlRef.current) URL.revokeObjectURL(urlRef.current); urlRef.current = null; setMessage("The viewer could not display the browser frame."); }} />
      {pointer && !controlling && !parked ? <svg aria-label="Agent action target" width="24" height="30" viewBox="0 0 24 30" style={{ position: "absolute", zIndex: 2, left: `${pointer.x * 100}%`, top: `${pointer.y * 100}%`, pointerEvents: "none", transition: "left 120ms linear, top 120ms linear", overflow: "visible" }}>
        <path d="M1 1 L8 27 L13 19 L23 20 Z" fill="#e11d48" stroke="white" strokeWidth="2" />
      </svg> : null}
    </div> : <div className="live-browser-empty">
      {!allowed ? <p>{!permitted ? "Live browser observation requires an owner or administrator role." : !browser ? "No test browser is currently open. Recorded activity remains available below." : unavailableReason}</p> : null}
    </div>}
    {parked && allowed ? <div className="live-browser-empty">
      <p>The tester needs you to log in</p>
      {onTakeControl ? <button type="button" className="primary-button" onClick={onTakeControl}>Take control and log in</button> : <a className="primary-button" href="#human-action-heading">Take control and log in</a>}
    </div> : null}
    <div className="live-browser-caption"><p role="status">{shownFrame ? caption : allowed ? message : "No live pixels are displayed."}</p>
      {shownFrame && shownFrame.width > 0 ? <span>{shownFrame.width} × {shownFrame.height} browser view</span> : null}
      {controlling && onReturnControl ? <button type="button" className="text-link" onClick={onReturnControl}>Return control</button> : null}
      {shownFrame ? <time dateTime={shownFrame.deliveredAt.toISOString()}>Frame delivered {shownFrame.deliveredAt.toLocaleTimeString()}</time> : null}
      {allowed && canAttach && (!shownFrame || message.startsWith("The viewer lost")) ? <button type="button" className="text-link" onClick={() => void reconnect()}>Retry viewing</button> : null}
    </div>
  </section>;
}
