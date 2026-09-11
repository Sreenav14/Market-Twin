import { House, LayoutGrid, Play, Settings, Plus, ArrowRight, LogOut, Target, ShieldCheck, TriangleAlert, Check, UserRound, Building2 } from "lucide-react";

const icons = { home: House, apps: LayoutGrid, runs: Play, settings: Settings, plus: Plus, arrow: ArrowRight, logout: LogOut, target: Target, shield: ShieldCheck, warning: TriangleAlert, check: Check, user: UserRound, workspace: Building2 };
export type IconName = keyof typeof icons;
export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const Component = icons[name];
  return <Component size={size} strokeWidth={1.7} aria-hidden="true" />;
}
