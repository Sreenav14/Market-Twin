export type IconName = "home" | "apps" | "runs" | "settings" | "plus" | "arrow" | "logout" | "target" | "shield" | "warning" | "check" | "user" | "workspace";

const paths: Record<IconName, string> = {
  home: "M3 10.5 10 4l7 6.5V18H6v-7.5",
  apps: "M3.5 3.5h5v5h-5zM11.5 3.5h5v5h-5zM3.5 11.5h5v5h-5zM11.5 11.5h5v5h-5z",
  runs: "M5 3.5 15.5 10 5 16.5z",
  settings: "M10 6.8a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4ZM10 2.5v2M10 15.5v2M17.5 10h-2M4.5 10h-2M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4M15.3 15.3l-1.4-1.4M6.1 6.1 4.7 4.7",
  plus: "M10 4v12M4 10h12",
  arrow: "M4 10h11M11 6l4 4-4 4",
  logout: "M8 4H4v12h4M12 6l4 4-4 4M16 10H8",
  target: "M10 3a7 7 0 1 0 7 7M10 6a4 4 0 1 0 4 4M10 9a1 1 0 1 0 1 1",
  shield: "M10 2.7 16 5v4.6c0 3.7-2.5 6.3-6 7.7-3.5-1.4-6-4-6-7.7V5z",
  warning: "M10 3 18 17H2zM10 7v4M10 14h.01",
  check: "m4.5 10.2 3.2 3.2 7.8-7.8",
  user: "M10 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM3.5 17c.7-3.2 3.1-5 6.5-5s5.8 1.8 6.5 5",
  workspace: "M3 5h14v11H3zM7 5V3h6v2",
};

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}
