import { useDeferredValue } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { Search, SlidersHorizontal } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { EmptyState } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { findingClassification, isConfirmedFinding, severityOrder, sortFindings } from "../../lib/results";
import { StatusBadge } from "../../components/ui/StatusBadge";

export function RunFindingsPage() {
  const { run, results } = useOutletContext<RunContext>();
  const [params, setParams] = useSearchParams();
  const search = params.get("q") || "";
  const deferredSearch = useDeferredValue(search);
  const severity = params.get("severity") || "all";
  const category = params.get("category") || "all";
  const sort = params.get("sort") || "severity";
  const findings = results.status === "ready" ? results.data.findings : [];
  const selectedId = params.get("selected") || "";
  const categories = [
    ...new Set(findings.map((finding) => finding.category)),
  ].sort();
  function setFilter(key: string, value: string) {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (!value || value === "all") next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }
  const filtered = sortFindings(
    findings.filter(
      (finding) =>
        (severity === "all" || finding.severity === severity) &&
        (category === "all" || finding.category === category) &&
        `${finding.title} ${finding.summary} ${finding.category}`
          .toLowerCase()
          .includes(deferredSearch.toLowerCase()),
    ),
    sort,
  );
  const selected = filtered.find((finding) => finding.id === selectedId) ?? filtered[0];
  function selectFinding(id: string) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set("selected", id);
      return next;
    }, { replace: true });
  }
  return (
    <ResultsBoundary>
      <section aria-labelledby="findings-heading">
        <div className="section-heading">
          <div>
            <h2 id="findings-heading">Findings</h2>
            <p className="muted">
              Prioritize what matters, then inspect the references behind it.
            </p>
          </div>
          <span className="muted">{findings.filter(isConfirmedFinding).length} confirmed · {findings.length} total records</span>
        </div>
        {findings.length > 0 ? (
          <>
            <div className="filter-bar">
              <div className="search-field">
                <Search size={17} aria-hidden="true" />
                <label className="visually-hidden" htmlFor="finding-search">
                  Search findings
                </label>
                <input
                  id="finding-search"
                  value={search}
                  onChange={(event) => setFilter("q", event.target.value)}
                  placeholder="Search findings…"
                  autoComplete="off"
                />
              </div>
              <label className="filter-select">
                <SlidersHorizontal size={15} aria-hidden="true" />
                <span className="visually-hidden">Severity</span>
                <select
                  aria-label="Severity"
                  value={severity}
                  onChange={(event) =>
                    setFilter("severity", event.target.value)
                  }
                >
                  <option value="all">All severities</option>
                  {severityOrder.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label className="filter-select">
                <span className="visually-hidden">Category</span>
                <select
                  aria-label="Category"
                  value={category}
                  onChange={(event) =>
                    setFilter("category", event.target.value)
                  }
                >
                  <option value="all">All categories</option>
                  {categories.map((value) => (
                    <option key={value} value={value}>
                      {value.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label className="filter-select">
                <span className="visually-hidden">Sort findings</span>
                <select
                  aria-label="Sort findings"
                  value={sort}
                  onChange={(event) => setFilter("sort", event.target.value)}
                >
                  <option value="severity">Highest severity</option>
                  <option value="journeys">Most affected journeys</option>
                </select>
              </label>
            </div>
            <p className="filter-count" role="status">
              {filtered.length} of {findings.length} findings
            </p>
            {filtered.length ? (
              <>
                <div className="findings-workbench">
                <div className="findings-groups">
                {([
                  ["Confirmed issues", "Visually verified issue"],
                  ["Needs Verification", "Needs Verification"],
                  ["Test execution issues", "Test execution issue"],
                ] as const).map(([heading, classification]) => {
                  const items = filtered.filter((finding) => findingClassification(finding) === classification);
                  return items.length ? (
                    <section key={heading} aria-label={heading}>
                      <h3>{heading}</h3>
                      {heading === "Needs Verification" ? <p className="muted">These observations require relevant browser evidence. Agreement between synthetic personas is not independent proof.</p> : null}
                      <ul className="finding-list findings-list">
                        {items.map((finding) => <li className="finding-item" key={finding.id}>
                          <button type="button" className="finding-select" aria-pressed={selected?.id === finding.id} onClick={() => selectFinding(finding.id)}>
                            <StatusBadge status={finding.severity} />
                            <span className="category-label">{findingClassification(finding)} · {finding.category.replaceAll("_", " ")}</span>
                            <strong>{finding.title}</strong><span>{finding.summary}</span>
                            <small>{finding.evidence.step_ids.length} steps · {finding.evidence.artifact_ids.length} artifacts</small>
                          </button>
                        </li>)}
                      </ul>
                    </section>
                  ) : null;
                })}
                </div>
                {selected ? <aside className="finding-inspector" aria-labelledby="finding-inspector-title" aria-live="polite">
                  <div className="finding-title-meta"><StatusBadge status={selected.severity} /><span className="category-label">{findingClassification(selected)} · {selected.category.replaceAll("_", " ")}</span></div>
                  <h3 id="finding-inspector-title">{selected.title}</h3><p>{selected.summary}</p>
                  <p><strong>Recommendation</strong><br />{selected.recommendation || "No recommendation was included."}</p>
                  <p className="muted">{selected.evidence.step_ids.length} cited steps · {selected.evidence.artifact_ids.length} artifacts · {selected.journey_ids.length} affected journeys</p>
                  {selected.evidence.step_ids.length ? <p className="muted">Cited step IDs: {selected.evidence.step_ids.slice(0, 2).join(", ")}{selected.evidence.step_ids.length > 2 ? " …" : ""}. Journey links provide the saved step context.</p> : null}
                  {selected.journey_ids.slice(0, 2).map((journeyId) => <Link className="text-link" key={journeyId} to={`/runs/${run.id}/journeys/${journeyId}`}>Open affected journey</Link>)}
                  {selected.evidence.artifact_ids.slice(0, 2).map((artifactId) => <Link className="text-link" key={artifactId} to={`/runs/${run.id}/evidence/${artifactId}`}>Open evidence {artifactId.slice(0, 8)}</Link>)}
                  <Link className="secondary-button" to={`/runs/${run.id}/findings/${selected.id}`}>Open finding details</Link>
                </aside> : null}
                </div>
              </>
            ) : (
              <EmptyState
                title="No matching findings"
                copy="Try another search or clear your filters."
                action={
                  <Button variant="secondary" onClick={() => setParams({})}>
                    Clear filters
                  </Button>
                }
              />
            )}
          </>
        ) : (
          <EmptyState
            title="No findings in this evaluation"
            copy="This test did not produce findings from the available evaluation checks. Review the report to understand its scope and outcomes."
          />
        )}
      </section>
    </ResultsBoundary>
  );
}
