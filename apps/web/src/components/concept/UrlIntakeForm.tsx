import React, { useId, useState } from "react";

interface UrlIntakeFormProps {
  onValidSubmit?: (parsedOrigin: string, parsedUrl: string) => void;
  className?: string;
  isSubmitting?: boolean;
}

export const UrlIntakeForm: React.FC<UrlIntakeFormProps> = ({
  onValidSubmit,
  className = "",
  isSubmitting = false,
}) => {
  const uniqueId = useId();
  const inputId = `url-input-${uniqueId}`;
  const messageId = `url-msg-${uniqueId}`;

  const [value, setValue] = useState("");
  const [errorStatus, setErrorStatus] = useState<"none" | "empty" | "unparseable">("none");
  const [successOrigin, setSuccessOrigin] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();

    if (!trimmed) {
      setErrorStatus("empty");
      setSuccessOrigin(null);
      return;
    }

    let urlToParse = trimmed;
    if (!/^https?:\/\//i.test(urlToParse)) {
      urlToParse = `https://${urlToParse}`;
    }

    try {
      const parsed = new URL(urlToParse);
      // Host must have a dot or be localhost and not contain spaces
      if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password || !parsed.hostname || (!parsed.hostname.includes(".") && parsed.hostname !== "localhost") || parsed.hostname.includes(" ")) {
        setErrorStatus("unparseable");
        setSuccessOrigin(null);
        return;
      }
      const origin = `${parsed.protocol}//${parsed.host}`;
      setErrorStatus("none");
      setSuccessOrigin(origin);
      if (onValidSubmit) {
        onValidSubmit(origin, parsed.href);
      }
    } catch {
      setErrorStatus("unparseable");
      setSuccessOrigin(null);
    }
  };

  const hasError = errorStatus !== "none";

  return (
    <form
      onSubmit={handleSubmit}
      className={`concept-url-form ${className}`}
      noValidate
      style={{ width: "100%", maxWidth: "560px" }}
    >
      <label
        htmlFor={inputId}
        className="font-meta-label block"
        style={{ color: "var(--ink-2)", marginBottom: "8px" }}
      >
        YOUR APP'S ADDRESS
      </label>

      <div className="flex flex-col sm:flex-row gap-3">
        <input
          id={inputId}
          type="text"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (errorStatus !== "none") setErrorStatus("none");
            setSuccessOrigin(null);
          }}
          placeholder="yourapp.com"
          aria-invalid={hasError ? "true" : undefined}
          aria-describedby={messageId}
          disabled={isSubmitting}
          className="font-body flex-1"
          style={{
            height: "48px",
            padding: "0 16px",
            borderRadius: 0,
            border: hasError
              ? "1px solid var(--broken)"
              : "1px solid var(--ink-faint)",
            backgroundColor: "var(--card)",
            color: "var(--ink)",
          }}
        />

        <button
          type="submit"
          disabled={isSubmitting}
          className="font-button-label transition-colors sm:w-auto w-full"
          style={{
            height: "48px",
            padding: "12px 20px",
            borderRadius: 0,
            backgroundColor: isSubmitting
              ? "rgba(17,17,17,0.4)"
              : "var(--flame-deep)",
            color: "#FFFFFF",
            border: "none",
            cursor: isSubmitting ? "not-allowed" : "pointer",
            whiteSpace: "nowrap",
          }}
          onMouseEnter={(e) => {
            if (!isSubmitting) {
              e.currentTarget.style.backgroundColor = "var(--flame-deep-hover)";
            }
          }}
          onMouseLeave={(e) => {
            if (!isSubmitting) {
              e.currentTarget.style.backgroundColor = "var(--flame-deep)";
            }
          }}
        >
          START A TEST
        </button>
      </div>

      {/* Reserved message line (22px min-height so layout never jumps) */}
      <div
        id={messageId}
        aria-live="polite"
        style={{
          minHeight: "22px",
          marginTop: "8px",
          fontSize: "13px",
          lineHeight: "20px",
          fontFamily: "Inter, system-ui, sans-serif",
        }}
      >
        {errorStatus === "empty" && (
          <span style={{ color: "var(--broken)" }}>
            Enter your app's address to start.
          </span>
        )}
        {errorStatus === "unparseable" && (
          <span style={{ color: "var(--broken)" }}>
            That doesn't look like a web address. Check it and try again.
          </span>
        )}
        {successOrigin && (
          <span style={{ color: "var(--ink-2)" }}>
            We'll test {successOrigin}
          </span>
        )}
      </div>
    </form>
  );
};
