import { useEffect, useRef, useState } from "react";
import type { LiveBrowser } from "../../lib/api";

const tabIsHidden = () => document.visibilityState === "hidden";

export interface LiveBrowserStream {
  url: string;
  ticket: string;
}

/** One surface, two modes. The same socket stream watches the agent work
 * and, when control passes to the human, keeps streaming under the control
 * chrome — the stream does not restart. The observer never sends input:
 * the only client message is the {ticket} handshake the viewer gateway
 * requires on connect (the HumanBrowserViewer protocol). Frames arrive as
 * binary JPEG blobs; control JSON (accepted_sequence, network_diagnostics)
 * is ignored because an observer sends nothing that can be acked. */
export function LiveBrowserObserver({ runId, browser, identity, permitted, stream, onReconnect, onReturnControl, onTakeControl }: {
  runId: string; browser: LiveBrowser | null; identity: string; permitted: boolean;
  stream?: LiveBrowserStream | null;
  onReconnect?: () => Promise<LiveBrowserStream>;
  onReturnControl?: () => void;
  onTakeControl?: () => void;
}) {
  const [grant, setGrant] = useState<LiveBrowserStream | null>(stream ?? null);
  const [frame, setFrame] = useState<{ url: string; identity: string; deliveredAt: Date } | null>(null);
  const [message, setMessage] = useState("Waiting for the first live frame.");
  const [retry, setRetry] = useState(0);
  const urlRef = useRef<string | null>(null);
  const controllingRef = useRef(false);
  const controlling = browser?.control_state === "human";
  controllingRef.current = controlling;
  const parked = browser?.control_state === "human_pending";
  const allowed = permitted && browser?.viewer_state === "available" && ["agent", "human_pending", "human"].includes(browser.control_state);
  const streamIdentity = `${identity}:${runId}:${browser?.browser_session_id}:${browser?.generation}:${allowed}:${grant?.url ?? ""}`;
  const shownFrame = frame?.identity === streamIdentity && allowed ? frame : null;

  useEffect(() => {
    setGrant(stream ?? null);
  }, [stream?.url, stream?.ticket]);

  const reconnect = async () => {
    if (onReconnect) {
      try {
        setGrant(await onReconnect());
      } catch {
        // Keep the current grant; the retry below re-enters the effect and
        // the surface reports the stream error state if it still fails.
      }
    }
    setRetry((value) => value + 1);
  };

  useEffect(() => {
    let active = true;
    let newestFrame = 0;
    const clear = () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
      setFrame(null);
    };
    clear();
    if (!allowed || !browser || !grant) return;
    setMessage("Waiting for the first live frame.");
    let socket: WebSocket;
    try {
      socket = new WebSocket(grant.url);
    } catch {
      setMessage("Browser frame temporarily unavailable; the test can continue.");
      return;
    }
    socket.binaryType = "blob";
    socket.onopen = () => {
      socket.send(JSON.stringify({ ticket: grant.ticket }));
    };
    socket.onmessage = (event: MessageEvent<Blob | string>) => {
      if (!active || typeof event.data === "string") return;
      const received = ++newestFrame;
      const candidate = URL.createObjectURL(event.data);
      const image = new Image();
      image.src = candidate;
      void image.decode().then(() => {
        if (!active || received !== newestFrame || tabIsHidden()) {
          URL.revokeObjectURL(candidate);
          return;
        }
        const previous = urlRef.current;
        urlRef.current = candidate;
        if (previous) URL.revokeObjectURL(previous);
        setFrame({ url: candidate, identity: streamIdentity, deliveredAt: new Date() });
        setMessage(controllingRef.current ? "You are controlling this browser — the test is paused" : "Read-only live view. Browser input is disabled.");
      }).catch(() => {
        URL.revokeObjectURL(candidate);
      });
    };
    socket.onerror = () => {
      if (active) setMessage("Browser frame temporarily unavailable; the test can continue.");
    };
    const visibility = () => {
      if (tabIsHidden()) {
        socket.close();
        clear();
        setMessage("Live view paused while this tab is hidden.");
      } else {
        void reconnect();
      }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => {
      active = false;
      document.removeEventListener("visibilitychange", visibility);
      socket.close();
      clear();
    };
  }, [streamIdentity, retry]);

  const caption = controlling ? "You are controlling this browser — the test is paused" : "Read-only live view. Browser input is disabled.";
  return <section className="live-browser-surface" aria-label="Read-only test browser">
    {shownFrame ? <img src={shownFrame.url} alt="Current view of the selected test browser" style={parked ? { opacity: 0.45 } : undefined} onError={() => { setFrame(null); if (urlRef.current) URL.revokeObjectURL(urlRef.current); urlRef.current = null; setMessage("Browser frame temporarily unavailable; the test can continue."); }} /> : <div className="live-browser-empty">
      <p>{!permitted ? "Live browser observation requires an owner or administrator role." : !browser ? "No test browser is currently open. Recorded activity remains available below." : !allowed ? "Read-only observation is hidden during protected human interaction." : message}</p>
    </div>}
    {parked && allowed ? <div className="live-browser-empty">
      <p>The tester needs you to log in</p>
      {onTakeControl ? <button type="button" className="primary-button" onClick={onTakeControl}>Take control and log in</button> : <a className="primary-button" href="#human-action-heading">Take control and log in</a>}
    </div> : null}
    <div className="live-browser-caption"><p role="status">{shownFrame ? caption : allowed ? message : "No live pixels are displayed."}</p>
      {controlling && onReturnControl ? <button type="button" className="text-link" onClick={onReturnControl}>Return control</button> : null}
      {shownFrame ? <time dateTime={shownFrame.deliveredAt.toISOString()}>Frame delivered {shownFrame.deliveredAt.toLocaleTimeString()}</time> : allowed ? <button type="button" className="text-link" onClick={() => void reconnect()}>Retry</button> : null}
    </div>
  </section>;
}
