import { Component, type ReactNode } from "react";

/** Keep render failures visible without exposing exception content to the UI. */
export class RenderErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return <main className="boot-screen error-page" role="alert">
        <h1>Something went wrong</h1>
        <p>MarketTwin could not display this view. Reload to try again.</p>
        <button type="button" className="primary-button" onClick={() => window.location.reload()}>Reload MarketTwin</button>
      </main>;
    }
    return this.props.children;
  }
}
