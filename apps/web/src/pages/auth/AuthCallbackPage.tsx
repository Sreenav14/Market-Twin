import { useEffect } from "react";
export function AuthCallbackPage() {
  useEffect(() => { document.title = "Authentication · MarketTwin"; }, []);
  return <div className="auth-layout"><main className="auth-main auth-main-single"><section className="auth-card"><p className="eyebrow">Production authentication</p><h1 className="auth-callback-title">Cognito callback</h1><p className="panel-note">Production Cognito Authorization Code + PKCE is part of the locked architecture, but the current local V1 uses the local identity provider. This route does not simulate a production login.</p></section></main></div>;
}
