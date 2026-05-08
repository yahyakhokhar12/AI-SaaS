import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, signup } from "../lib/api";
import NeuroVaultLogo from "../components/NeuroVaultLogo";

export default function Login({ onAuthed }) {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(email, password);
      }
      const authedUser = await onAuthed();
      if (!authedUser) {
        throw new Error("Session was not established. Please open the app on http://127.0.0.1:5173 and try again.");
      }
      navigate("/chat");
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto mt-10 grid w-full max-w-5xl gap-6 px-4 md:grid-cols-2">
      <div className="panel p-8">
        <NeuroVaultLogo subtitle="Zero-Trust AI Workspace" />
        <h1 className="mt-2 text-3xl font-semibold text-white">Private by design</h1>
        <ul className="mt-4 space-y-2 text-sm text-slate-300">
          <li>- Client-side AES-GCM encrypted chat history</li>
          <li>- No plaintext chat stored on server</li>
          <li>- Streaming assistant responses</li>
          <li>- Local conversations and memory</li>
        </ul>
      </div>

      <div className="panel p-8">
        <h2 className="text-xl font-semibold">{mode === "login" ? "Welcome back" : "Create account"}</h2>
        <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Email"
            required
            className="w-full rounded-lg border border-line bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent"
          />
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Password"
            minLength={8}
            required
            className="w-full rounded-lg border border-line bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium text-black disabled:opacity-60"
          >
            {loading ? "Please wait..." : mode === "login" ? "Login" : "Sign up"}
          </button>
        </form>

        <button
          type="button"
          className="mt-3 w-full rounded-lg border border-line px-3 py-2 text-sm text-slate-300"
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login");
            setError("");
          }}
        >
          {mode === "login" ? "Need an account? Sign up" : "Already have an account? Login"}
        </button>

        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
      </div>
    </section>
  );
}
