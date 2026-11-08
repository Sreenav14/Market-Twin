import { Button } from "./button";

/**
 * Pagination & load-more — ONE recipe (Phase 2b, Spec 1 §6).
 * Tables/records use numbered Pagination (infinite scroll is banned
 * there); secondary append-friendly lists use LoadMore with ONE label
 * shape — "Load more {noun}" — and the count stated in words beside it.
 * The three historical labels ("Load more steps" / "Load more recorded
 * steps" / "Load older activity") are retired.
 */
export function LoadMore({
  noun,
  loaded,
  total,
  loading,
  onLoad,
}: {
  noun: string;
  loaded: number;
  total?: number;
  loading: boolean;
  onLoad: () => void;
}) {
  return (
    <div className="load-more">
      <Button variant="secondary" disabled={loading} onClick={onLoad}>
        {loading ? `Loading ${noun}…` : `Load more ${noun}`}
      </Button>
      <p className="load-more-count" role="status">
        {total !== undefined
          ? `${loaded} of ${total} ${noun} loaded`
          : `${loaded} ${noun} loaded`}
      </p>
    </div>
  );
}

function pageSlots(page: number, totalPages: number): (number | "…")[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const keep = new Set([1, totalPages, page - 1, page, page + 1]);
  const out: (number | "…")[] = [];
  let gap = false;
  for (let i = 1; i <= totalPages; i++) {
    if (keep.has(i)) {
      out.push(i);
      gap = false;
    } else if (!gap) {
      out.push("…");
      gap = true;
    }
  }
  return out;
}

export function Pagination({
  page,
  totalPages,
  onPage,
  label = "Pagination",
}: {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
  label?: string;
}) {
  if (totalPages <= 1) return null;
  return (
    <nav aria-label={label} className="pagination">
      <button
        type="button"
        className="pagination-step"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        aria-label="Previous page"
      >
        ‹ Previous
      </button>
      {pageSlots(page, totalPages).map((slot, i) =>
        slot === "…" ? (
          <span key={`gap-${i}`} className="pagination-gap" aria-hidden="true">
            …
          </span>
        ) : slot === page ? (
          <span key={slot} className="pagination-page pagination-current" aria-current="page">
            {slot}
          </span>
        ) : (
          <button
            key={slot}
            type="button"
            className="pagination-page"
            onClick={() => onPage(slot)}
            aria-label={`Page ${slot}`}
          >
            {slot}
          </button>
        ),
      )}
      <button
        type="button"
        className="pagination-step"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
        aria-label="Next page"
      >
        Next ›
      </button>
    </nav>
  );
}
