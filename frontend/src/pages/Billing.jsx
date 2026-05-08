import { useState } from "react";
import { Link } from "react-router-dom";
import { createPayment, simulatePaymentSuccess } from "../lib/api";
import NeuroVaultLogo from "../components/NeuroVaultLogo";

function MethodIcon({ method }) {
  if (method === "easypaisa") {
    return (
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M4 7H20V17H4V7Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
          <path d="M8 11H16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          <path d="M8 14H13" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      </span>
    );
  }

  if (method === "jazzcash") {
    return (
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/15 text-amber-300">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.7" />
          <path d="M8.5 12H15.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          <path d="M12 8.5V15.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      </span>
    );
  }

  return (
    <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-sky-500/15 text-sky-300">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3.5" y="6.5" width="17" height="11" rx="2" stroke="currentColor" strokeWidth="1.7" />
        <path d="M3.5 10.5H20.5" stroke="currentColor" strokeWidth="1.7" />
      </svg>
    </span>
  );
}

export default function Billing({ user, onRefreshUser, onLogout }) {
  const [loadingMethod, setLoadingMethod] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const isPro = user?.plan === "pro" && user?.status === "active";
  const simulationEnabled = import.meta.env.VITE_ENABLE_PAYMENT_SIMULATION === "true";

  async function handlePay(method) {
    if (isPro) {
      return;
    }
    setLoadingMethod(method);
    setError("");
    setMessage("");
    try {
      const response = await createPayment(method, 2000);
      window.location.href = response.checkout_url;
    } catch (payError) {
      setError(payError.message);
      setLoadingMethod("");
    }
  }

  async function handleSimulate(method) {
    setLoadingMethod(`simulate-${method}`);
    setError("");
    setMessage("");
    try {
      await simulatePaymentSuccess(method);
      await onRefreshUser?.();
      setMessage(`Simulated ${method} payment success. Your subscription is now updated.`);
    } catch (simulateError) {
      setError(simulateError.message);
    } finally {
      setLoadingMethod("");
    }
  }

  return (
    <section className="h-screen overflow-hidden p-3 md:p-4">
      <div className="grid h-full grid-cols-1 gap-3">
        <div className="panel flex items-center justify-between p-4">
          <div>
            <NeuroVaultLogo subtitle="Billing & Subscription" />
          </div>
          <div className="flex items-center gap-2">
            <Link to="/chat" className="rounded-lg border border-line px-3 py-2 text-sm text-slate-300 hover:bg-slate-800/50">
              Back to chat
            </Link>
            <button
              type="button"
              onClick={onLogout}
              className="rounded-lg border border-line px-3 py-2 text-sm text-slate-300 hover:bg-slate-800/50"
            >
              Logout
            </button>
          </div>
        </div>

        <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
          <div className="panel p-5">
            <h2 className="text-xl font-semibold text-white">Subscription</h2>
            <p className="mt-1 text-sm text-slate-300">Current plan: {user?.plan?.toUpperCase()} ({user?.status})</p>
            <p className="text-sm text-slate-300">Total requests used: {user?.requests_count ?? 0}</p>
            {isPro ? <p className="mt-2 text-sm text-emerald-300">Pro plan is active.</p> : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[
              { method: "easypaisa", title: "Easypaisa", desc: "Pay using Easypaisa wallet or app" },
              { method: "jazzcash", title: "JazzCash", desc: "Pay via JazzCash merchant checkout" },
              { method: "cardpayment", title: "Card Payment", desc: "Pay securely with debit or credit card" },
            ].map((item) => (
              <div key={item.method} className="panel p-5">
                <div className="flex items-center gap-3">
                  <MethodIcon method={item.method} />
                  <h3 className="text-lg font-semibold text-white">{item.title}</h3>
                </div>
                <p className="mt-2 text-sm text-slate-300">{item.desc}</p>
                <p className="mt-3 text-sm text-slate-400">PKR 2,000 / month</p>
                <button
                  type="button"
                  onClick={() => void handlePay(item.method)}
                  disabled={loadingMethod === item.method || isPro}
                  className="mt-4 w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium text-black disabled:opacity-60"
                >
                  {isPro ? "Already active" : loadingMethod === item.method ? "Redirecting..." : `Pay with ${item.title}`}
                </button>
                {!isPro && simulationEnabled ? (
                  <button
                    type="button"
                    onClick={() => void handleSimulate(item.method)}
                    disabled={loadingMethod === `simulate-${item.method}`}
                    className="mt-2 w-full rounded-lg border border-line px-3 py-2 text-sm text-slate-300 disabled:opacity-60"
                  >
                    {loadingMethod === `simulate-${item.method}` ? "Simulating..." : "Simulate success (local dev)"}
                  </button>
                ) : null}
              </div>
            ))}
          </div>

          {!simulationEnabled ? null : (
            <p className="text-xs text-amber-300">
              Dev simulation is enabled in frontend env.
            </p>
          )}
          {error ? <p className="text-sm text-rose-300">{error}</p> : null}
          {message ? <p className="text-sm text-emerald-300">{message}</p> : null}
        </div>
      </div>
    </section>
  );
}
