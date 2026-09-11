import { useDeferredValue } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { Search, SlidersHorizontal } from "lucide-react";
import { RunContext } from "../../layouts/RunLayout";
import { FindingListItem } from "../../components/markettwin/FindingListItem";
import { ResultsBoundary } from "../../components/markettwin/ResultsBoundary";
import { EmptyState } from "../../components/ui/StateViews";
import { Button } from "../../components/ui/button";
import { severityOrder, sortFindings } from "../../lib/results";

export function RunFindingsPage() {
  const { run, results } = useOutletContext<RunContext>();
  const [params, setParams] = useSearchParams();
  const search = params.get("q") || "";
  const deferredSearch = useDeferredValue(search);
  const severity = params.get("severity") || "all";
  const category = params.get("category") || "all";
  const sort = params.get("sort") || "severity";
  const findings = results.status === "ready" ? results.data.findings : [];
  const categories = [...new Set(findings.map(finding => finding.category))].sort();
  function setFilter(key: string, value: string) {
    setParams(previous => { const next = new URLSearchParams(previous); if (!value || value === "all") next.delete(key); else next.set(key, value); return next; }, { replace: true });
  }
  const filtered = sortFindings(findings.filter(finding =>
    (severity === "all" || finding.severity === severity) &&
    (category === "all" || finding.category === category) &&
    `${finding.title} ${finding.summary} ${finding.category}`.toLowerCase().includes(deferredSearch.toLowerCase())), sort);
  return <ResultsBoundary><section aria-labelledby="findings-heading">
    <div className="section-heading"><div><h2 id="findings-heading">Findings</h2><p className="muted">Prioritize what matters, then inspect the references behind it.</p></div><span className="muted">{findings.length} total</span></div>
    {findings.length > 0 ? <><div className="filter-bar"><div className="search-field"><Search size={17} aria-hidden="true" /><label className="visually-hidden" htmlFor="finding-search">Search findings</label><input id="finding-search" value={search} onChange={event => setFilter("q", event.target.value)} placeholder="Search findings…" autoComplete="off" /></div>
      <label className="filter-select"><SlidersHorizontal size={15} aria-hidden="true" /><span className="visually-hidden">Severity</span><select aria-label="Severity" value={severity} onChange={event => setFilter("severity", event.target.value)}><option value="all">All severities</option>{severityOrder.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label className="filter-select"><span className="visually-hidden">Category</span><select aria-label="Category" value={category} onChange={event => setFilter("category", event.target.value)}><option value="all">All categories</option>{categories.map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
      <label className="filter-select"><span className="visually-hidden">Sort findings</span><select aria-label="Sort findings" value={sort} onChange={event => setFilter("sort", event.target.value)}><option value="severity">Highest severity</option><option value="journeys">Most affected journeys</option></select></label>
    </div><p className="filter-count" role="status">{filtered.length} of {findings.length} findings</p>
      {filtered.length ? <ul className="finding-list">{filtered.map(finding => <FindingListItem key={finding.id} finding={finding} runId={run.id} />)}</ul> : <EmptyState title="No matching findings" copy="Try another search or clear your filters." action={<Button variant="secondary" onClick={() => setParams({})}>Clear filters</Button>} />}
    </> : <EmptyState title="No findings in this evaluation" copy="This test did not produce findings from the available evaluation checks. Review the report to understand its scope and outcomes." />}
  </section></ResultsBoundary>;
}
