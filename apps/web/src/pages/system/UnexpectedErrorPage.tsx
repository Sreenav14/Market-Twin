import { Link } from "react-router-dom";
import { AlertCircle, Home, RotateCcw } from "lucide-react";
import { Button } from "../../components/ui/button";

export function UnexpectedErrorPage() {
  function handleReload() {
    window.location.reload();
  }

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "65vh",
        padding: "32px 16px",
      }}
    >
      <div
        style={{
          maxWidth: 520,
          width: "100%",
          padding: "36px 32px",
          borderRadius: 12,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.04)",
          textAlign: "center",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 48,
            height: 48,
            borderRadius: "50%",
            background: "var(--surface-muted)",
            color: "var(--text-2)",
            marginBottom: 20,
          }}
        >
          <AlertCircle size={24} aria-hidden="true" />
        </div>

        <h1 style={{ fontSize: 22, fontWeight: 650, margin: "0 0 10px", color: "var(--text)" }}>
          Something unexpected occurred
        </h1>

        <p style={{ fontSize: 14, color: "var(--text-2)", lineHeight: 1.6, margin: "0 0 24px" }}>
          MarketTwin encountered an issue while rendering this view. Your saved test configurations, execution logs, and captured evidence remain safe and unaffected in the database.
        </p>

        <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
          <Button
            variant="secondary"
            onClick={handleReload}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <RotateCcw size={14} aria-hidden="true" />
            <span>Reload page</span>
          </Button>

          <Link
            to="/overview"
            className="primary-button"
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <Home size={15} aria-hidden="true" />
            <span>Return to Overview</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
