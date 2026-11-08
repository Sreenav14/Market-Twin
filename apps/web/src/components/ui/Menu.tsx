import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useEffect, useRef, useState, type ReactElement, type ReactNode } from "react";

/* ONE menu recipe (Phase 2c, Spec 2 §1): APG Menu via Radix
   DropdownMenu — roving highlight shared by mouse and keyboard,
   Esc returns focus to the trigger, Tab closes and moves on,
   typeahead built in. Menus are ACTIONS on one object; navigation
   lists use NavDisclosure, form value choice uses a real select. */

export interface MenuItemSpec {
  label: string;
  onSelect?: () => void;
  destructive?: boolean;
  disabled?: boolean;
  shortcut?: string;
  checked?: boolean;
}

export function Menu({
  label,
  trigger,
  items,
  groups,
}: {
  label: string;
  trigger: ReactElement;
  items?: MenuItemSpec[];
  groups?: { label: string; items: MenuItemSpec[] }[];
}) {
  const renderItem = (item: MenuItemSpec) => (
    <DropdownMenu.Item
      key={item.label}
      className={`mt-menu-item${item.destructive ? " mt-menu-item--danger" : ""}`}
      disabled={item.disabled}
      onSelect={() => item.onSelect?.()}
    >
      <span>{item.label}</span>
      {item.checked ? <span aria-hidden="true">✓</span> : null}
      {item.shortcut ? <span className="mt-menu-shortcut">{item.shortcut}</span> : null}
    </DropdownMenu.Item>
  );
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>{trigger}</DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="mt-menu-content" sideOffset={4} aria-label={label}>
          {groups
            ? groups.map((group, i) => (
                <DropdownMenu.Group key={group.label}>
                  {i > 0 ? <DropdownMenu.Separator className="mt-menu-separator" /> : null}
                  <DropdownMenu.Label className="mt-menu-label">{group.label}</DropdownMenu.Label>
                  {group.items.map(renderItem)}
                </DropdownMenu.Group>
              ))
            : (items ?? []).map(renderItem)}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

/* APG Disclosure Navigation (Spec 2 §1.6 exception): a button with
   aria-expanded and a plain list of links — Tab moves through the
   links, Esc closes and returns focus to the button, click-outside
   closes; no arrow-key menu model is promised or intercepted.
   Replaces the <details>-based "More" menu. */
export function NavDisclosure({
  label,
  buttonContent,
  buttonClassName = "",
  panelClassName = "",
  children,
}: {
  label: string;
  buttonContent: ReactNode;
  buttonClassName?: string;
  panelClassName?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open ]);

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        ref={buttonRef}
        type="button"
        className={buttonClassName}
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((value) => !value)}
      >
        {buttonContent}
      </button>
      {open ? (
        <div
          className={`mt-disclosure-panel ${panelClassName}`.trim()}
          aria-label={label}
          style={{ position: "absolute", zIndex: 60 }}
          onClick={(event) => {
            if ((event.target as HTMLElement).closest("a[href]")) setOpen(false);
          }}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
