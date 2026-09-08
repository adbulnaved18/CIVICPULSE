import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import logo from "../assets/Logo.png";
import { useAuth } from "../context/AuthContext";
import RegionModal, { getSavedRegion } from "./RegionModal";
import "./Navbar.css";

function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [activeRegion, setActiveRegion] = useState(() => getSavedRegion());
  const [showRegionChanger, setShowRegionChanger] = useState(false);

  async function handleLogout() {
    try {
      await logout();
      navigate("/");
    } catch (error) {
      console.error("Failed to log out:", error);
    }
  }

  return (
    <>
      <header className="home-navbar">
        <Link to="/" className="home-logo" aria-label="CivicPulse home">
          <span className="logo-mark">
            <img src={logo} alt="CivicPulse" />
          </span>
          <span className="logo-copy">
            <strong>CivicPulse</strong>
            <span>Your Voice. Your City.</span>
          </span>
        </Link>

        <nav className="home-nav" aria-label="Main navigation">
          <Link to="/" className={location.pathname === "/" ? "active" : ""}>
            Home
          </Link>
          <Link
            to="/complaints"
            className={location.pathname === "/complaints" ? "active" : ""}
          >
            Complaints
          </Link>
          <Link
            to="/participatory-budgeting"
            className={
              location.pathname === "/participatory-budgeting" ? "active" : ""
            }
          >
            Participatory Budgeting
          </Link>
          <a href="/#about-us">About Us</a>
          <Link
            to="/admin"
            className={location.pathname === "/admin" ? "active" : ""}
          >
            Admin
          </Link>
        </nav>

        <div className="nav-actions">
          {isAuthenticated ? (
            <>
              <Link
                to="/profile"
                className="nav-login"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  background: "rgba(16, 185, 129, 0.1)",
                  padding: "6px 14px",
                  borderRadius: "20px",
                  color: "#065f46",
                  fontWeight: 600,
                  textDecoration: "none",
                  transition: "all 0.2s ease",
                }}
                title="View your reported complaints"
              >
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    backgroundColor: "#10b981",
                    display: "inline-block",
                  }}
                />
                Hi, {user?.name}
              </Link>
              <button
                type="button"
                className="nav-region-pin"
                onClick={() => setShowRegionChanger(true)}
                title={activeRegion ? `Region: ${activeRegion}` : "Set your region"}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "1.2rem",
                  padding: "0 8px"
                }}
              >
                📍
              </button>
              <button
                type="button"
                className="nav-login logout-button"
                onClick={handleLogout}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  font: "inherit",
                }}
              >
                Log Out
              </button>
            </>
          ) : (
            <Link to="/auth" className="nav-login">
              Login
            </Link>
          )}

          <Link to="/complaints" className="nav-report-button">
            Report an Issue
            <span aria-hidden="true">→</span>
          </Link>
        </div>
      </header>

      {showRegionChanger && (
        <RegionModal
          onComplete={(region) => {
            setActiveRegion(region);
            setShowRegionChanger(false);
          }}
        />
      )}
    </>
  );
}

export default Navbar;
