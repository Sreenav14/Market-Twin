import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorSummary, FieldError } from "./Field";
import { Checkbox, RadioGroup, Switch } from "./Choice";
import {
  FileDropZone,
  INGESTION_ACCEPT,
  INGESTION_EXTENSIONS,
  validateIngestionFile,
} from "./FileUploader";
import { Banner, InlineAlert, ToastProvider, useToast } from "./Feedback";

/* Phase 2d pins: the forms & feedback primitives carry the family's
   rules in their behaviour, not just their look — GOV.UK summary
   focus/title behaviour, APG choice semantics, the dispatcher's
   real format set, and the toast rules (no error severity exists;
   nothing expires while the user is interacting with it). */

afterEach(() => {
  vi.useRealTimers();
  document.title = "";
});

describe("FieldError", () => {
  it("carries a visually-hidden 'Error:' prefix and is NOT a live region", () => {
    render(<FieldError id="name-error">Enter a target name.</FieldError>);
    const error = document.getElementById("name-error")!;
    expect(error.getAttribute("role")).toBeNull();
    expect(error.textContent).toContain("Error:");
    expect(error.textContent).toContain("Enter a target name.");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("ErrorSummary", () => {
  it("takes focus on mount, prefixes the title, and restores both as errors clear", () => {
    document.title = "Add target";
    const errors = [
      { targetId: "target-name", message: "Enter a target name." },
      { targetId: "base-url", message: "Enter a base URL." },
    ];
    const { rerender, unmount } = render(
      <>
        <input id="target-name" aria-label="Target name" />
        <input id="base-url" aria-label="Base URL" />
        <ErrorSummary errors={errors} />
      </>,
    );
    const summary = screen.getByRole("alert");
    expect(summary).toHaveTextContent("There is a problem");
    expect(document.activeElement).toBe(summary);
    expect(document.title).toBe("Error: Add target");

    rerender(
      <>
        <input id="target-name" aria-label="Target name" />
        <input id="base-url" aria-label="Base URL" />
        <ErrorSummary errors={[errors[1]]} />
      </>,
    );
    expect(screen.queryByText("Enter a target name.")).toBeNull();
    expect(screen.getByText("Enter a base URL.")).toBeInTheDocument();

    unmount();
    expect(document.title).toBe("Add target");
  });

  it("moves focus to the field when a summary link is clicked", async () => {
    const user = userEvent.setup();
    render(
      <>
        <input id="target-name" aria-label="Target name" />
        <ErrorSummary errors={[{ targetId: "target-name", message: "Enter a target name." }]} />
      </>,
    );
    await user.click(screen.getByRole("link", { name: "Enter a target name." }));
    expect(document.activeElement).toBe(document.getElementById("target-name"));
  });
});

describe("Checkbox", () => {
  it("exposes the indeterminate state as a DOM property for group parents", () => {
    render(<Checkbox label="Select all" indeterminate checked={false} onChange={() => {}} />);
    const box = screen.getByRole("checkbox", { name: "Select all" }) as HTMLInputElement;
    expect(box.indeterminate).toBe(true);
  });
});

describe("RadioGroup", () => {
  it("is one tab stop and the arrow keys move and check (APG)", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [value, setValue] = useState("yes");
      return (
        <RadioGroup
          legend="Expected result"
          name="expected"
          value={value}
          onChange={setValue}
          options={[
            { value: "yes", label: "Yes" },
            { value: "no", label: "No" },
          ]}
        />
      );
    }
    render(<Harness />);
    const yes = screen.getByRole("radio", { name: "Yes" }) as HTMLInputElement;
    const no = screen.getByRole("radio", { name: "No" }) as HTMLInputElement;
    await user.tab();
    expect(document.activeElement).toBe(yes);
    await user.keyboard("{ArrowDown}");
    expect(no.checked).toBe(true);
    expect(document.activeElement).toBe(no);
    await user.tab();
    expect(document.activeElement).not.toBe(yes);
    expect(document.activeElement).not.toBe(no);
  });
});

describe("Switch", () => {
  it("reports state as words, toggles via aria-checked, and shows Saving… while pending", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(<Switch label="Live updates" checked={false} onChange={onChange} />);
    const control = screen.getByRole("switch", { name: "Live updates" });
    expect(control).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("Off")).toBeInTheDocument();
    await user.click(control);
    expect(onChange).toHaveBeenCalledWith(true);

    rerender(<Switch label="Live updates" checked onChange={onChange} pending />);
    expect(screen.getByRole("switch", { name: "Live updates" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("switch", { name: "Live updates" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Saving…")).toBeInTheDocument();
  });
});

describe("FileDropZone", () => {
  it("wires accept to exactly the extraction dispatcher's format set", () => {
    render(
      <FileDropZone
        id="source-file"
        file={null}
        describedBy="source-file-constraints"
        onPick={() => {}}
        onInvalid={() => {}}
        onRemove={() => {}}
      />,
    );
    const input = document.getElementById("source-file") as HTMLInputElement;
    expect(input.accept).toBe(INGESTION_ACCEPT.replace(/,/g, ","));
    for (const extension of INGESTION_EXTENSIONS) {
      expect(input.accept).toContain(extension);
    }
    expect(validateIngestionFile(new File(["x"], "notes.md"))).toBeNull();
    expect(validateIngestionFile(new File(["x"], "setup.exe"))).toMatch(/not a supported format/);
    expect(validateIngestionFile(new File([], "empty.pdf"))).toMatch(/is empty/);
  });

  it("routes a wrong-type file to the error recipe and never picks it; a valid file gets a removable row", () => {
    function Harness() {
      const [file, setFile] = useState<File | null>(null);
      const [error, setError] = useState<string | null>(null);
      return (
        <>
          <FileDropZone
            id="source-file"
            file={file}
            invalid={Boolean(error)}
            describedBy="source-file-constraints"
            onPick={(picked) => {
              setFile(picked);
              setError(null);
            }}
            onInvalid={setError}
            onRemove={() => setFile(null)}
          />
          {error ? <FieldError id="source-file-error">{error}</FieldError> : null}
        </>
      );
    }
    render(<Harness />);
    const input = document.getElementById("source-file") as HTMLInputElement;

    fireEvent.change(input, { target: { files: [new File(["x"], "setup.exe")] } });
    expect(screen.getByText(/not a supported format/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Remove/ })).toBeNull();

    fireEvent.change(input, { target: { files: [new File(["hello"], "guide.txt")] } });
    expect(screen.queryByText(/not a supported format/)).toBeNull();
    expect(screen.getByText("guide.txt")).toBeInTheDocument();
    expect(screen.getByText("5 B")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove guide.txt" }));
    expect(screen.queryByText("guide.txt")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Browse files" }));
  });
});

describe("InlineAlert and Banner", () => {
  it("renders severity as icon + title; an error carries no dismiss control", () => {
    render(
      <InlineAlert severity="error" title="Could not save" role="alert">
        The server refused the change.
      </InlineAlert>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not save");
    expect(screen.getByRole("alert")).toHaveTextContent("The server refused the change.");
    expect(screen.queryByRole("button", { name: "Dismiss notification" })).toBeNull();
  });

  it("offers dismiss only where the caller allows it, and banners never offer it", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    render(
      <>
        <InlineAlert severity="success" title="Saved" onDismiss={onDismiss} />
        <Banner severity="warning" title="The tester is paused">
          It resumes when you finish.
        </Banner>
      </>,
    );
    const dismissButtons = screen.getAllByRole("button", { name: "Dismiss notification" });
    expect(dismissButtons).toHaveLength(1);
    await user.click(dismissButtons[0]);
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent("The tester is paused");
  });
});

describe("Toasts", () => {
  function Harness() {
    const { toast } = useToast();
    return (
      <button
        onClick={() => toast({ title: "Applications saved", body: "Attached to the selected apps." })}
      >
        Save applications
      </button>
    );
  }

  it("shows a success toast in the always-mounted status region and auto-dismisses at 8s", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    const region = screen.getByRole("status");
    expect(region).toBeInTheDocument();
    expect(region).not.toHaveTextContent("Applications saved");

    fireEvent.click(screen.getByRole("button", { name: "Save applications" }));
    expect(region).toHaveTextContent("Applications saved");

    act(() => vi.advanceTimersByTime(7_999));
    expect(region).toHaveTextContent("Applications saved");
    act(() => vi.advanceTimersByTime(1));
    expect(region).not.toHaveTextContent("Applications saved");
  });

  it("pauses the countdown while hovered — nothing expires under the user", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save applications" }));
    const toast = screen.getByText("Applications saved").closest(".mt-toast")!;
    fireEvent.mouseEnter(toast);
    act(() => vi.advanceTimersByTime(20_000));
    expect(screen.getByRole("status")).toHaveTextContent("Applications saved");
    fireEvent.mouseLeave(toast);
    act(() => vi.advanceTimersByTime(8_000));
    expect(screen.getByRole("status")).not.toHaveTextContent("Applications saved");
  });
});
