import { useOutletContext } from "react-router-dom";
import { AppShellContext } from "../../layouts/AppShell";
import { useTheme, type ThemeMode } from "../../lib/theme";
export function ProfileSettingsPage() {
  const { user } = useOutletContext<AppShellContext>();
  const { theme, setTheme } = useTheme();
  return (
    <section className="panel settings-panel">
      <div className="section-heading compact-heading">
        <div>
          <h2>Profile</h2>
        </div>
      </div>
      <dl className="definition-list">
        <div>
          <dt>Name</dt>
          <dd>{user.display_name || "Not set"}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd>{user.email}</dd>
        </div>
        <div>
          <dt>User ID</dt>
          <dd className="monospace">{user.id}</dd>
        </div>
      </dl>
      <p className="panel-note">
        Profile details are read-only here.
      </p>
      <div className="form-grid">
        <label htmlFor="appearance-theme">Appearance</label>
        <select id="appearance-theme" value={theme}
          onChange={(event) => setTheme(event.target.value as ThemeMode)}>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
          <option value="system">Use device setting</option>
        </select>
        <p className="form-help">Saved for this browser and applied throughout the app.</p>
      </div>
    </section>
  );
}
