import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { BrandMark } from "../components/ui/BrandMark";
import { ToastProvider } from "../components/ui/Feedback";
import { ErrorPanel, Spinner } from "../components/ui/StateViews";
import { ApiError, CurrentUser, api } from "../lib/api";
import { AsyncState } from "../lib/useAsync";
import { LoginPage } from "../pages/auth/LoginPage";
import { AuthCallbackPage } from "../pages/auth/AuthCallbackPage";
import { AuthenticatedRouter } from "./router";
import { queryClient } from "../lib/query";
import { HowPage } from "../pages/public/PublicPages";
import {
  LandingPage,
  DashboardPage,
  TestResultsPage,
  WatchLivePage,
} from "../pages/concept";

function AppRoot() {
  const { pathname, search, state: navigationState } = useLocation();
  const navigate = useNavigate();
  const sessionRequest = useRef(0);
  const [session, setSession] = useState<AsyncState<CurrentUser>>({
    status: "loading",
    data: null,
    error: null,
  });

  const handleConceptNavigate = (destination: string) => {
    switch (destination) {
      case "Landing page":
        navigate("/");
        break;
      case "Dashboard":
        navigate(pathname.startsWith("/examples/") ? "/examples/dashboard" : "/dashboard");
        break;
      case "Watch live":
        navigate(pathname.startsWith("/examples/") ? "/examples/watch" : "/dashboard");
        break;
      case "Test results":
        navigate(pathname.startsWith("/examples/") ? "/examples/results" : "/runs");
        break;
      case "How it works":
        navigate("/how-it-works");
        break;
      case "Example report":
        navigate("/examples/results");
        break;
      case "Add an app":
        navigate("/applications/new");
        break;
      case "Your apps":
        navigate("/applications");
        break;
      case "Tests":
        navigate("/runs");
        break;
      case "Needs your help":
        navigate("/dashboard");
        break;
      case "Testers":
        navigate("/agents");
        break;
      case "Settings":
        navigate("/settings");
        break;
      case "Sign in":
        navigate("/login");
        break;
      default:
        break;
    }
  };

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

  // Concept and public pages stay available while workspace access is resolving.
  if (pathname === "/" || pathname === "/landing") {
    return <LandingPage onNavigate={handleConceptNavigate}
      onStartTest={(url) => navigate(`/applications/new?url=${encodeURIComponent(url)}`)} />;
  }
  if (pathname === "/examples/dashboard") {
    return <DashboardPage onNavigate={handleConceptNavigate} />;
  }
  if (pathname === "/examples/results") {
    return <TestResultsPage onNavigate={handleConceptNavigate} />;
  }
  if (pathname === "/examples/watch") {
    return <WatchLivePage onNavigate={handleConceptNavigate} />;
  }
  if (pathname === "/how-it-works") return <HowPage />;
  if (pathname === "/login" && session.status === "ready") {
    const returnTo: unknown = navigationState?.returnTo;
    return <Navigate to={typeof returnTo === "string" && returnTo.startsWith("/") && !returnTo.startsWith("//") ? returnTo : "/dashboard"} replace />;
  }
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
        <Route path="*" element={<Navigate to="/login" state={{ returnTo: pathname + search }} replace />} />
      </Routes>
    );
  }

  return <AuthenticatedRouter user={session.data} onLogout={logout} />;
}

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppRoot />
      </ToastProvider>
    </BrowserRouter>
  );
}
