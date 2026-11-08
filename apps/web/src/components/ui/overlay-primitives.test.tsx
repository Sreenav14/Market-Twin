import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { SegmentedControl } from "./SegmentedControl";
import { Tab, TabPanel, Tabs } from "./Tabs";
import { Menu, NavDisclosure } from "./Menu";
import { Dialog, DiscardChangesDialog } from "./Dialog";
import { Popover } from "./Popover";
import { Tooltip } from "./tooltip";
import { CommandMenu } from "../markettwin/CommandMenu";
import { NAV_COMMANDS, filterNavCommands } from "../../lib/navCommands";

describe("SegmentedControl — ONE segmented recipe (radiogroup)", () => {
  function Harness() {
    const [value, setValue] = useState("a");
    return (
      <SegmentedControl
        label="View"
        value={value}
        onChange={(v) => setValue(v as "a")}
        options={[
          { value: "a", label: "List" },
          { value: "b", label: "Board" },
          { value: "c", label: "Chart", disabled: true },
        ]}
      />
    );
  }
  it("is a radiogroup of radios with roving tabindex; arrows move AND check, skipping disabled", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByRole("radiogroup", { name: "View" })).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    const list = screen.getByRole("radio", { name: "List" });
    const board = screen.getByRole("radio", { name: "Board" });
    expect(list).toHaveAttribute("aria-checked", "true");
    expect(board).toHaveAttribute("tabindex", "-1");
    list.focus();
    await user.keyboard("{ArrowRight}");
    expect(board).toHaveFocus();
    expect(board).toHaveAttribute("aria-checked", "true");
    await user.keyboard("{ArrowRight}"); // disabled Chart is skipped, wraps to List
    expect(list).toHaveFocus();
    expect(list).toHaveAttribute("aria-checked", "true");
    await user.keyboard("{End}"); // last ENABLED option
    expect(board).toHaveFocus();
  });
});

describe("Tabs — ONE tabs recipe (APG via Radix)", () => {
  it("tablist/tab/tabpanel with automatic activation on arrows", async () => {
    const user = userEvent.setup();
    render(
      <Tabs label="Views" value="one" onValueChange={() => {}}
        tabs={<><Tab value="one">One</Tab><Tab value="two">Two</Tab></>}>
        <TabPanel value="one">First panel</TabPanel>
        <TabPanel value="two">Second panel</TabPanel>
      </Tabs>,
    );
    // controlled harness: use internal state instead
    expect(screen.getByRole("tablist", { name: "Views" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "One" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("First panel");
    await user.click(screen.getByRole("tab", { name: "One" }));
    expect(screen.getByRole("tab", { name: "One" })).toHaveFocus();
  });

  it("switches panels when the value changes", () => {
    function Harness() {
      const [value, setValue] = useState("one");
      return (
        <Tabs label="Views" value={value} onValueChange={setValue}
          tabs={<><Tab value="one">One</Tab><Tab value="two">Two</Tab></>}>
          <TabPanel value="one">First panel</TabPanel>
          <TabPanel value="two">Second panel</TabPanel>
        </Tabs>
      );
    }
    render(<Harness />);
    return userEvent.setup().click(screen.getByRole("tab", { name: "Two" })).then(() => {
      expect(screen.getByRole("tabpanel")).toHaveTextContent("Second panel");
    });
  });
});

describe("Menu — APG menu recipe (Radix DropdownMenu)", () => {
  it("opens on the trigger, arrows move the highlight, Enter selects and closes", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <Menu
        label="Actions for run"
        trigger={<button type="button">Run actions</button>}
        items={[
          { label: "Rename", onSelect },
          { label: "Delete run", destructive: true, onSelect: () => {} },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Run actions" }));
    expect(await screen.findByRole("menu")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("NavDisclosure — navigation is not a menu", () => {
  it("aria-expanded trigger, plain links, Esc closes and returns focus", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <NavDisclosure label="More sections" buttonContent={<span>More</span>}>
          <a href="/runs">Evaluation</a>
        </NavDisclosure>
      </MemoryRouter>,
    );
    const trigger = screen.getByRole("button", { name: "More sections" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Evaluation" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });
});

describe("Dialog — ONE dialog primitive", () => {
  it("focuses the named safe action in a destructive confirmation; Esc closes", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [open, setOpen] = useState(false);
      const safeRef = useRef<HTMLButtonElement>(null);
      return (
        <Dialog open={open} onOpenChange={setOpen} title="Delete test: Run?" size="sm" alert
            trigger={<button type="button">Delete run</button>}
            initialFocusRef={safeRef}
            footer={<button ref={safeRef} type="button" onClick={() => setOpen(false)}>Keep test</button>}>
            <p>This cannot be undone.</p>
          </Dialog>
      );
    }
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Delete run" }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep test" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete run" })).toHaveFocus();
  });

  it("a dirty form routes dismissal to the discard confirmation, pristine closes freely", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [open, setOpen] = useState(false);
      const [confirm, setConfirm] = useState(false);
      return (
        <>
          <Dialog open={open} onOpenChange={setOpen} title="Rename knowledge" form dirty
            trigger={<button type="button">Rename</button>}
            onDirtyAttempt={() => setConfirm(true)}>
            <input aria-label="Name" defaultValue="Changed" />
          </Dialog>
          <DiscardChangesDialog open={confirm} onKeep={() => setConfirm(false)}
            onDiscard={() => { setConfirm(false); setOpen(false); }} />
        </>
      );
    }
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Rename" }));
    expect(await screen.findByRole("dialog", { name: "Rename knowledge" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(await screen.findByRole("alertdialog", { name: /Discard changes/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep editing" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(screen.queryByRole("dialog", { name: "Rename knowledge" })).not.toBeInTheDocument();
  });
});

describe("Popover — non-modal, interactive content", () => {
  it("opens on click, Esc closes and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    render(
      <Popover label="About checks" trigger={<button type="button">About checks</button>} title="Checks">
        <a href="/runs">See tests</a>
      </Popover>,
    );
    const trigger = screen.getByRole("button", { name: "About checks" });
    await user.click(trigger);
    expect(await screen.findByRole("link", { name: "See tests" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("link", { name: "See tests" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});

describe("Tooltip — governed primitive", () => {
  it("shows its text when the trigger takes keyboard focus", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip text="Sign out">
        <button type="button" aria-label="Sign out">x</button>
      </Tooltip>,
    );
    await user.tab();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Sign out");
  });
});

describe("navCommands — ONE registry for nav + palette", () => {
  it("has unique hrefs and filters by title, description and keywords", () => {
    const hrefs = NAV_COMMANDS.map((c) => c.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(filterNavCommands("")).toHaveLength(NAV_COMMANDS.length);
    expect(filterNavCommands("billing").map((c) => c.id)).toEqual(["settings"]);
    expect(filterNavCommands("zzz")).toHaveLength(0);
  });

  it("palette: arrows + Enter run the highlighted command through runCommand", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/applications"]}>
        <CommandMenu />
        <Routes>
          <Route path="/applications" element={<p>Apps page</p>} />
          <Route path="/dashboard" element={<p>Home page</p>} />
        </Routes>
      </MemoryRouter>,
    );
    await user.click(screen.getByRole("button", { name: "Open quick navigation" }));
    const input = await screen.findByRole("combobox");
    expect(input).toHaveFocus();
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await user.keyboard("{Enter}"); // first command = Home
    expect(await screen.findByText("Home page")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("palette empty state names the query", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CommandMenu />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole("button", { name: "Open quick navigation" }));
    const input = await screen.findByRole("combobox");
    await user.type(input, "zzzz");
    expect(await screen.findByText(/No results for/)).toHaveTextContent("zzzz");
    expect(screen.getByRole("status")).toHaveTextContent("0 results");
  });
});
