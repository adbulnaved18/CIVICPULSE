import React from "react";
import { Navigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function SecurityIllustration() {
  return (
    <svg
      width="390"
      height="300"
      viewBox="0 0 390 300"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* Soft background circle */}
      <circle cx="195" cy="140" r="105" fill="#F0FAF6" />
      <circle cx="195" cy="140" r="88" fill="#E7F7F0" />

      {/* Decorative dots */}
      <circle cx="88" cy="75" r="4" fill="#B8DED0" />
      <circle cx="302" cy="70" r="4" fill="#B8DED0" />
      <circle cx="312" cy="170" r="3" fill="#C8E5DA" />
      <circle cx="76" cy="180" r="3" fill="#C8E5DA" />

      {/* Decorative crosses */}
      <path
        d="M98 38L106 46M106 38L98 46"
        stroke="#71B99F"
        strokeWidth="3"
        strokeLinecap="round"
      />

      <path
        d="M294 58L302 66M302 58L294 66"
        stroke="#71B99F"
        strokeWidth="3"
        strokeLinecap="round"
      />

      {/* Left plant */}
      <path
        d="M105 245C113 218 130 195 151 183"
        stroke="#62B99A"
        strokeWidth="7"
        strokeLinecap="round"
      />

      <path
        d="M119 220C98 213 87 198 89 181C108 184 123 196 128 211"
        fill="#75C5A5"
      />

      <path
        d="M128 204C125 181 133 164 148 155C157 175 151 194 137 211"
        fill="#4CAF83"
      />

      <path
        d="M108 238C91 235 79 225 75 211C92 208 108 218 116 231"
        fill="#8DD0B5"
      />

      {/* Right plant */}
      <path
        d="M285 245C278 218 261 195 240 183"
        stroke="#62B99A"
        strokeWidth="7"
        strokeLinecap="round"
      />

      <path
        d="M271 220C292 212 303 198 301 181C282 184 267 196 262 211"
        fill="#75C5A5"
      />

      <path
        d="M262 204C265 181 257 164 242 155C233 175 239 194 253 211"
        fill="#4CAF83"
      />

      <path
        d="M282 238C299 235 311 225 315 211C298 208 282 218 274 231"
        fill="#8DD0B5"
      />

      {/* Ground */}
      <ellipse
        cx="195"
        cy="245"
        rx="105"
        ry="12"
        fill="#B6DED0"
      />

      {/* Shield shadow */}
      <path
        d="M195 48L278 83V145C278 198 244 225 195 242C146 225 112 198 112 145V83L195 48Z"
        fill="#158B60"
        opacity="0.12"
      />

      {/* Main shield */}
      <path
        d="M195 45L275 79V140C275 192 242 219 195 237C148 219 115 192 115 140V79L195 45Z"
        fill="#35B978"
      />

      {/* Shield inner */}
      <path
        d="M195 64L255 90V140C255 177 232 199 195 215C158 199 135 177 135 140V90L195 64Z"
        fill="#159862"
      />

      {/* Shield highlight */}
      <path
        d="M195 64L135 90V140C135 177 158 199 195 215V64Z"
        fill="#49C684"
        opacity="0.45"
      />

      {/* Lock body */}
      <rect
        x="160"
        y="124"
        width="70"
        height="65"
        rx="10"
        fill="white"
      />

      {/* Lock shackle */}
      <path
        d="M173 125V107C173 94 183 84 195 84C207 84 217 94 217 107V125"
        stroke="white"
        strokeWidth="13"
        strokeLinecap="round"
      />

      {/* Keyhole */}
      <circle cx="195" cy="151" r="9" fill="#159862" />

      <path
        d="M195 158V174"
        stroke="#159862"
        strokeWidth="7"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ProtectedRoute({ children, requireAdmin = false }) {
  const { loading, isAuthenticated, isAdmin } = useAuth();

  if (loading) {
    return (
      <div className="protected-loading">
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }

  if (requireAdmin && !isAdmin) {
    return (
      <div className="access-denied-page">
        <div className="access-denied-content">

          {/* Illustration */}
          <div className="security-illustration">
            <SecurityIllustration />
          </div>

          {/* Heading */}
          <h1 className="access-denied-title">
            <span>Access</span>{" "}
            <strong>Denied</strong>
          </h1>

          <div className="access-denied-line" />

          <p className="access-denied-subtitle">
            You need an administrator account to view this page.
          </p>

          {/* Restricted Area */}
          <div className="restricted-box">
            <div className="restricted-icon">
              <svg
                width="42"
                height="42"
                viewBox="0 0 48 48"
                fill="none"
              >
                <path
                  d="M24 5L39 11V22C39 32 32.5 38 24 42C15.5 38 9 32 9 22V11L24 5Z"
                  stroke="#168B60"
                  strokeWidth="2.8"
                />
                <circle
                  cx="24"
                  cy="21"
                  r="5"
                  stroke="#168B60"
                  strokeWidth="2.5"
                />
                <path
                  d="M15.5 32C17.5 27.5 20 26 24 26C28 26 30.5 27.5 32.5 32"
                  stroke="#168B60"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                />
              </svg>
            </div>

            <div className="restricted-content">
              <h2>Restricted Area</h2>

              <p>
                This area is restricted to authorized CivicPulse
                administrators only. If you believe you should have
                access, contact your administrator.
              </p>
            </div>
          </div>

          {/* Buttons */}
          <div className="access-denied-actions">

            <Link
              to="/auth"
              className="access-login-button"
            >
              <span className="button-icon">→</span>
              Go to Login
            </Link>

            <Link
              to="/"
              className="access-home-button"
            >
              <span className="home-icon">⌂</span>
              Back to Home
            </Link>

          </div>

          {/* Footer divider */}
          <div className="access-footer-divider">
            <span></span>

            <div className="footer-shield">
              ♢
            </div>

            <span></span>
          </div>

          <div className="access-footer">
            <strong>CivicPulse</strong>
            <span>•</span>
            <span>Building better communities together</span>
          </div>

        </div>
      </div>
    );
  }

  return children;
}

export default ProtectedRoute;