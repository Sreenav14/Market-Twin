import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { BrandMark } from "../components/ui/BrandMark";
import { ErrorPanel, Spinner } from "../components/ui/StateViews";
import { ApiError, CurrentUser, api } from "../lib/api";
import { AsyncState } from "../lib/useAsync";
import { LoginPage } from "../pages/auth/LoginPage";
import { SignupPage } from "../pages/auth/SignupPage";
import { AuthCallbackPage } from "../pages/auth/AuthCallbackPage";
import { AuthenticatedRouter } from "./router";

function AppRoot() {
  const [session, setSession] = useState<AsyncState<CurrentUser>>({ status: "loading", data: null, error: null });

  const resolveSession = useCallback(() => {
    setSession({ status: "loading", data: null, error: null });
    api.me()
      .then((user) => setSession({ status: "ready", data: user, error: null }))
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          setSession({ status: "error", data: null, error: "unauthenticated" });
        } else {
          setSession({ status: "error", data: null, error: error instanceof Error ? error.message : "Unable to connect." });
        }
      });
  }, []);

  useEffect(resolveSession, [resolveSession]);

  async function logout() {
    await api.logout();
    setSession({ status: "error", data: null, error: "unauthenticated" });
  }

  if (session.status === "loading") {
    return <div className="boot-screen"><BrandMark /><Spinner /><span>Opening MarketTwin…</span></div>;
  }

  if (session.status === "error") {
    if (session.error !== "unauthenticated") {
      return <div className="boot-screen"><BrandMark /><ErrorPanel message={session.error} action={<button className="secondary-button" onClick={resolveSession}>Try again</button>} /></div>;
    }

    return (
      <Routes>
        <Route path="/login" element={<LoginPage onAuthenticated={(user) => setSession({ status: "ready", data: user, error: null })} />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return <AuthenticatedRouter user={session.data} onLogout={logout} />;
}

export function App() {
  return <BrowserRouter><AppRoot /></BrowserRouter>;
}
