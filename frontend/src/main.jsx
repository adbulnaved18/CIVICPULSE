import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import "./App.css";

import Home from "./pages/Home";
import SubmitComplaint from "./pages/SubmitComplaint";
import AdminDashboard from "./pages/AdminDashboard";
import AdminMap from "./pages/AdminMap";
import ParticipatoryBudgeting from "./pages/ParticipatoryBudgeting";
import Auth from "./pages/Auth";
import MyProfile from "./pages/MyProfile";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>

          {/* ================= HOME ================= */}
          <Route
            path="/"
            element={<Home />}
          />

          {/* ================= AUTH ================= */}
          <Route
            path="/auth"
            element={<Auth />}
          />

          {/* ================= COMPLAINTS (login required) ================= */}
          <Route
            path="/complaints"
            element={
              <ProtectedRoute>
                <SubmitComplaint />
              </ProtectedRoute>
            }
          />

          {/* ================= USER PROFILE / MY REPORTS ================= */}
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <MyProfile />
              </ProtectedRoute>
            }
          />

          {/* ================= PARTICIPATORY BUDGETING ================= */}
          <Route
            path="/participatory-budgeting"
            element={<ParticipatoryBudgeting />}
          />

          {/* ================= ADMIN (login + admin role required) ================= */}
          <Route
            path="/admin"
            element={
              <ProtectedRoute requireAdmin>
                <AdminDashboard />
              </ProtectedRoute>
            }
          />

          {/* ================= ADMIN MAP ================= */}
          <Route
            path="/admin/map"
            element={
              <ProtectedRoute requireAdmin>
                <AdminMap />
              </ProtectedRoute>
            }
          />

        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

ReactDOM.createRoot(
  document.getElementById("root")
).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
