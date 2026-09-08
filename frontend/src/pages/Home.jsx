import React, {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Link,
  useNavigate,
} from "react-router-dom";

import {
  getComplaints,
  getParticipatoryBudgetingPriorities,
} from "../services/apiClient";

import "./Home.css";
import logo from "../assets/Logo.png";

import { useAuth } from "../context/AuthContext";

import RegionModal, {
  getSavedRegion,
  saveRegion,
} from "../components/RegionModal";


function Home() {

  // ============================================================
  // AUTH
  // ============================================================

  const {
    user,
    isAuthenticated,
    logout,
  } = useAuth();

  const navigate = useNavigate();


  async function handleLogout() {
    try {
      await logout();
      navigate("/");
    } catch (error) {
      console.error("Logout failed:", error);
    }
  }


  // ============================================================
  // REGION
  // ============================================================

  const [activeRegion, setActiveRegion] = useState(
    () => getSavedRegion()
  );

  const [showRegionChanger, setShowRegionChanger] =
    useState(false);


  // ============================================================
  // COMPLAINTS
  // ============================================================

  const [complaints, setComplaints] = useState([]);

  const [complaintsLoading, setComplaintsLoading] =
    useState(true);


  // ============================================================
  // PARTICIPATORY BUDGETING
  // ============================================================

  const [
    participatoryPriorities,
    setParticipatoryPriorities,
  ] = useState([]);

  const [
    prioritiesLoading,
    setPrioritiesLoading,
  ] = useState(true);

  const [
    prioritiesError,
    setPrioritiesError,
  ] = useState("");


  // ============================================================
  // ANIMATED STATS
  // ============================================================

  const [animatedStats, setAnimatedStats] = useState({
    total: 0,
    supports: 0,
    active: 0,
    resolved: 0,
  });


  // ============================================================
  // LOAD COMPLAINTS
  // ============================================================

  useEffect(() => {

    let mounted = true;

    async function loadComplaints() {

      try {

        setComplaintsLoading(true);

        /*
         * IMPORTANT:
         *
         * getComplaints(state, region)
         *
         * Therefore activeRegion MUST be passed
         * as the second argument.
         */
        const data = await getComplaints(
          null,
          activeRegion
        );

        if (!mounted) {
          return;
        }

        setComplaints(
          Array.isArray(data)
            ? data
            : []
        );

      } catch (error) {

        console.error(
          "Failed to load complaints:",
          error
        );

        if (mounted) {
          setComplaints([]);
        }

      } finally {

        if (mounted) {
          setComplaintsLoading(false);
        }

      }
    }

    loadComplaints();

    return () => {
      mounted = false;
    };

  }, [activeRegion]);


  // ============================================================
  // LOAD PARTICIPATORY PRIORITIES
  // ============================================================

  useEffect(() => {

    let mounted = true;

    async function loadPriorities() {

      try {

        setPrioritiesLoading(true);
        setPrioritiesError("");

        const data =
          await getParticipatoryBudgetingPriorities();

        if (!mounted) {
          return;
        }

        setParticipatoryPriorities(
          Array.isArray(data)
            ? data
            : []
        );

      } catch (error) {

        console.error(
          "Failed to load participatory budgeting priorities:",
          error
        );

        if (mounted) {

          setParticipatoryPriorities([]);

          setPrioritiesError(
            error?.message ||
            "Unable to load community priorities."
          );

        }

      } finally {

        if (mounted) {
          setPrioritiesLoading(false);
        }

      }

    }

    loadPriorities();

    return () => {
      mounted = false;
    };

  }, []);


  // ============================================================
  // COMPLAINT STATISTICS
  // ============================================================

  const stats = useMemo(() => {

    const total = complaints.length;

    const resolved =
      complaints.filter(
        (complaint) =>
          String(
            complaint.status || ""
          ).toLowerCase() === "resolved"
      ).length;

    const active =
      complaints.filter(
        (complaint) =>
          String(
            complaint.status || ""
          ).toLowerCase() !== "resolved"
      ).length;

    const supports =
      complaints.reduce(
        (sum, complaint) => {

          const value =
            complaint.supports ??
            complaint.votes ??
            0;

          return sum + Number(value || 0);

        },
        0
      );

    return {
      total,
      supports,
      active,
      resolved,
    };

  }, [complaints]);


  // ============================================================
  // ANIMATE STATISTICS
  // ============================================================

  useEffect(() => {

    const duration = 900;

    const startTime = performance.now();

    let animationFrame;

    function animate(currentTime) {

      const elapsed =
        currentTime - startTime;

      const progress =
        Math.min(
          elapsed / duration,
          1
        );

      const eased =
        1 - Math.pow(
          1 - progress,
          3
        );

      setAnimatedStats({

        total: Math.round(
          stats.total * eased
        ),

        supports: Math.round(
          stats.supports * eased
        ),

        active: Math.round(
          stats.active * eased
        ),

        resolved: Math.round(
          stats.resolved * eased
        ),

      });

      if (progress < 1) {

        animationFrame =
          requestAnimationFrame(
            animate
          );

      }

    }

    animationFrame =
      requestAnimationFrame(
        animate
      );

    return () => {
      cancelAnimationFrame(
        animationFrame
      );
    };

  }, [
    stats.total,
    stats.supports,
    stats.active,
    stats.resolved,
  ]);


  // ============================================================
  // PARTICIPATORY BUDGETING DATA
  // ============================================================

  const budgetPriorities = useMemo(() => {

    if (
      !Array.isArray(
        participatoryPriorities
      )
    ) {
      return [];
    }

    const normalized =
      participatoryPriorities
        .map((issue) => {

          const supports =
            Number(
              issue?.supports ?? 0
            );

          return {
            ...issue,
            supports:
              Number.isFinite(supports)
                ? Math.max(
                    0,
                    supports
                  )
                : 0,
          };

        })
        .filter(
          (issue) =>
            issue &&
            issue.id !== undefined
        );

    normalized.sort(
      (a, b) =>
        Number(b.supports) -
        Number(a.supports)
    );

    const totalSupports =
      normalized.reduce(
        (sum, issue) =>
          sum +
          Number(
            issue.supports || 0
          ),
        0
      );

    if (totalSupports <= 0) {

      return normalized
        .slice(0, 3)
        .map((issue) => ({
          ...issue,
          percentage: 0,
        }));

    }

    return normalized
      .slice(0, 3)
      .map((issue) => {

        const percentage =
          Math.round(
            (
              Number(
                issue.supports || 0
              ) /
              totalSupports
            ) * 100
          );

        return {
          ...issue,
          percentage:
            Math.min(
              100,
              Math.max(
                0,
                percentage
              )
            ),
        };

      });

  }, [
    participatoryPriorities,
  ]);


  // ============================================================
  // RECENT COMPLAINTS
  // ============================================================

  const recentComplaints = useMemo(() => {

    return [...complaints]
      .sort(
        (a, b) =>
          Number(b.id ?? 0) -
          Number(a.id ?? 0)
      )
      .slice(0, 3);

  }, [complaints]);


  // ============================================================
  // HELPERS
  // ============================================================

  function getStatusClass(status) {

    const normalized =
      String(
        status || ""
      ).toLowerCase();

    if (
      normalized === "resolved"
    ) {
      return "status-resolved";
    }

    if (
      normalized === "in progress" ||
      normalized === "in-progress"
    ) {
      return "status-progress";
    }

    return "status-pending";
  }


  function getPriority(priority) {

    const value =
      Number(
        priority ?? 0
      );

    if (value >= 5) {
      return "High";
    }

    if (value >= 2) {
      return "Medium";
    }

    return "Low";
  }


  function getPriorityClass(priority) {

    const value =
      Number(
        priority ?? 0
      );

    if (value >= 5) {
      return "priority-high";
    }

    if (value >= 2) {
      return "priority-medium";
    }

    return "priority-low";
  }


  // ============================================================
  // RENDER
  // ============================================================

  return (

    <div className="home-page">

      <div
        className="home-ambient-glow"
        aria-hidden="true"
      >
        <span />
        <span />
        <span />
      </div>


      {/* ======================================================
          REGION MODAL
      ====================================================== */}

      {showRegionChanger && (

        <RegionModal
          onComplete={(region) => {

            if (region !== undefined) {

              saveRegion(region);

              setActiveRegion(region);

            }

            setShowRegionChanger(false);

          }}
        />

      )}


      {/* ======================================================
          NAVIGATION
      ====================================================== */}

      <header className="home-navbar">

        <Link
          to="/"
          className="home-logo"
          aria-label="CivicPulse home"
        >

          <span className="logo-mark">

            <img
              src={logo}
              alt="CivicPulse"
            />

          </span>

          <span className="logo-copy">

            <strong>
              CivicPulse
            </strong>

            <span>
              Your Voice. Your City.
            </span>

          </span>

        </Link>


        <nav
          className="home-nav"
          aria-label="Main navigation"
        >

          <Link
            to="/"
            className="active"
          >
            Home
          </Link>

          <Link to="/complaints">
            Complaints
          </Link>

          <Link to="/participatory-budgeting">
            Participatory Budgeting
          </Link>

          <a href="#about-us">
            About Us
          </a>

          <Link to="/admin">
            Admin
          </Link>

        </nav>


        <div className="nav-actions">

          {isAuthenticated ? (

            <>

              <Link to="/profile" className="nav-user" style={{ textDecoration: "none", cursor: "pointer" }} title="View your reported complaints">

                <span className="nav-user-dot">
                  ●
                </span>

                Hi, {user?.name}

              </Link>


              <button
                type="button"
                className="nav-region-pin"
                onClick={() =>
                  setShowRegionChanger(true)
                }
                title={
                  activeRegion
                    ? `Region: ${activeRegion}`
                    : "Set your region"
                }
              >
                📍
              </button>


              <button
                type="button"
                className="nav-login logout-button"
                onClick={handleLogout}
              >
                Log Out
              </button>

            </>

          ) : (

            <Link
              to="/auth"
              className="nav-login"
            >
              Login
            </Link>

          )}


          <Link
            to="/complaints"
            className="nav-report-button"
          >
            Report an Issue

            <span>
              →
            </span>

          </Link>

        </div>

      </header>


      <main>

        {/* ======================================================
    PREMIUM HERO
====================================================== */}

<section className="hero-section">

  {/* ==================================================
      HERO BACKGROUND DECORATION
  ================================================== */}

  <div
    className="hero-orb hero-orb-one"
    aria-hidden="true"
  />

  <div
    className="hero-orb hero-orb-two"
    aria-hidden="true"
  />

  <div
    className="hero-grid"
    aria-hidden="true"
  />


  {/* ==================================================
      HERO CONTENT
  ================================================== */}

  <div className="hero-content">

    <div className="hero-eyebrow">

      <span className="eyebrow-dot"></span>

      <span>
        Citizen-powered civic platform
      </span>

      <span className="eyebrow-live">
        LIVE
      </span>

    </div>


    <div className="hero-kicker">
      YOUR COMMUNITY. YOUR VOICE.
    </div>


    <h1 className="hero-title">

      Your Voice.

      <br />

      <span>
        Your City.
      </span>

      <br />

      <strong>
        Your Impact.
      </strong>

    </h1>


    <div className="hero-title-line">
      <span></span>
    </div>


    <p className="hero-description">

      CivicPulse gives citizens a clearer way to
      report local problems, support existing issues,
      and help communities identify the priorities
      that deserve attention.

    </p>


    {/* ==================================================
        HERO ACTIONS
    ================================================== */}

    <div className="hero-actions">

      <Link
        to="/complaints"
        className="primary-button hero-primary-button"
      >

        <span className="button-icon">
          +
        </span>

        <span>
          Report an Issue
        </span>

        <span
          className="button-arrow"
          aria-hidden="true"
        >
          →
        </span>

      </Link>


      <Link
        to="/participatory-budgeting"
        className="secondary-button hero-secondary-button"
      >

        <span>
          Explore Community Priorities
        </span>

        <span
          className="button-arrow"
          aria-hidden="true"
        >
          →
        </span>

      </Link>

    </div>


    {/* ==================================================
        HERO TRUST
    ================================================== */}

    <div className="hero-trust">

      <span className="trust-check">
        ✓
      </span>

      <span>
        Report
      </span>

      <span className="trust-separator">
        •
      </span>

      <span>
        Support
      </span>

      <span className="trust-separator">
        •
      </span>

      <span>
        Prioritize
      </span>

      <span className="trust-separator">
        •
      </span>

      <span>
        Resolve
      </span>

    </div>


    {/* ==================================================
        HERO MINI STATS
    ================================================== */}

    <div className="hero-mini-stats">

      <div className="hero-mini-stat">

        <span className="hero-mini-number">
          {animatedStats.total}
        </span>

        <span className="hero-mini-label">
          Issues reported
        </span>

      </div>


      <div className="hero-mini-divider"></div>


      <div className="hero-mini-stat">

        <span className="hero-mini-number">
          {animatedStats.supports}
        </span>

        <span className="hero-mini-label">
          Community supports
        </span>

      </div>


      <div className="hero-mini-divider"></div>


      <div className="hero-mini-stat">

        <span className="hero-mini-number">
          {animatedStats.resolved}
        </span>

        <span className="hero-mini-label">
          Resolved
        </span>

      </div>

    </div>

  </div>


  {/* ==================================================
      COMMUNITY PULSE VISUAL
  ================================================== */}

  <div className="hero-visual">

    {/* floating notification */}

    <div className="hero-floating-card hero-floating-card-one">

      <div className="floating-card-icon">
        ✓
      </div>

      <div className="floating-card-copy">

        <strong>
          Community support
        </strong>

        <span>
          Growing visibility
        </span>

      </div>

      <span className="floating-card-trend">
        +24%
      </span>

    </div>


    {/* floating issue count */}

    <div className="hero-floating-card hero-floating-card-two">

      <span className="floating-number">
        {animatedStats.active}
      </span>

      <div>

        <strong>
          Active issues
        </strong>

        <span>
          Need attention
        </span>

      </div>

    </div>


    {/* ==================================================
        MAIN PULSE CARD
    ================================================== */}

    <div className="pulse-card">

      {/* card glow */}

      <div
        className="pulse-card-glow"
        aria-hidden="true"
      />


      {/* ==================================================
          HEADER
      ================================================== */}

      <div className="pulse-header">

        <div>

          <div className="pulse-title-row">

            <span className="pulse-eyebrow">
              COMMUNITY PULSE
            </span>

            <span className="pulse-live">

              <span></span>

              Live

            </span>

          </div>


          <h2>
            What needs attention?
          </h2>


          <p>
            A live snapshot of civic activity
            in your community.
          </p>

        </div>

      </div>


      {/* ==================================================
          MAP
      ================================================== */}

      <div
        className="pulse-map"
        aria-label="Illustration of civic issues"
      >

        <div
          className="map-scan"
          aria-hidden="true"
        />


        <div
          className="map-grid"
          aria-hidden="true"
        />


        {/* roads */}

        <div className="map-road road-one"></div>
        <div className="map-road road-two"></div>
        <div className="map-road road-three"></div>
        <div className="map-road road-four"></div>
        <div className="map-road road-five"></div>


        {/* blocks */}

        <div className="map-block block-one"></div>
        <div className="map-block block-two"></div>
        <div className="map-block block-three"></div>
        <div className="map-block block-four"></div>
        <div className="map-block block-five"></div>
        <div className="map-block block-six"></div>


        {/* additional buildings */}

        <div className="map-building building-one"></div>
        <div className="map-building building-two"></div>
        <div className="map-building building-three"></div>


        {/* ==================================================
            MARKER 01
        ================================================== */}

        <div className="pulse-marker marker-one">

          <div className="marker-icon">
            <span>
              01
            </span>
          </div>

          <div className="marker-label">

            <strong>
              Street Lighting
            </strong>

            <span>
              Needs attention
            </span>

          </div>

          <div className="marker-pulse"></div>

        </div>


        {/* ==================================================
            MARKER 02
        ================================================== */}

        <div className="pulse-marker marker-two">

          <div className="marker-icon">
            <span>
              02
            </span>
          </div>

          <div className="marker-label">

            <strong>
              Road Maintenance
            </strong>

            <span>
              Reported nearby
            </span>

          </div>

          <div className="marker-pulse"></div>

        </div>


        {/* ==================================================
            MARKER 03
        ================================================== */}

        <div className="pulse-marker marker-three">

          <div className="marker-icon">
            <span>
              03
            </span>
          </div>

          <div className="marker-label">

            <strong>
              Water Supply
            </strong>

            <span>
              Needs attention
            </span>

          </div>

          <div className="marker-pulse"></div>

        </div>


        {/* ==================================================
            MAP CENTER PULSE
        ================================================== */}

        <div
          className="map-center-pulse"
          aria-hidden="true"
        >

          <span></span>

        </div>

      </div>


      {/* ==================================================
          METRICS
      ================================================== */}

      <div className="pulse-metrics">

        <div className="pulse-metric">

          <div className="metric-icon metric-green">
            <span>
              01
            </span>
          </div>

          <div className="metric-content">

            <strong>
              {animatedStats.active}
            </strong>

            <span>
              Active issues
            </span>

            <small>
              Currently requiring attention
            </small>

          </div>

          <span className="metric-arrow">
            ↗
          </span>

        </div>


        <div className="pulse-metric">

          <div className="metric-icon metric-blue">
            <span>
              02
            </span>
          </div>

          <div className="metric-content">

            <strong>
              {animatedStats.supports}
            </strong>

            <span>
              Community supports
            </span>

            <small>
              Citizen engagement
            </small>

          </div>

          <span className="metric-arrow">
            ↗
          </span>

        </div>

      </div>


      {/* ==================================================
          BOTTOM MESSAGE
      ================================================== */}

      <div className="pulse-bottom">

        <div className="pulse-bottom-check">
          ✓
        </div>

        <div>

          <strong>
            Stronger together
          </strong>

          <span>
            Collective support creates visibility.
          </span>

        </div>


        <div
          className="pulse-bars"
          aria-hidden="true"
        >

          <span></span>
          <span></span>
          <span></span>
          <span></span>
          <span></span>

        </div>

      </div>

    </div>

  </div>

</section>


        {/* ====================================================
            STATS
        ==================================================== */}

        <section
          className="stats-section"
          aria-label="CivicPulse statistics"
        >

          <div className="stat-card">

            <span className="stat-number">
              {animatedStats.total}
            </span>

            <div className="stat-copy">

              <strong>
                Issues Reported
              </strong>

              <span>
                Problems raised by citizens
              </span>

            </div>

          </div>


          <div className="stat-card">

            <span className="stat-number">
              {animatedStats.supports}
            </span>

            <div className="stat-copy">

              <strong>
                Community Supports
              </strong>

              <span>
                Citizen engagement
              </span>

            </div>

          </div>


          <div className="stat-card">

            <span className="stat-number">
              {animatedStats.active}
            </span>

            <div className="stat-copy">

              <strong>
                Active Issues
              </strong>

              <span>
                Currently requiring attention
              </span>

            </div>

          </div>


          <div className="stat-card stat-highlight">

            <span className="stat-number">
              {animatedStats.resolved}
            </span>

            <div className="stat-copy">

              <strong>
                Issues Resolved
              </strong>

              <span>
                Successfully closed
              </span>

            </div>

          </div>

        </section>


        {/* ======================================================
    HOW IT WORKS — PREMIUM
====================================================== */}

<section className="how-section">

  {/* Decorative background */}
  <div
    className="how-bg-orb how-bg-orb-one"
    aria-hidden="true"
  />

  <div
    className="how-bg-orb how-bg-orb-two"
    aria-hidden="true"
  />

  <div
    className="how-grid-pattern"
    aria-hidden="true"
  />

  {/* ==================================================
      SECTION INTRO
  ================================================== */}

  <div className="how-intro">

    <div className="how-intro-label">

      <span className="how-label-line"></span>

      <span className="section-label">
        HOW CIVICPULSE WORKS
      </span>

    </div>


    <div className="how-intro-main">

      <div className="how-heading-wrap">

        <span className="how-heading-number">
          01 — 04
        </span>

        <h2>
          From citizen
          <br />
          voice to
          <span> civic action.</span>
        </h2>

      </div>


      <div className="how-intro-copy">

        <p>
          CivicPulse turns everyday local problems
          into visible community priorities — creating
          a clearer path from reporting an issue to
          meaningful civic action.
        </p>


        <div className="how-intro-note">

          <span className="how-note-dot"></span>

          <span>
            Simple for citizens. Clear for communities.
          </span>

        </div>

      </div>

    </div>

  </div>


  {/* ==================================================
      PROCESS
  ================================================== */}

  <div className="steps-wrapper">

    {/* Connecting line */}
    <div
      className="steps-connector"
      aria-hidden="true"
    >
      <span></span>
    </div>


    <div className="steps-grid">


      {/* ==================================================
          STEP 01
      ================================================== */}

      <article className="step-card step-card-report">

        <div className="step-card-glow"></div>


        <div className="step-top">

          <span className="step-number">
            01
          </span>

          <span className="step-category">
            IDENTIFY
          </span>

        </div>


        <div className="step-icon-wrap">

          <div className="step-icon">
            <span>+</span>
          </div>

          <span className="step-icon-ring"></span>

        </div>


        <div className="step-content">

          <h3>
            Report
          </h3>

          <p>
            See a problem in your community?
            Tell people what is happening and
            where it needs attention.
          </p>

        </div>


        <div className="step-footer">

          <span>
            Start a civic conversation
          </span>

          <span className="step-arrow">
            ↗
          </span>

        </div>

      </article>


      {/* ==================================================
          STEP 02
      ================================================== */}

      <article className="step-card step-card-support">

        <div className="step-card-glow"></div>


        <div className="step-top">

          <span className="step-number">
            02
          </span>

          <span className="step-category">
            ENGAGE
          </span>

        </div>


        <div className="step-icon-wrap">

          <div className="step-icon">
            <span>↑</span>
          </div>

          <span className="step-icon-ring"></span>

        </div>


        <div className="step-content">

          <h3>
            Support
          </h3>

          <p>
            Find existing complaints and add
            your support instead of creating
            unnecessary duplicates.
          </p>

        </div>


        <div className="step-footer">

          <span>
            Add your community voice
          </span>

          <span className="step-arrow">
            ↗
          </span>

        </div>

      </article>


      {/* ==================================================
          STEP 03
      ================================================== */}

      <article className="step-card step-card-prioritize">

        <div className="step-card-glow"></div>


        <div className="step-top">

          <span className="step-number">
            03
          </span>

          <span className="step-category">
            PRIORITIZE
          </span>

        </div>


        <div className="step-icon-wrap">

          <div className="step-icon">
            <span>≡</span>
          </div>

          <span className="step-icon-ring"></span>

        </div>


        <div className="step-content">

          <h3>
            Prioritize
          </h3>

          <p>
            Community support helps recurring
            problems rise above individual reports
            and become visible priorities.
          </p>

        </div>


        <div className="step-footer">

          <span>
            Surface what matters most
          </span>

          <span className="step-arrow">
            ↗
          </span>

        </div>

      </article>


      {/* ==================================================
          STEP 04
      ================================================== */}

      <article className="step-card step-card-resolve">

        <div className="step-card-glow"></div>


        <div className="step-top">

          <span className="step-number">
            04
          </span>

          <span className="step-category">
            ACTION
          </span>

        </div>


        <div className="step-icon-wrap">

          <div className="step-icon">
            <span>✓</span>
          </div>

          <span className="step-icon-ring"></span>

        </div>


        <div className="step-content">

          <h3>
            Resolve
          </h3>

          <p>
            Authorized authorities can track
            progress and update the status of
            reported civic issues.
          </p>

        </div>


        <div className="step-footer">

          <span>
            Move toward meaningful action
          </span>

          <span className="step-arrow">
            ↗
          </span>

        </div>

      </article>

    </div>

  </div>


  {/* ==================================================
      BOTTOM STATEMENT
  ================================================== */}

  <div className="how-bottom">

    <div className="how-bottom-line"></div>

    <div className="how-bottom-content">

      <span className="how-bottom-mark">
        CIVICPULSE
      </span>

      <p>
        A problem becomes more visible when
        a community speaks together.
      </p>

    </div>

    <div className="how-bottom-line"></div>

  </div>

</section>


        {/* ====================================================
            ABOUT
        ==================================================== */}

        <section
          className="about-section"
          id="about-us"
        >

          <div className="about-inner">

            <div className="about-intro">

              <span className="section-label">
                ABOUT CIVICPULSE
              </span>

              <h2>
                Giving citizens
                <br />
                a stronger voice
                <br />
                in their city.
              </h2>

              <div className="about-rule"></div>

              <p className="about-intro-note">
                A clearer connection between citizens,
                civic problems, community priorities,
                and meaningful action.
              </p>

            </div>


            <div className="about-description">

              <p className="about-lead">
                CivicPulse is a citizen-powered civic
                platform designed to make reporting local
                problems and participating in community
                priorities simpler and more transparent.
              </p>

              <p>
                Instead of scattering similar complaints
                across different channels, CivicPulse brings
                civic issues together in one shared platform.
              </p>

              <p>
                Citizens can report issues, discover existing
                complaints, and support problems affecting
                their community.
              </p>

              <p>
                Authorized authorities can then track those
                issues and update their progress, creating
                a clearer connection between citizens,
                civic problems, and action.
              </p>

            </div>

          </div>


          <div className="about-principles">

            <article className="about-principle">

              <span className="about-principle-number">
                01
              </span>

              <div>

                <h3>
                  Built for Communities
                </h3>

                <p>
                  Focused on real local problems
                  experienced every day.
                </p>

              </div>

            </article>


            <article className="about-principle">

              <span className="about-principle-number">
                02
              </span>

              <div>

                <h3>
                  Powered by Citizens
                </h3>

                <p>
                  Report, support, participate,
                  and help shape community priorities.
                </p>

              </div>

            </article>


            <article className="about-principle">

              <span className="about-principle-number">
                03
              </span>

              <div>

                <h3>
                  Transparent & Connected
                </h3>

                <p>
                  A shared view of civic issues
                  and their progress.
                </p>

              </div>

            </article>


            <article className="about-principle">

              <span className="about-principle-number">
                04
              </span>

              <div>

                <h3>
                  Focused on Impact
                </h3>

                <p>
                  Moving communities from identifying
                  problems toward meaningful action.
                </p>

              </div>

            </article>

          </div>

        </section>


        {/* ====================================================
            PARTICIPATORY BUDGETING
        ==================================================== */}

        <section className="budget-section">

          <div className="budget-content">

            <span className="section-label">
              PARTICIPATORY BUDGETING
            </span>

            <h2>
              Help decide what
              <br />
              deserves attention first.
            </h2>

            <p>
              Citizens can help prioritize recurring civic
              problems. Final budget allocation and
              implementation remain with the authorized
              authority.
            </p>

            <Link
              to="/participatory-budgeting"
              className="primary-button"
            >
              Explore Participatory Budgeting

              <span>
                →
              </span>

            </Link>

          </div>


          <div className="budget-visual">

            <div className="budget-card">

              <div className="budget-card-header">

                <div>

                  <span>
                    COMMUNITY PRIORITIES
                  </span>

                  <h3>
                    What matters most?
                  </h3>

                </div>

                <div className="budget-period">
                  2026
                </div>

              </div>


              {prioritiesLoading ? (

                <div className="budget-loading">
                  Loading community priorities...
                </div>

              ) : prioritiesError ? (

                <div className="budget-empty">
                  Unable to load community priorities.
                </div>

              ) : budgetPriorities.length === 0 ? (

                <div className="budget-empty">

                  <strong>
                    No community priorities yet.
                  </strong>

                  <p>
                    Submit your priorities and help
                    shape the community's focus.
                  </p>

                </div>

              ) : (

                budgetPriorities.map(
                  (issue, index) => {

                    const title =
                      issue.title ||
                      issue.description ||
                      issue.category ||
                      "Civic Issue";

                    const percentage =
                      Number(
                        issue.percentage || 0
                      );

                    return (

                      <div
                        className="budget-item"
                        key={
                          issue.id ??
                          `priority-${index}`
                        }
                        style={{
                          "--item-delay":
                            `${index * 90}ms`,
                        }}
                      >

                        <div className="budget-item-header">

                          <span>
                            {title}
                          </span>

                          <strong>
                            {percentage}%
                          </strong>

                        </div>

                        <div
                          className="budget-progress"
                          aria-label={
                            `${title}: ${percentage}%`
                          }
                        >

                          <span
                            style={{
                              width:
                                `${percentage}%`,
                            }}
                          />

                        </div>

                      </div>

                    );

                  }
                )

              )}


              <div className="budget-card-footer">

                <span className="budget-footer-dot">
                  ●
                </span>

                Community input helps surface
                real priorities.

              </div>

            </div>

          </div>

        </section>


        {/* ====================================================
            RECENT COMMUNITY ACTIVITY
        ==================================================== */}

        <section className="recent-section">

          <div className="section-header">

            <div>

              <span className="section-label">
                COMMUNITY ACTIVITY
              </span>

              <h2>
                Recent civic issues
              </h2>

              <p>
                See what citizens are reporting
                across the community.
              </p>

            </div>


            <Link
              to="/complaints"
              className="view-all-link"
            >
              View all complaints

              <span>
                →
              </span>

            </Link>

          </div>


          {complaintsLoading ? (

            <div className="loading-state">

              <span className="loading-spinner"></span>

              Loading community activity...

            </div>

          ) : recentComplaints.length === 0 ? (

            <div className="empty-state">

              <span className="empty-number">
                01
              </span>

              <h3>
                No complaints yet
              </h3>

              <p>
                Be the first person to report
                a civic issue in your community.
              </p>

              <Link
                to="/complaints"
                className="primary-button"
              >
                Report an Issue

                <span>
                  →
                </span>

              </Link>

            </div>

          ) : (

            <div className="recent-grid">

              {recentComplaints.map(
                (complaint, index) => {

                  const statusClass =
                    getStatusClass(
                      complaint.status
                    );

                  const priority =
                    getPriority(
                      complaint.priority
                    );

                  const priorityClass =
                    getPriorityClass(
                      complaint.priority
                    );

                  const supportCount =
                    Number(
                      complaint.supports ??
                      complaint.votes ??
                      0
                    );

                  return (

                    <article
                      className="recent-card"
                      key={
                        complaint.id ??
                        `complaint-${index}`
                      }
                      style={{
                        "--card-delay":
                          `${index * 80}ms`,
                      }}
                    >

                      <div className="recent-card-top">

                        <span className="complaint-id">
                          #{complaint.id}
                        </span>

                        <span
                          className={
                            `status ${statusClass}`
                          }
                        >

                          <span></span>

                          {complaint.status ||
                            "Pending"}

                        </span>

                      </div>


                      <h3>
                        {complaint.description ||
                          "Civic issue reported"}
                      </h3>


                      <p className="recent-location">

                        {complaint.category ||
                          "General Issue"}

                        <span>
                          •
                        </span>

                        {complaint.location ||
                          "Location unavailable"}

                      </p>


                      <div className="recent-card-footer">

                        <span>
                          👍 {supportCount} supports
                        </span>

                        <span
                          className={
                            `recent-priority ${priorityClass}`
                          }
                        >
                          Priority: {priority}
                        </span>

                      </div>

                    </article>

                  );

                }
              )}

            </div>

          )}

        </section>


        {/* ====================================================
            FINAL CTA
        ==================================================== */}

        <section className="final-cta">

          <div className="final-cta-content">

            <span className="section-label">
              MAKE YOUR VOICE COUNT
            </span>

            <h2>
              See a problem?
              <br />
              Don't just walk past it.
            </h2>

            <p>
              Report it. Let your community support it.
              Help make your city better.
            </p>

          </div>


          <Link
            to="/complaints"
            className="primary-button final-cta-button"
          >
            Report an Issue

            <span>
              →
            </span>

          </Link>

        </section>

      </main>


      {/* ======================================================
          FOOTER
      ====================================================== */}

      <footer className="home-footer">

        <div className="footer-brand">

          <Link
            to="/"
            className="home-logo"
          >

            <span className="logo-mark">

              <img
                src={logo}
                alt="CivicPulse"
              />

            </span>

            <span className="logo-copy">

              <strong>
                CivicPulse
              </strong>

              <span>
                Your Voice. Your City.
              </span>

            </span>

          </Link>


          <p>
            A citizen-powered platform for
            transparent and participatory
            civic action.
          </p>

        </div>


        <div className="footer-links">

          <div>

            <strong>
              Platform
            </strong>

            <Link to="/">
              Home
            </Link>

            <Link to="/complaints">
              Complaints
            </Link>

            <Link to="/participatory-budgeting">
              Participatory Budgeting
            </Link>

            <a href="#about-us">
              About Us
            </a>

            <Link to="/auth">
              Login / Register
            </Link>

          </div>


          <div>

            <strong>
              Management
            </strong>

            <Link to="/admin">
              Admin Dashboard
            </Link>

          </div>

        </div>

      </footer>

    </div>

  );
}


export default Home;