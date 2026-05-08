import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Billing from "./pages/Billing";
import Chat from "./pages/Chat";
import Login from "./pages/Login";
import { logout, me } from "./lib/api";

function ProtectedRoute({ user, children }) {
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function AppLayout({ user, onLogout, onRefreshUser }) {
  return (
    <div className="app-shell min-h-screen">
      <Routes>
        <Route path="/chat" element={<Chat user={user} onLogout={onLogout} />} />
        <Route path="/billing" element={<Billing user={user} onRefreshUser={onRefreshUser} onLogout={onLogout} />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </div>
  );
}

export default function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  async function refreshMe() {
    try {
      const currentUser = await me();
      setUser(currentUser);
      return currentUser;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshMe();
  }, []);

  async function handleLogout() {
    await logout();
    setUser(null);
    navigate("/login");
  }

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-300">Loading workspace...</div>;
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to={user ? "/chat" : "/login"} replace />} />
      <Route path="/login" element={user ? <Navigate to="/chat" replace /> : <Login onAuthed={refreshMe} />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute user={user}>
            <AppLayout user={user} onLogout={handleLogout} onRefreshUser={refreshMe} />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
