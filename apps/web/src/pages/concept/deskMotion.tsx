import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

/* The Briefing Desk's honest motion system (home-motion research §4/§5).
 *
 * Five rules, shared between this module and the stylesheet:
 *  R1 — Nothing animates on arrival: the gate (`armedRef`) stays false
 *       until the first desk content has painted, so first load, tab
 *       return and first data all render statically.
 *  R2 — Only real changes move: components diff against what was last
 *       committed; an identical poll payload changes no state here.
 *       Lengths transition; numbers and words swap discretely at t=0.
 *  R3 — One register: Carbon productive tokens (--dur-*, --ease-*).
 *       Monotonic only — no springs, overshoot or bounce anywhere.
 *  R4 — Exactly one attention event: a new Needs-you item arriving
 *       while the user is present (wired up in the page, not here).
 *  R5 — Reduced motion / hidden document: end states, instantly. Every
 *       choreography below checks `canAnimateDesk` first, and the CSS
 *       zeroes whatever transitions remain under prefers-reduced-motion.
 *
 * CSS transitions only. No animation library, no keyframe loops, and
 * nothing on this page animates infinitely.
 */

export interface DeskMotionState {
  /** False until the first desk content has committed; read during render. */
  armedRef: { current: boolean };
  reduced: boolean;
  suspended: boolean;
}

const staticMotion: DeskMotionState = {
  armedRef: { current: true },
  reduced: false,
  suspended: false,
};

export const DeskMotionContext = createContext<DeskMotionState>(staticMotion);

export function useDeskMotion(): DeskMotionState {
  return useContext(DeskMotionContext);
}

export function canAnimateDesk(motion: DeskMotionState): boolean {
  return (
    motion.armedRef.current &&
    !motion.reduced &&
    !motion.suspended &&
    (typeof document === "undefined" || !document.hidden)
  );
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false,
  );
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(query.matches);
    onChange();
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/** While the document is hidden, changes must apply instantly — nothing
 * may queue up and replay when the tab becomes visible again. */
export function useDocumentHidden(): boolean {
  const [hidden, setHidden] = useState<boolean>(
    () => typeof document !== "undefined" && document.hidden,
  );
  useEffect(() => {
    const onChange = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  return hidden;
}

/* ---------- DeskZone: a section that can appear and leave ----------
 * Used for the masthead and the live strip. Appearing after arrival
 * (a state change while the user is present) fades in at the enter
 * duration; disappearing fades out at the exit duration while the rest
 * of the page recomposes — a fade-through, never a morph. An empty
 * zone renders display:contents so it never becomes a grid item. */

export function DeskZone({ show, children }: { show: boolean; children: ReactNode }) {
  const motion = useDeskMotion();
  const [snapshot, setSnapshot] = useState<ReactNode>(null);
  const [leaving, setLeaving] = useState(false);
  const [appear, setAppear] = useState<"off" | "from" | "to">("off");
  const prevSnapshotRef = useRef<ReactNode>(null);
  const hasSnapshot = snapshot !== null && snapshot !== undefined;

  // While shown, the snapshot tracks the live children; a snapshot that
  // appears from nothing (while armed) earns the enter fade.
  useEffect(() => {
    if (!show) return;
    if (prevSnapshotRef.current == null && canAnimateDesk(motion)) setAppear("from");
    prevSnapshotRef.current = children;
    setSnapshot(children);
    setLeaving(false);
  }, [show, children, motion]);

  // Leaving: keep the last snapshot for one exit fade, then drop it.
  useEffect(() => {
    if (show || !hasSnapshot) return;
    if (!canAnimateDesk(motion)) {
      setSnapshot(null);
      prevSnapshotRef.current = null;
      return;
    }
    setLeaving(true);
    const timer = window.setTimeout(() => {
      setSnapshot(null);
      setLeaving(false);
      prevSnapshotRef.current = null;
    }, 170);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show, hasSnapshot]);

  // Flip the appear from-state to its end state next frame.
  useEffect(() => {
    if (appear !== "from") return;
    let done = false;
    const flip = () => {
      if (!done) {
        done = true;
        setAppear("to");
      }
    };
    const raf = requestAnimationFrame(flip);
    const timer = window.setTimeout(flip, 50);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(timer);
    };
  }, [appear]);

  useEffect(() => {
    if (appear !== "to") return;
    const timer = window.setTimeout(() => setAppear("off"), 300);
    return () => window.clearTimeout(timer);
  }, [appear]);

  if (!hasSnapshot) return <div className="desk-zone-empty" aria-hidden="true" />;
  const className = leaving
    ? "desk-zone-leaving"
    : appear === "from"
      ? "desk-appear"
      : appear === "to"
        ? "desk-appear desk-appear-in"
        : undefined;
  return <div className={className}>{snapshot}</div>;
}

/* ---------- DeskSwap: the masthead's content crossfade ----------
 * When the swap key changes while the user is present (a new verdict,
 * a failed run replacing the hero), the previous content fades out at
 * the exit duration while the new content fades in at the enter
 * duration. The motion is identical for every verdict — differentiation
 * stays word + tint + basis, never movement. On arrival, when reduced,
 * or while hidden, the swap is instant — and a swap only animates when
 * the outgoing content was itself settled (on screen at least 400ms),
 * so load sequencing (runs first, report a beat later) never animates:
 * the placeholder was never a state the user settled into. */

export function DeskSwap({ swapKey, children }: { swapKey: string; children: ReactNode }) {
  const motion = useDeskMotion();
  const [leaving, setLeaving] = useState<ReactNode>(null);
  const [phase, setPhase] = useState<"rest" | "from" | "to">("rest");
  const [cycle, setCycle] = useState(0);
  const keyRef = useRef(swapKey);
  const keySinceRef = useRef(performance.now());
  const prevNodeRef = useRef<ReactNode>(null);

  // Remember the last committed content: it becomes the leaving copy if
  // the key changes on the next render.
  useEffect(() => {
    prevNodeRef.current = children;
  });

  if (keyRef.current !== swapKey) {
    keyRef.current = swapKey;
    const outgoingSettled = performance.now() - keySinceRef.current >= 400;
    keySinceRef.current = performance.now();
    if (outgoingSettled && canAnimateDesk(motion)) {
      setLeaving(prevNodeRef.current);
      setPhase("from");
      setCycle((count) => count + 1);
    } else {
      setLeaving(null);
      setPhase("rest");
    }
  }

  useEffect(() => {
    if (cycle === 0) return;
    let flipped = false;
    const flip = () => {
      if (!flipped) {
        flipped = true;
        setPhase("to");
      }
    };
    const raf = requestAnimationFrame(flip);
    const flipTimer = window.setTimeout(flip, 50);
    const clearLeaving = window.setTimeout(() => setLeaving(null), 180);
    const rest = window.setTimeout(() => setPhase("rest"), 320);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(flipTimer);
      window.clearTimeout(clearLeaving);
      window.clearTimeout(rest);
    };
  }, [cycle]);

  return (
    <div className="desk-swap">
      {leaving !== null && leaving !== undefined ? (
        <div
          className={`desk-swap-leaving${phase === "to" ? " desk-swap-leaving-out" : ""}`}
          aria-hidden="true"
        >
          {leaving}
        </div>
      ) : null}
      <div
        className={
          phase === "from"
            ? "desk-swap-enter"
            : phase === "to"
              ? "desk-swap-enter desk-swap-enter-in"
              : undefined
        }
      >
        {children}
      </div>
    </div>
  );
}

/* ---------- DeskScaleFill: the outcome bar's length transition ----------
 * The segment's flex box snaps to its new size at t=0 (labels and counts
 * with it — they are siblings of this span, never inside the scaled
 * element). The fill alone starts scaled by old/new, so it visually
 * still shows the previous length, then transitions the transform to
 * scaleX(1) over the bar duration. At rest it is always exactly the
 * segment's true length; mid-flight it lies on the path between two
 * real lengths and never overshoots. */

export function DeskScaleFill({ frac, className }: { frac: number; className?: string }) {
  const motion = useDeskMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const prevRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    const element = ref.current;
    const previous = prevRef.current;
    prevRef.current = frac;
    if (!element || previous === null || previous === frac || frac <= 0) return;
    if (!canAnimateDesk(motion)) return;
    element.style.transition = "none";
    element.style.transform = `scaleX(${previous / frac})`;
    void element.offsetWidth;
    element.style.transition = "transform var(--dur-bar) var(--ease-change)";
    element.style.transform = "scaleX(1)";
    const timer = window.setTimeout(() => {
      if (ref.current) ref.current.style.transition = "";
    }, 340);
    return () => window.clearTimeout(timer);
  }, [frac, motion]);

  return <span ref={ref} className={className} aria-hidden="true" />;
}

/* ---------- useFlip: survivor translation for keyed lists ----------
 * When items enter or leave a keyed list, the survivors' boxes jump.
 * This measures each [data-flip-key] child's rect against the previous
 * commit and, if it moved, plays the delta back as a transform over
 * the move duration — FLIP, transform only. New items have no previous
 * rect and never flip; identical data produces an unchanged dep string
 * and the effect never runs. An optional gate (a deadline timestamp)
 * restricts animation to a window the caller opened — the archive uses
 * it so only user-driven filter changes flip rows, never poll-driven
 * ones. */

export function useFlip(
  containerRef: RefObject<HTMLElement | null>,
  dep: string,
  gateRef?: { current: number },
) {
  const motion = useDeskMotion();
  const rectsRef = useRef(new Map<string, { left: number; top: number }>());

  useLayoutEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    const elements = Array.from(root.querySelectorAll<HTMLElement>("[data-flip-key]"));
    const next = new Map<string, { left: number; top: number }>();
    const animate =
      canAnimateDesk(motion) && (gateRef === undefined || performance.now() <= gateRef.current);
    for (const element of elements) {
      const key = element.getAttribute("data-flip-key") ?? "";
      const rect = element.getBoundingClientRect();
      next.set(key, { left: rect.left, top: rect.top });
      const previous = rectsRef.current.get(key);
      if (animate && previous) {
        const dx = previous.left - rect.left;
        const dy = previous.top - rect.top;
        if (dx !== 0 || dy !== 0) {
          element.style.transition = "none";
          element.style.transform = `translate(${dx}px, ${dy}px)`;
          requestAnimationFrame(() => {
            element.style.transition = "transform var(--dur-move) var(--ease-change)";
            element.style.transform = "";
          });
        }
      }
    }
    rectsRef.current = next;
  }, [dep, motion, containerRef]);
}

/* ---------- useDeskEnterFlip: one-shot entrance flips ----------
 * Elements rendered with [data-desk-enter] start in their from-state
 * (see .desk-enter). After the commit that introduces them, this flips
 * .desk-entered onto them next frame so the CSS transition runs to the
 * end state. Elements rendered while motion cannot animate never carry
 * the attribute in the first place. */

export function useDeskEnterFlip(rootRef: RefObject<HTMLElement | null>, dep: string) {
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const elements = Array.from(
      root.querySelectorAll<HTMLElement>("[data-desk-enter]:not(.desk-entered)"),
    );
    if (!elements.length) return;
    let done = false;
    const flip = () => {
      if (done) return;
      done = true;
      for (const element of elements) element.classList.add("desk-entered");
    };
    const raf = requestAnimationFrame(flip);
    const timer = window.setTimeout(flip, 60);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(timer);
    };
  }, [dep, rootRef]);
}
