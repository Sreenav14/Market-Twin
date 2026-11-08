import React, { useEffect, useRef, useState } from "react";

interface MenuItem {
  name: string;
  description: string;
  href?: string;
  onClick?: () => void;
}

interface MenuGroup {
  label: string;
  items: MenuItem[];
}

interface MegaMenuProps {
  onNavigate?: (destination: string) => void;
  className?: string;
}

export const MegaMenu: React.FC<MegaMenuProps> = ({ onNavigate, className = "" }) => {
  /* Navigation, not a menu (Phase 2c, Spec 2 \u00a71.1): APG disclosure
     semantics \u2014 aria-expanded trigger, plain nav panel, Esc returns
     focus, click-outside closes, Tab moves through the items. The
     role="menu"/menuitem model was removed: it promised arrow-key
     menu behaviour this navigation list does not owe. */
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const groups: MenuGroup[] = [
    {
      label: "START HERE",
      items: [
        {
          name: "Add an app",
          description: "Give us your app's address. That is all we need to begin.",
          onClick: () => {
            setIsOpen(false);
            if (onNavigate) onNavigate("Add an app");
          },
        },
      ],
    },
    {
      label: "SEE IT WORKING",
      items: [
        {
          name: "Dashboard",
          description: "Everything that needs you, and everything running.",
          onClick: () => {
            setIsOpen(false);
            if (onNavigate) onNavigate("Dashboard");
          },
        },
        {
          name: "Watch live",
          description: "See each tester working, as it happens.",
          onClick: () => {
            setIsOpen(false);
            if (onNavigate) onNavigate("Watch live");
          },
        },
        {
          name: "Test results",
          description: "What worked, what broke, and the proof.",
          onClick: () => {
            setIsOpen(false);
            if (onNavigate) onNavigate("Test results");
          },
        },
        {
          name: "Testers",
          description: "Who checks your app, and how they see it.",
          onClick: () => {
            setIsOpen(false);
            if (onNavigate) onNavigate("Testers");
          },
        },
      ],
    },
    {
      label: "GET YOUR ANSWERS",
      items: [
        {
          name: "Example report",
          description: "A real test, written the way yours will be.",
          onClick: () => {
            setIsOpen(false);
            if (onNavigate) onNavigate("Example report");
          },
        },
        {
          name: "How it works",
          description: "From address to answer, step by step.",
          onClick: () => {
            setIsOpen(false);
            if (onNavigate) onNavigate("How it works");
          },
        },
        {
          name: "Your apps",
          description: "Every app you have added, and its latest verdict.",
          onClick: () => {
            setIsOpen(false);
            if (onNavigate) onNavigate("Your apps");
          },
        },
      ],
    },
  ];

  // Close on outside click or Escape
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    };

    const handlePointerDown = (e: PointerEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [isOpen]);

  return (
    <div
      ref={containerRef}
      className={`concept-megamenu-wrapper relative inline-block ${className}`}
    >
      {/* Trigger button */}
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(!isOpen)}
        className="font-button-label inline-flex items-center gap-1.5 transition-colors"
        style={{
          minHeight: "44px",
          padding: "8px 12px",
          backgroundColor: "transparent",
          border: "none",
          color: "var(--ink)",
          cursor: "pointer",
        }}
      >
        <span>PRODUCT</span>
        <span
          aria-hidden="true"
          style={{
            transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 150ms ease",
            display: "inline-block",
            fontSize: "10px",
          }}
        >
          ⌄
        </span>
      </button>

      {/* Mega panel (desktop) */}
      {isOpen && (
        <div
          aria-label="Product navigation"
          className="hidden md:grid grid-cols-3 absolute left-0 z-50" data-nav-disclosure="true"
          style={{
            top: "calc(100% + 8px)",
            width: "880px",
            maxWidth: "calc(100vw - 48px)",
            backgroundColor: "var(--card)",
            border: "1px solid var(--line)",
            borderRadius: "12px",
            boxShadow: "var(--shadow-panel)",
            padding: "24px",
            gap: "32px",
          }}
        >
          {groups.map((group) => (
            <div key={group.label} className="flex flex-col gap-3">
              <div
                className="font-meta-label"
                style={{ color: "var(--ink-faint)", marginBottom: "4px" }}
              >
                {group.label}
              </div>

              {group.items.map((item) => (
                <button
                  key={item.name}
                  type="button"
                  onClick={item.onClick}
                  className="text-left w-full transition-colors flex flex-col p-2"
                  style={{
                    backgroundColor: "transparent",
                    border: "none",
                    borderRadius: "6px",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.backgroundColor = "var(--paper)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.backgroundColor = "transparent")
                  }
                >
                  <div
                    className="font-grid-cell flex items-center justify-between"
                    style={{
                      fontSize: "15px",
                      lineHeight: "22px",
                      fontWeight: 600,
                      color: "var(--ink)",
                    }}
                  >
                    <span>{item.name}</span>
                  </div>
                  <div
                    className="font-body-small"
                    style={{
                      fontSize: "13px",
                      lineHeight: "20px",
                      color: "var(--ink-2)",
                      marginTop: "2px",
                    }}
                  >
                    {item.description}
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Accordion panel (mobile ≤900px) */}
      {isOpen && (
        <div
          aria-label="Product navigation"
          className="md:hidden flex flex-col gap-4 absolute left-0 z-50 p-4"
          style={{
            top: "calc(100% + 8px)",
            width: "calc(100vw - 32px)",
            backgroundColor: "var(--card)",
            border: "1px solid var(--line)",
            borderRadius: "12px",
            boxShadow: "var(--shadow-panel)",
          }}
        >
          {groups.map((group) => (
            <div key={group.label} className="flex flex-col gap-2">
              <div
                className="font-meta-label"
                style={{ color: "var(--ink-faint)", borderBottom: "1px solid var(--line)", paddingBottom: "4px" }}
              >
                {group.label}
              </div>
              {group.items.map((item) => (
                <button
                  key={item.name}
                  type="button"
                  onClick={item.onClick}
                  className="text-left py-2 font-grid-cell"
                  style={{
                    backgroundColor: "transparent",
                    border: "none",
                    color: "var(--ink)",
                    fontWeight: 600,
                    minHeight: "44px",
                  }}
                >
                  <div>{item.name}</div>
                  <div className="font-body-small" style={{ color: "var(--ink-2)", fontWeight: 400 }}>
                    {item.description}
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
