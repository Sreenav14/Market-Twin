import { useEffect, useRef, useState } from "react";
import { ApiError, api, type LiveBrowser } from "../../lib/api";

const tabIsHidden = () => document.visibilityState === "hidden";

/** Passive transport only: no lease, WebSocket, key, click or pointer input path. */
export function LiveBrowserObserver({ runId, browser, identity, permitted }: {
  runId: string; browser: LiveBrowser | null; identity: string; permitted: boolean;
}) {
  const [frame, setFrame] = useState<{ url: string; identity: string; deliveredAt: Date } | null>(null);
  const [message, setMessage] = useState("Waiting for the first live frame.");
  const [retry, setRetry] = useState(0);
  const urlRef = useRef<string | null>(null);
  const allowed = permitted && browser?.viewer_state === "available" && ["agent", "human_pending"].includes(browser.control_state);
  const frameIdentity = `${identity}:${runId}:${browser?.browser_session_id}:${browser?.generation}:${browser?.control_state}:${allowed}`;
  const shownFrame = frame?.identity === frameIdentity && allowed ? frame : null;

  useEffect(() => {
    let active = true;
    let fetching = false;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let requestTimer: ReturnType<typeof setTimeout> | undefined;
    let pendingUrl: string | null = null;
    let controller: AbortController | null = null;
    const clear = () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      if (pendingUrl) URL.revokeObjectURL(pendingUrl);
      pendingUrl = null;
      urlRef.current = null;
      setFrame(null);
    };
    clear();
    if (!allowed || !browser) return;
    const poll = async () => {
      if (!active || fetching || stopped || tabIsHidden()) return;
      fetching = true;
      controller = new AbortController();
      const current = controller;
      requestTimer = setTimeout(() => {
        current.abort();
        if (active) { clear(); setMessage("The live frame timed out; the test can continue."); }
      }, 5000);
      let candidate: string | null = null;
      try {
        const blob = await api.getLiveBrowserFrame(runId, browser, current.signal);
        if (!active || current.signal.aborted) return;
        candidate = URL.createObjectURL(blob);
        pendingUrl = candidate;
        const image = new Image();
        image.src = candidate;
        await image.decode();
        if (!active || current.signal.aborted || tabIsHidden()) return;
        const previous = urlRef.current;
        urlRef.current = candidate;
        pendingUrl = null;
        candidate = null;
        if (previous) URL.revokeObjectURL(previous);
        setFrame({ url: urlRef.current, identity: frameIdentity, deliveredAt: new Date() });
        setMessage("Read-only live view. Browser input is disabled.");
      } catch (error) {
        if (!active || current.signal.aborted) return;
        clear();
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          stopped = true;
          setMessage("Live browser access is unavailable. Check your workspace permissions before retrying.");
        } else if (error instanceof ApiError && error.status === 409) {
          stopped = true;
          setMessage("This browser changed or is protected. Waiting for updated execution state.");
        } else {
          setMessage("Browser frame temporarily unavailable; the test can continue. Retry the live view.");
        }
      } finally {
        if (requestTimer) clearTimeout(requestTimer);
        if (candidate) URL.revokeObjectURL(candidate);
        fetching = false;
        if (active && !stopped && !tabIsHidden()) timer = setTimeout(() => void poll(), 1000);
      }
    };
    const visibility = () => {
      if (timer) clearTimeout(timer);
      if (tabIsHidden()) {
        controller?.abort(); clear(); setMessage("Live view paused while this tab is hidden.");
      } else void poll();
    };
    setMessage("Waiting for the first live frame.");
    document.addEventListener("visibilitychange", visibility);
    void poll();
    return () => {
      active = false; controller?.abort();
      if (timer) clearTimeout(timer);
      if (requestTimer) clearTimeout(requestTimer);
      document.removeEventListener("visibilitychange", visibility);
      clear();
    };
  }, [frameIdentity, retry]);

  return <section className="live-browser-surface" aria-label="Read-only test browser">
    {shownFrame ? <img src={shownFrame.url} alt="Current read-only view of the selected test browser" onError={() => { setFrame(null); if (urlRef.current) URL.revokeObjectURL(urlRef.current); urlRef.current = null; setMessage("The browser frame could not be displayed. Retry the live view."); }} /> : <div className="live-browser-empty">
      <p>{!permitted ? "Live browser observation requires an owner or administrator role." : !browser ? "No test browser is currently open. Recorded activity remains available below." : !allowed ? "Read-only observation is hidden during protected human interaction and safe-continuation checks." : message}</p>
    </div>}
    <div className="live-browser-caption"><p role="status">{shownFrame ? message : allowed ? message : "No live pixels are displayed."}</p>
      {shownFrame ? <time dateTime={shownFrame.deliveredAt.toISOString()}>Frame delivered {shownFrame.deliveredAt.toLocaleTimeString()}</time> : allowed ? <button type="button" className="text-link" onClick={() => setRetry((value) => value + 1)}>Retry live view</button> : null}
    </div>
  </section>;
}
