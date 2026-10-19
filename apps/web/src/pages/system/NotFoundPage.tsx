import { Link } from "react-router-dom";
import { Compass, Home } from "lucide-react";

export function NotFoundPage() {
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
          <Compass size={24} aria-hidden="true" />
        </div>

        <h1 style={{ fontSize: 22, fontWeight: 650, margin: "0 0 10px", color: "var(--text)" }}>
          Page unavailable
        </h1>

        <p style={{ fontSize: 14, color: "var(--text-2)", lineHeight: 1.6, margin: "0 0 24px" }}>
          The requested page or resource could not be found. It may have moved, been archived, or may not exist in your active workspace.
        </p>

        <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
          <Link
            to="/overview"
            className="primary-button"
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <Home size={15} aria-hidden="true" />
            <span>Return to Overview</span>
          </Link>
          <Link to="/runs" className="secondary-button">
            View Tests
          </Link>
        </div>
      </div>
    </div>
  );
}
