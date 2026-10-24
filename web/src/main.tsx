import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { ToastProvider } from "./components/Toast";
import { AuthProvider } from "./auth/AuthProvider";
import { shouldRetry } from "./lib/http";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "@fontsource/manrope/800.css";
import "./theme.css";
import "./public.css";
import "./queue.css";
import "./cutout.css";

// No refetch on window focus: switching tabs would fire every query again at once, which trips the hosts' rate limit.
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: shouldRetry, retryDelay: 3000, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider><ToastProvider><App /></ToastProvider></AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
