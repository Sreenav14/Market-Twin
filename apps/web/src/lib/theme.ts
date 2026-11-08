import { useEffect, useState } from "react";

export type ThemeMode = "dark" | "light" | "system";

const STORAGE_KEY = "markettwin-theme";

export function getStoredTheme(): ThemeMode {
  if (typeof window === "undefined") return "light";
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // Rendering must still work when Chrome blocks site storage.
  }
  // The warm concept is the single product theme; light is the default.
  return "light";
}

export function getEffectiveTheme(mode: ThemeMode = getStoredTheme()): "dark" | "light" {
  if (mode === "system") {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  }
  return mode;
}

export function applyTheme(mode: ThemeMode): void {
  if (typeof document === "undefined") return;
  const effective = getEffectiveTheme(mode);
  const root = document.documentElement;

  root.setAttribute("data-theme", effective);
  if (effective === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }

  // Update meta color-scheme and theme-color
  const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
  if (colorSchemeMeta) {
    colorSchemeMeta.setAttribute("content", effective);
  }
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  if (themeColorMeta) {
    themeColorMeta.setAttribute("content", effective === "dark" ? "#101214" : "#F5F4F2");
  }

  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // localStorage may be restricted in private browsing
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(() => getStoredTheme());
  const [effectiveTheme, setEffectiveTheme] = useState<"dark" | "light">(() => getEffectiveTheme());

  useEffect(() => {
    applyTheme(theme);
    setEffectiveTheme(getEffectiveTheme(theme));

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleMediaChange = () => {
      if (getStoredTheme() === "system") {
        applyTheme("system");
        setEffectiveTheme(getEffectiveTheme("system"));
      }
    };

    mediaQuery.addEventListener("change", handleMediaChange);
    return () => mediaQuery.removeEventListener("change", handleMediaChange);
  }, [theme]);

  const setTheme = (nextTheme: ThemeMode) => {
    setThemeState(nextTheme);
    applyTheme(nextTheme);
  };

  const toggleTheme = () => {
    const next = effectiveTheme === "dark" ? "light" : "dark";
    setTheme(next);
  };

  return {
    theme,
    effectiveTheme,
    setTheme,
    toggleTheme,
    isDark: effectiveTheme === "dark",
  };
}
