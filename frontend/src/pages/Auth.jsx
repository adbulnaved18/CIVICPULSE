import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "./Auth.css";
import logo from "../assets/Logo.png";
import { useAuth } from "../context/AuthContext";
import RegionModal, { getSavedRegion } from "../components/RegionModal";

function Auth() {
  const { login, signup } = useAuth();
  const navigate = useNavigate();

  const [isLogin, setIsLogin] = useState(true);
  const [showRegionModal, setShowRegionModal] = useState(false);

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);

  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  /* =========================================================
     INPUT CHANGE
     ========================================================= */

  function handleChange(e) {
    const { name, value } = e.target;

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));

    setError("");
    setSuccess("");
  }

  /* =========================================================
     SUBMIT
     ========================================================= */

  function handleSubmit(e) {
    e.preventDefault();

    setError("");
    setSuccess("");

    /* -------------------------
       BASIC VALIDATION
       ------------------------- */

    if (!formData.email.trim() || !formData.password) {
      setError("Please fill in all required fields.");
      return;
    }

    if (!isLogin && !formData.name.trim()) {
      setError("Please enter your full name.");
      return;
    }

    if (!isLogin && formData.password.length < 6) {
      setError("Password must contain at least 6 characters.");
      return;
    }

    if (
      !isLogin &&
      formData.password !== formData.confirmPassword
    ) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);

    /* =======================================================
       LOGIN
       ======================================================= */

    if (isLogin) {
      login(formData.email, formData.password)
        .then((user) => {
          setSuccess("Login successful. Redirecting...");

          /*
           * ADMIN
           */
          if (user?.role === "admin") {
            navigate("/admin");
            return;
          }

          /*
           * NORMAL USER
           */
          if (getSavedRegion()) {
            navigate("/");
          } else {
            setShowRegionModal(true);
          }
        })
        .catch((err) => {
          setError(
            err?.message ||
              "Unable to sign in. Please check your credentials."
          );

          setIsSubmitting(false);
        });
    }

    /* =======================================================
       SIGN UP
       ======================================================= */

    else {
      signup(
        formData.name.trim(),
        formData.email.trim(),
        formData.password
      )
        .then(() => {
          return login(
            formData.email.trim(),
            formData.password
          );
        })
        .then(() => {
          setSuccess(
            "Account created successfully. Welcome to CivicPulse!"
          );

          setShowRegionModal(true);
        })
        .catch((err) => {
          setError(
            err?.message ||
              "Unable to create your account. Please try again."
          );

          setIsSubmitting(false);
        });
    }
  }

  /* =========================================================
     SWITCH LOGIN / REGISTER
     ========================================================= */

  function switchMode() {
    setIsLogin((prev) => !prev);

    setError("");
    setSuccess("");

    setShowPassword(false);
    setShowConfirmPassword(false);

    setFormData({
      name: "",
      email: "",
      password: "",
      confirmPassword: "",
    });
  }

  /* =========================================================
     FORGOT PASSWORD
     ========================================================= */

  function handleForgotPassword() {
    setError("");

    setSuccess(
      "Password reset will be connected when authentication is added."
    );
  }

  /* =========================================================
     REGION COMPLETE
     ========================================================= */

  function handleRegionComplete() {
    setShowRegionModal(false);
    navigate("/");
  }

  /* =========================================================
     JSX
     ========================================================= */

  return (
    <main className="auth-page">

      {/* =====================================================
          REGION MODAL
          ===================================================== */}

      {showRegionModal && (
        <RegionModal
          onComplete={handleRegionComplete}
        />
      )}


      {/* =====================================================
          LEFT — LIVING CITY
          ===================================================== */}

      <section
        className="auth-visual"
        aria-label="CivicPulse introduction"
      >

        {/* Atmospheric background */}

        <div className="auth-grid" />
        <div className="auth-noise" />

        <div className="auth-glow auth-glow-one" />
        <div className="auth-glow auth-glow-two" />
        <div className="auth-glow auth-glow-three" />


        {/* Floating particles */}

        <span className="auth-orb auth-orb-one" />
        <span className="auth-orb auth-orb-two" />
        <span className="auth-orb auth-orb-three" />
        <span className="auth-orb auth-orb-four" />
        <span className="auth-orb auth-orb-five" />


        {/* Network lines */}

        <div className="city-network network-one" />
        <div className="city-network network-two" />
        <div className="city-network network-three" />


        {/* Civic nodes */}

        <div className="city-node node-one">
          <span />
        </div>

        <div className="city-node node-two">
          <span />
        </div>

        <div className="city-node node-three">
          <span />
        </div>

        <div className="city-node node-four">
          <span />
        </div>


        {/* =================================================
            BRAND
            ================================================= */}

        <Link
          to="/"
          className="auth-logo"
          aria-label="CivicPulse home"
        >

          <span className="auth-logo-mark">
            <img
              src={logo}
              alt="CivicPulse"
            />
          </span>

          <div>
            <h2>CivicPulse</h2>

            <span>
              Your Voice. Your City.
            </span>
          </div>

        </Link>


        {/* =================================================
            HERO
            ================================================= */}

        <div className="auth-visual-content">

          {/* Badge */}

          <div className="auth-badge">

            <span className="auth-badge-dot" />

            <span>
              🏛️ Citizen-powered civic platform
            </span>

            <span className="badge-live">
              LIVE
            </span>

          </div>


          {/* Main heading */}

          <h1 className="auth-main-title">

            Your voice
            <br />

            can shape
            <br />

            <span>
              your city.
            </span>

          </h1>


          {/* Description */}

          <p>
            Join CivicPulse to report local issues,
            support your community, and participate
            in building a better city together.
          </p>


          {/* =================================================
              FEATURES
              ================================================= */}

          <div className="auth-feature-list">

            <div className="auth-feature">

              <span className="feature-icon">
                <span>✓</span>
              </span>

              <div>
                <strong>
                  Report civic issues
                </strong>

                <small>
                  Make problems visible to your community.
                </small>
              </div>

              <span className="feature-arrow">
                ↗
              </span>

            </div>


            <div className="auth-feature">

              <span className="feature-icon">
                <span>✓</span>
              </span>

              <div>
                <strong>
                  Support existing complaints
                </strong>

                <small>
                  Show which issues matter most.
                </small>
              </div>

              <span className="feature-arrow">
                ↗
              </span>

            </div>


            <div className="auth-feature">

              <span className="feature-icon">
                <span>✓</span>
              </span>

              <div>
                <strong>
                  Participate in decisions
                </strong>

                <small>
                  Help prioritize your city's needs.
                </small>
              </div>

              <span className="feature-arrow">
                ↗
              </span>

            </div>

          </div>


          {/* =================================================
              LIVE STATUS
              ================================================= */}

          <div className="living-city-status">

            <span className="status-pulse" />

            <span>
              Community activity is live
            </span>

            <span className="status-line" />

            <span className="status-city">
              CIVICPULSE
            </span>

          </div>

        </div>


        {/* =================================================
            CITYSCAPE
            ================================================= */}

        <div
          className="cityscape"
          aria-hidden="true"
        >

          <div className="building building-1" />
          <div className="building building-2" />
          <div className="building building-3" />
          <div className="building building-4" />
          <div className="building building-5" />
          <div className="building building-6" />
          <div className="building building-7" />

        </div>


        {/* Footer */}

        <div className="auth-visual-footer">
          © 2026 CivicPulse
        </div>

      </section>


      {/* =====================================================
          RIGHT — AUTHENTICATION
          ===================================================== */}

      <section
        className={`auth-form-section ${
          isLogin ? "auth-mode-login" : "auth-mode-signup"
        }`}
      >

        <div className="form-ambient-glow" />
        <div className="form-particle form-particle-one" />
        <div className="form-particle form-particle-two" />


        <div className="auth-form-container">
          <div className="auth-card-glow" />
          <div className="auth-card-shine" />


          {/* =================================================
              MOBILE BRAND
              ================================================= */}

          <Link
            to="/"
            className="mobile-auth-logo"
            aria-label="CivicPulse home"
          >

            <span className="auth-logo-mark">

              <img
                src={logo}
                alt="CivicPulse"
              />

            </span>

            <strong>
              CivicPulse
            </strong>

          </Link>


          {/* =================================================
              HEADING
              ================================================= */}

          <div className="auth-heading">

            <div className="auth-section-label">

              <span className="label-line" />

              <span>
                {isLogin
                  ? "WELCOME BACK"
                  : "JOIN CIVICPULSE"}
              </span>

              <span className="label-dot" />

            </div>


            <h2
              key={isLogin ? "login-heading" : "signup-heading"}
            >
              {isLogin
                ? "Welcome back."
                : "Create your account."}
            </h2>


            <p>
              {isLogin
                ? "Sign in to continue to CivicPulse."
                : "Start making your voice count in your community."}
            </p>

          </div>


          {/* =================================================
              AUTH FORM
              ================================================= */}

          <form
            className="auth-form"
            onSubmit={handleSubmit}
            noValidate
          >


            {/* =================================================
                NAME — REGISTER ONLY
                ================================================= */}

            {!isLogin && (
              <div className="auth-field auth-field-animated">

                <label htmlFor="name">
                  Full Name
                </label>

                <div className="input-shell">

                  <span
                    className="input-icon"
                    aria-hidden="true"
                  >
                    ✦
                  </span>

                  <input
                    id="name"
                    name="name"
                    type="text"
                    placeholder="Enter your full name"
                    value={formData.name}
                    onChange={handleChange}
                    autoComplete="name"
                    required={!isLogin}
                  />

                </div>

              </div>
            )}


            {/* =================================================
                EMAIL
                ================================================= */}

            <div className="auth-field">

              <label htmlFor="email">
                Email Address
              </label>

              <div className="input-shell">

                <span
                  className="input-icon"
                  aria-hidden="true"
                >
                  @
                </span>

                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@example.com"
                  value={formData.email}
                  onChange={handleChange}
                  autoComplete="email"
                  required
                />

              </div>

            </div>


            {/* =================================================
                PASSWORD
                ================================================= */}

            <div className="auth-field">

              <div className="auth-label-row">

                <label htmlFor="password">
                  Password
                </label>

                {isLogin && (
                  <button
                    type="button"
                    className="forgot-password"
                    onClick={handleForgotPassword}
                  >
                    Forgot password?
                  </button>
                )}

              </div>


              <div className="input-shell">

                <span
                  className="input-icon"
                  aria-hidden="true"
                >
                  ◈
                </span>

                <input
                  id="password"
                  name="password"
                  type={
                    showPassword
                      ? "text"
                      : "password"
                  }
                  placeholder="Enter your password"
                  value={formData.password}
                  onChange={handleChange}
                  autoComplete={
                    isLogin
                      ? "current-password"
                      : "new-password"
                  }
                  required
                />


                <button
                  type="button"
                  className="password-toggle"
                  onClick={() =>
                    setShowPassword(
                      (prev) => !prev
                    )
                  }
                  aria-label={
                    showPassword
                      ? "Hide password"
                      : "Show password"
                  }
                  aria-pressed={showPassword}
                >
                  {showPassword
                    ? "◉"
                    : "◌"}
                </button>

              </div>

            </div>


            {/* =================================================
                CONFIRM PASSWORD
                ================================================= */}

            {!isLogin && (
              <div className="auth-field auth-field-animated">

                <label htmlFor="confirmPassword">
                  Confirm Password
                </label>

                <div className="input-shell">

                  <span
                    className="input-icon"
                    aria-hidden="true"
                  >
                    ◈
                  </span>

                  <input
                    id="confirmPassword"
                    name="confirmPassword"
                    type={
                      showConfirmPassword
                        ? "text"
                        : "password"
                    }
                    placeholder="Confirm your password"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    autoComplete="new-password"
                    required={!isLogin}
                  />

                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() =>
                      setShowConfirmPassword(
                        (prev) => !prev
                      )
                    }
                    aria-label={
                      showConfirmPassword
                        ? "Hide password"
                        : "Show password"
                    }
                    aria-pressed={
                      showConfirmPassword
                    }
                  >
                    {showConfirmPassword
                      ? "◉"
                      : "◌"}
                  </button>

                </div>

              </div>
            )}


            {/* =================================================
                ERROR
                ================================================= */}

            {error && (
              <div
                className="auth-message auth-error"
                role="alert"
              >

                <span className="message-icon">
                  !
                </span>

                <span>
                  {error}
                </span>

              </div>
            )}


            {/* =================================================
                SUCCESS
                ================================================= */}

            {success && (
              <div
                className="auth-message auth-success"
                role="status"
                aria-live="polite"
              >

                <span className="message-icon">
                  ✓
                </span>

                <span>
                  {success}
                </span>

              </div>
            )}


            {/* =================================================
                SUBMIT
                ================================================= */}

            <button
              type="submit"
              className={`auth-submit ${
                isSubmitting
                  ? "is-loading"
                  : ""
              }`}
              disabled={isSubmitting}
            >

              {isSubmitting ? (
                <>
                  <span
                    className="submit-spinner"
                    aria-hidden="true"
                  />

                  <span>
                    {isLogin
                      ? "Signing in..."
                      : "Creating account..."}
                  </span>
                </>
              ) : (
                <>
                  <span>
                    {isLogin
                      ? "Sign In"
                      : "Create Account"}
                  </span>

                  <span
                    className="auth-submit-arrow"
                    aria-hidden="true"
                  >
                    →
                  </span>
                </>
              )}

              <span
                className="button-shine"
                aria-hidden="true"
              />

              <span
                className="auth-submit-ripple"
                aria-hidden="true"
              />

            </button>

          </form>


          {/* =================================================
              DIVIDER
              ================================================= */}

          <div className="auth-divider">

            <span />
            <span>OR</span>
            <span />

          </div>


          {/* =================================================
              LOGIN / REGISTER SWITCH
              ================================================= */}

          <div className="auth-switch">

            <span>
              {isLogin
                ? "Don't have an account?"
                : "Already have an account?"}
            </span>

            <button
              type="button"
              onClick={switchMode}
            >
              {isLogin
                ? "Create one"
                : "Sign in"}
            </button>

          </div>


          {/* =================================================
              BACK TO HOME
              ================================================= */}

          <div className="auth-back">

            <Link to="/">
              <span aria-hidden="true">
                ←
              </span>

              Back to CivicPulse
            </Link>

          </div>


          {/* =================================================
              SECURITY
              ================================================= */}

          <div className="auth-security">

            <span className="security-lock">
              ✓
            </span>

            <span>
              Secure CivicPulse authentication
            </span>

          </div>

        </div>

      </section>

    </main>
  );
}

export default Auth;