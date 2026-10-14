import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { BrandMark } from "../components/ui/BrandMark";
import { ErrorPanel, Spinner } from "../components/ui/StateViews";
import { ApiError, CurrentUser, api } from "../lib/api";
import { AsyncState } from "../lib/useAsync";
import { LoginPage } from "../pages/auth/LoginPage";
import { AuthCallbackPage } from "../pages/auth/AuthCallbackPage";
import { AuthenticatedRouter } from "./router";
import { queryClient } from "../lib/query";
import { HomePage, HowPage } from "../pages/public/PublicPages";

function AppRoot() {
  const { pathname } = useLocation();
  const sessionRequest = useRef(0);
  const [session, setSession] = useState<AsyncState<CurrentUser>>({
    status: "loading",
    data: null,
    error: null,
  });

  const resolveSession = useCallback(() => {
    const requestId = ++sessionRequest.current;
    setSession({ status: "loading", data: null, error: null });
    api
      .me()
      .then((user) => {
        if (requestId === sessionRequest.current)
          setSession({ status: "ready", data: user, error: null });
      })
      .catch((error: unknown) => {
        if (requestId !== sessionRequest.current) return;
        if (error instanceof ApiError && error.status === 401) {
          setSession({ status: "error", data: null, error: "unauthenticated" });
        } else {
          setSession({
            status: "error",
            data: null,
            error:
              error instanceof Error ? error.message : "Unable to connect.",
          });
        }
      });
  }, []);

  useEffect(resolveSession, [resolveSession]);

  async function logout() {
    await api.logout();
    sessionRequest.current += 1;
    queryClient.clear();
    setSession({ status: "error", data: null, error: "unauthenticated" });
  }

  // Public product pages stay available while workspace access is resolving.
  if (pathname === "/") return <HomePage />;
  if (pathname === "/how-it-works") return <HowPage />;
  if (pathname === "/login" && session.status !== "ready") {
    return <LoginPage onAuthenticated={(user) => {
      sessionRequest.current += 1;
      setSession({ status: "ready", data: user, error: null });
    }} />;
  }

  if (session.status === "loading") {
    return (
      <div className="boot-screen">
        <BrandMark />
        <Spinner />
        <span>Opening MarketTwin…</span>
      </div>
    );
  }

  if (session.status === "error") {
    if (session.error !== "unauthenticated") {
      return (
        <div className="boot-screen">
          <BrandMark />
          <ErrorPanel
            message={session.error}
            action={
              <button className="secondary-button" onClick={resolveSession}>
                Try again
              </button>
            }
          />
        </div>
      );
    }

    return (
      <Routes>
        <Route
          path="/login"
          element={
            <LoginPage
              onAuthenticated={(user) =>
                setSession({ status: "ready", data: user, error: null })
              }
            />
          }
        />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return <AuthenticatedRouter user={session.data} onLogout={logout} />;
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoot />
    </BrowserRouter>
  );
}
