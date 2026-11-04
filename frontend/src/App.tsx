import './App.css'
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import BoardPage from "./pages/board";
import EntryPage from "./pages/entry";
import UserBoardsPage from "./pages/user_boards";

function AppRoutes() {
  const { user, loading } = useAuth();

  // Waits for the session to be restored, so the entry page doesn't flash.
  if (loading) return null;

  return (
    <Routes>
      <Route path="/" element={user ? <UserBoardsPage /> : <Navigate to="/login" replace />} />
      <Route path="/boards/:id" element={user ? <BoardPage /> : <Navigate to="/login" replace />} />
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <EntryPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
