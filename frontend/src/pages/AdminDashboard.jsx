import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";

import {
  getComplaints,
  getComplaintEvidence,
  updateComplaintStatus,
  getRegions,
  getParticipatoryBudgetingPriorities,
  getApiUrl,
} from "../services/apiClient";
import { useAuth } from "../context/AuthContext";

import "./AdminDashboard.css";

const API_URL = getApiUrl();

function AdminDashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/");
  }

  const [complaints, setComplaints] = useState([]);
  const [evidence, setEvidence] = useState({});

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatingId, setUpdatingId] = useState(null);

  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");

  // Filters
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [priorityFilter, setPriorityFilter] = useState("All");

  // Last refresh time
  const [lastUpdated, setLastUpdated] = useState(null);

  // Region filter
  const [adminRegion, setAdminRegion] = useState("");
  const [regionOpen, setRegionOpen] = useState(false);
  const [regions, setRegions] = useState([]);
  const regionDropdownRef = useRef(null);

  // Participatory Budgeting
  const [pbPriorities, setPbPriorities] = useState([]);
  const [pbLoading, setPbLoading] = useState(true);

  useEffect(() => {
    loadComplaints();
    loadRegions();
    loadPBPriorities();
  }, []);

  // Re-fetch complaints when region filter changes
  useEffect(() => {
    loadComplaints();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adminRegion]);

  // Close region dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (
        regionDropdownRef.current &&
        !regionDropdownRef.current.contains(e.target)
      ) {
        setRegionOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  /*
   * =========================================================
   * LOAD COMPLAINTS
   * =========================================================
   */

  async function loadComplaints(showRefreshing = false) {
    try {
      if (showRefreshing) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setMessage("");
      setMessageType("");

      const data = await getComplaints(adminRegion || null, null);

      const complaintData = Array.isArray(data) ? data : [];

      /*
       * Highest priority first.
       * If priority is equal, older complaint ID appears first.
       */
      const sortedComplaints = [...complaintData].sort(
        (a, b) => {
          const priorityA = Number(a.priority ?? 0);
          const priorityB = Number(b.priority ?? 0);

          if (priorityB !== priorityA) {
            return priorityB - priorityA;
          }

          return Number(a.id) - Number(b.id);
        }
      );

      setComplaints(sortedComplaints);

      /*
       * Load evidence for every complaint.
       *
       * Promise.allSettled ensures that if one complaint
       * has missing/broken evidence, the entire dashboard
       * does not fail.
       */
      const evidenceResults = await Promise.allSettled(
        sortedComplaints.map(async (complaint) => {
          const result = await getComplaintEvidence(
            complaint.id
          );

          return {
            complaintId: complaint.id,
            evidence: result?.evidence ?? [],
          };
        })
      );

      const evidenceMap = {};

      evidenceResults.forEach((result) => {
        if (result.status === "fulfilled") {
          evidenceMap[result.value.complaintId] =
            result.value.evidence;
        }
      });

      setEvidence(evidenceMap);
      setLastUpdated(new Date());
    } catch (error) {
      console.error(
        "Failed to load complaints:",
        error
      );

      setMessage(
        "Unable to load complaints. Please try again."
      );

      setMessageType("error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  /*
   * =========================================================
   * LOAD REGIONS (for admin region filter)
   * =========================================================
   */

  async function loadRegions() {
    try {
      const data = await getRegions();
      setRegions(data?.regions || []);
    } catch {
      setRegions([]);
    }
  }


  /*
   * =========================================================
   * LOAD PARTICIPATORY BUDGETING PRIORITIES
   * =========================================================
   */

  async function loadPBPriorities() {
    try {
      setPbLoading(true);
      const data = await getParticipatoryBudgetingPriorities();
      const sorted = Array.isArray(data)
        ? [...data].sort(
            (a, b) =>
              Number(b.supports ?? 0) - Number(a.supports ?? 0)
          )
        : [];
      setPbPriorities(sorted);
    } catch {
      setPbPriorities([]);
    } finally {
      setPbLoading(false);
    }
  }

  /*
   * =========================================================
   * STATUS UPDATE
   * =========================================================
   */

  async function handleStatusChange(
    complaintId,
    newStatus
  ) {
    try {
      setUpdatingId(complaintId);

      setMessage("");
      setMessageType("");

      await updateComplaintStatus(
        complaintId,
        newStatus
      );

      setMessage(
        `Complaint #${complaintId} status updated to ${newStatus}.`
      );

      setMessageType("success");

      await loadComplaints(true);
    } catch (error) {
      console.error(
        "Failed to update complaint status:",
        error
      );

      setMessage(
        "Failed to update complaint status. Please try again."
      );

      setMessageType("error");
    } finally {
      setUpdatingId(null);
    }
  }

  /*
   * =========================================================
   * SUMMARY COUNTS
   * =========================================================
   */

  const totalComplaints = complaints.length;

  const pendingComplaints = complaints.filter(
    (complaint) =>
      complaint.status === "Pending"
  ).length;

  const inProgressComplaints = complaints.filter(
    (complaint) =>
      complaint.status === "In Progress"
  ).length;

  const resolvedComplaints = complaints.filter(
    (complaint) =>
      complaint.status === "Resolved"
  ).length;

  const highPriorityComplaints =
    complaints.filter(
      (complaint) =>
        Number(complaint.priority ?? 0) >= 5 &&
        complaint.status !== "Resolved"
    ).length;

  const totalSupports = complaints.reduce(
    (total, complaint) =>
      total + Number(complaint.votes ?? 0),
    0
  );

  /*
   * =========================================================
   * CATEGORY OPTIONS
   * =========================================================
   */

  const categoryOptions = useMemo(() => {
    const categories = complaints
      .map((complaint) =>
        complaint.category?.trim()
      )
      .filter(Boolean);

    return [...new Set(categories)].sort();
  }, [complaints]);

  /*
   * =========================================================
   * FILTERED COMPLAINTS
   * =========================================================
   */

  const [categoryFilter, setCategoryFilter] =
    useState("All");

  const filteredComplaints = useMemo(() => {
    const normalizedSearch =
      searchTerm.trim().toLowerCase();

    return complaints.filter((complaint) => {
      const description =
        complaint.description?.toLowerCase() || "";

      const category =
        complaint.category?.toLowerCase() || "";

      const location =
        complaint.location?.toLowerCase() || "";

      const status =
        complaint.status || "";

      const priority =
        Number(complaint.priority ?? 0);

      const matchesSearch =
        !normalizedSearch ||
        description.includes(normalizedSearch) ||
        category.includes(normalizedSearch) ||
        location.includes(normalizedSearch) ||
        String(complaint.id).includes(
          normalizedSearch
        );

      const matchesStatus =
        statusFilter === "All" ||
        status === statusFilter;

      const matchesCategory =
        categoryFilter === "All" ||
        complaint.category === categoryFilter;

      let matchesPriority = true;

      if (priorityFilter === "High") {
        matchesPriority = priority >= 5;
      }

      if (priorityFilter === "Medium") {
        matchesPriority =
          priority >= 2 && priority < 5;
      }

      if (priorityFilter === "Low") {
        matchesPriority = priority < 2;
      }

      return (
        matchesSearch &&
        matchesStatus &&
        matchesCategory &&
        matchesPriority
      );
    });
  }, [
    complaints,
    searchTerm,
    statusFilter,
    categoryFilter,
    priorityFilter,
  ]);

  /*
   * =========================================================
   * PRIORITY HELPERS
   * =========================================================
   */

  function getPriorityLabel(priority = 0) {
    const value = Number(priority ?? 0);

    if (value >= 5) {
      return "High";
    }

    if (value >= 2) {
      return "Medium";
    }

    return "Low";
  }

  function getPriorityClass(priority = 0) {
    const value = Number(priority ?? 0);

    if (value >= 5) {
      return "priority-label priority-high";
    }

    if (value >= 2) {
      return "priority-label priority-medium";
    }

    return "priority-label priority-low";
  }

  /*
   * =========================================================
   * STATUS HELPERS
   * =========================================================
   */

  function getStatusClass(status) {
    if (status === "Resolved") {
      return "status status-resolved";
    }

    if (status === "In Progress") {
      return "status status-progress";
    }

    return "status status-pending";
  }

  /*
   * =========================================================
   * EVIDENCE HELPERS
   * =========================================================
   */

  function getEvidenceUrl(filePath) {
    if (!filePath) {
      return "";
    }

    if (/^https?:\/\//i.test(filePath)) {
      return filePath;
    }

    const cleanPath = String(filePath).replace(
      /^\/+/,
      ""
    );

    return `${API_URL}/${cleanPath}`;
  }

  function isImage(fileType, filePath) {
    if (
      fileType &&
      fileType.startsWith("image/")
    ) {
      return true;
    }

    const extension = filePath
      ?.split(".")
      .pop()
      ?.toLowerCase();

    return [
      "jpg",
      "jpeg",
      "png",
      "gif",
      "webp",
      "bmp",
      "svg",
    ].includes(extension);
  }

  /*
   * =========================================================
   * LAST UPDATED TEXT
   * =========================================================
   */

  function getLastUpdatedText() {
    if (!lastUpdated) {
      return "Loading...";
    }

    return lastUpdated.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  /*
   * =========================================================
   * LOADING SCREEN
   * =========================================================
   */

  if (loading) {
    return (
      <div className="admin-dashboard">
        <header className="admin-header">
          <div>
            <span className="page-label">
              CIVICPULSE · ADMINISTRATION
            </span>

            <h1>
              Civic issue command center.
            </h1>

            <p>
              Monitor reported issues, prioritize
              community needs, and track resolution
              progress from one place.
            </p>
          </div>
        </header>

        <section className="empty-state">
          <h2>
            Loading dashboard...
          </h2>

          <p>
            Fetching the latest community issues.
          </p>
        </section>
      </div>
    );
  }

  /*
   * =========================================================
   * MAIN DASHBOARD
   * =========================================================
   */

  return (
    <div className="admin-dashboard">

      {/* =====================================================
          HEADER
      ====================================================== */}

      <header className="admin-header">
        <div>
          <span className="page-label">
            CIVICPULSE · ADMINISTRATION
          </span>

          <h1>
            Civic issue command center.
          </h1>

          <p>
            Monitor reported issues, prioritize
            community needs, and track resolution
            progress from one place.
          </p>
        </div>

        <div className="admin-header-actions" style={{ position: "relative", zIndex: 100 }}>
          {user && (
            <span className="admin-header-user">
              Logged in as {user.name} (admin)
            </span>
          )}

          <Link
            to="/admin/map"
            className="admin-header-btn"
          >
            🗺️ View Map
          </Link>

          {/* Region Dropdown */}
          <div style={{ position: "relative" }} ref={regionDropdownRef}>
            <button
              type="button"
              onClick={() => setRegionOpen(!regionOpen)}
              className={`admin-header-btn ${adminRegion ? "admin-header-btn--active" : ""}`}
              aria-expanded={regionOpen}
              aria-haspopup="true"
            >
              <span>📍</span>
              <span>{adminRegion || "All States"}</span>
              <span style={{ fontSize: "0.75rem", opacity: 0.8 }}>▼</span>
            </button>

            {regionOpen && (
              <div className="admin-region-dropdown" role="menu">
                <div
                  className={`admin-region-item ${adminRegion === "" ? "admin-region-item--selected" : ""}`}
                  onClick={() => {
                    setAdminRegion("");
                    setRegionOpen(false);
                  }}
                  role="menuitem"
                >
                  <span>All States</span>
                  {adminRegion === "" && <span>✓</span>}
                </div>

                {regions.map((r) => (
                  <div
                    key={r}
                    className={`admin-region-item ${adminRegion === r ? "admin-region-item--selected" : ""}`}
                    onClick={() => {
                      setAdminRegion(r);
                      setRegionOpen(false);
                    }}
                    role="menuitem"
                  >
                    <span>{r}</span>
                    {adminRegion === r && <span>✓</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={handleLogout}
            className="admin-header-btn admin-header-btn--logout"
          >
            Log Out
          </button>
        </div>
      </header>


      {/* =====================================================
          SYSTEM STATUS
      ====================================================== */}

      <section className="system-status">

        <div className="system-status-left">

          <span className="status-dot"></span>

          <strong>
            System Active
          </strong>

          <span>
            Community reporting is live
          </span>

        </div>

        <div className="system-status-meta">

          <span>
            Last refreshed:{" "}
            <strong>
              {getLastUpdatedText()}
            </strong>
          </span>

          <span>
            Community supports:{" "}
            <strong>
              {totalSupports}
            </strong>
          </span>

          <span>
            High priority:{" "}
            <strong>
              {highPriorityComplaints}
            </strong>
          </span>

        </div>

      </section>


      {/* =====================================================
          SUCCESS / ERROR MESSAGE
      ====================================================== */}

      {message && (
        <div
          className={`message ${messageType}`}
          role="alert"
        >
          {message}
        </div>
      )}


      {/* =====================================================
          DASHBOARD SUMMARY
      ====================================================== */}

      <section className="dashboard-summary">

        {/* TOTAL */}

        <article className="summary-card">

          <div className="summary-icon">
            ▣
          </div>

          <strong>
            Total Issues
          </strong>

          <h2>
            {totalComplaints}
          </h2>

          <p>
            All reported complaints
          </p>

        </article>


        {/* PENDING */}

        <article className="summary-card pending">

          <div className="summary-icon">
            ◷
          </div>

          <strong>
            Pending
          </strong>

          <h2>
            {pendingComplaints}
          </h2>

          <p>
            Awaiting action
          </p>

        </article>


        {/* IN PROGRESS */}

        <article className="summary-card progress">

          <div className="summary-icon">
            ↗
          </div>

          <strong>
            In Progress
          </strong>

          <h2>
            {inProgressComplaints}
          </h2>

          <p>
            Currently being handled
          </p>

        </article>


        {/* RESOLVED */}

        <article className="summary-card resolved">

          <div className="summary-icon">
            ✓
          </div>

          <strong>
            Resolved
          </strong>

          <h2>
            {resolvedComplaints}
          </h2>

          <p>
            Successfully completed
          </p>

        </article>


        {/* HIGH PRIORITY */}

        <article className="summary-card high-priority">

          <div className="summary-icon">
            !
          </div>

          <strong>
            High Priority
          </strong>

          <h2>
            {highPriorityComplaints}
          </h2>

          <p>
            Needs attention
          </p>

        </article>

      </section>


      {/* =====================================================
          COMPLAINT MANAGEMENT
      ====================================================== */}

      <section className="complaints-section">

        <div className="section-header">

          <div>

            <span className="section-label">
              OPERATIONS
            </span>

            <h2>
              Complaint Management
            </h2>

            <p className="section-description">
              High-priority unresolved issues are
              automatically surfaced first.
            </p>

          </div>

          <span className="complaint-count">
            {filteredComplaints.length}{" "}
            {filteredComplaints.length === 1
              ? "visible issue"
              : "visible issues"}
          </span>

        </div>


        {/* ===================================================
            FILTERS
        ==================================================== */}

        <div className="complaint-filters">

          {/* SEARCH */}

          <div className="search-wrapper">

            <span>
              ⌕
            </span>

            <input
              type="text"
              value={searchTerm}
              placeholder="Search issues, categories, locations..."
              onChange={(event) =>
                setSearchTerm(
                  event.target.value
                )
              }
              aria-label="Search complaints"
            />

          </div>


          {/* STATUS */}

          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(
                event.target.value
              )
            }
            aria-label="Filter by status"
          >

            <option value="All">
              All statuses
            </option>

            <option value="Pending">
              Pending
            </option>

            <option value="In Progress">
              In Progress
            </option>

            <option value="Resolved">
              Resolved
            </option>

          </select>


          {/* PRIORITY */}

          <select
            value={priorityFilter}
            onChange={(event) =>
              setPriorityFilter(
                event.target.value
              )
            }
            aria-label="Filter by priority"
          >

            <option value="All">
              All priorities
            </option>

            <option value="High">
              High priority
            </option>

            <option value="Medium">
              Medium priority
            </option>

            <option value="Low">
              Low priority
            </option>

          </select>


          {/* CATEGORY */}

          <select
            value={categoryFilter}
            onChange={(event) =>
              setCategoryFilter(
                event.target.value
              )
            }
            aria-label="Filter by category"
          >

            <option value="All">
              All categories
            </option>

            {categoryOptions.map(
              (category) => (
                <option
                  key={category}
                  value={category}
                >
                  {category}
                </option>
              )
            )}

          </select>

        </div>


        {/* ===================================================
            REFRESH CONTROL
        ==================================================== */}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: "18px",
          }}
        >

          <button
            type="button"
            onClick={() =>
              loadComplaints(true)
            }
            disabled={refreshing}
            style={{
              border: "1px solid #dce9e4",
              background: "#ffffff",
              color: "#155c49",
              padding: "9px 15px",
              borderRadius: "10px",
              fontFamily: "inherit",
              fontSize: "12px",
              fontWeight: 700,
              cursor: refreshing
                ? "default"
                : "pointer",
              opacity: refreshing
                ? 0.65
                : 1,
            }}
          >
            {refreshing
              ? "Refreshing..."
              : "↻ Refresh"}
          </button>

        </div>


        {/* ===================================================
            NO COMPLAINTS
        ==================================================== */}

        {complaints.length === 0 ? (

          <div className="empty-state">

            <h3>
              No complaints available
            </h3>

            <p>
              There are currently no complaints
              to manage.
            </p>

          </div>

        ) : filteredComplaints.length === 0 ? (

          <div className="empty-state">

            <h3>
              No matching issues
            </h3>

            <p>
              Try changing your search or
              filter selections.
            </p>

          </div>

        ) : (

          /* =================================================
             COMPLAINT LIST
          ================================================== */

          filteredComplaints.map(
            (complaint) => {

              const complaintEvidence =
                evidence[complaint.id] ?? [];

              const priority =
                Number(
                  complaint.priority ?? 0
                );

              const isHighPriority =
                priority >= 5 &&
                complaint.status !==
                  "Resolved";

              return (
                <article
                  key={complaint.id}
                  className={`admin-complaint-card ${
                    isHighPriority
                      ? "high-priority"
                      : ""
                  }`}
                >

                  {/* ========================================
                      TOP
                  ========================================= */}

                  <div className="complaint-top">

                    <span className="complaint-id">
                      Complaint #{complaint.id}
                    </span>

                    <span
                      className={getStatusClass(
                        complaint.status
                      )}
                    >
                      {complaint.status}
                    </span>

                  </div>


                  {/* ========================================
                      HIGH PRIORITY INDICATOR
                  ========================================= */}

                  {isHighPriority && (
                    <div
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                        marginBottom: "12px",
                        color: "#a64c1a",
                        fontSize: "11px",
                        fontWeight: 800,
                      }}
                    >
                      <span>
                        !
                      </span>

                      <span>
                        High priority issue
                      </span>

                      <span
                        style={{
                          fontWeight: 500,
                          color: "#8d6b58",
                        }}
                      >
                        This unresolved complaint
                        requires attention.
                      </span>
                    </div>
                  )}


                  {/* ========================================
                      DESCRIPTION
                  ========================================= */}

                  <h3>
                    {complaint.description ||
                      "No description provided."}
                  </h3>


                  {/* ========================================
                      INFORMATION
                  ========================================= */}

                  <div className="complaint-info">

                    <strong>
                      Category
                    </strong>

                    <span>
                      {complaint.category ||
                        "Not specified"}
                    </span>

                  </div>


                  <div className="complaint-info">

                    <strong>
                      Location
                    </strong>

                    <span>
                      {complaint.location ||
                        "Not specified"}
                    </span>

                  </div>


                  <div className="complaint-info">

                    <strong>
                      Language
                    </strong>

                    <span>
                      {complaint.language ===
                      "hi"
                        ? "Hindi"
                        : "English"}
                    </span>

                  </div>


                  <div className="complaint-info">

                    <strong>
                      Community Support
                    </strong>

                    <span>
                      {complaint.votes ?? 0}{" "}
                      supports
                    </span>

                  </div>


                  <div className="complaint-info">

                    <strong>
                      Priority
                    </strong>

                    <span
                      className={getPriorityClass(
                        priority
                      )}
                    >
                      {getPriorityLabel(
                        priority
                      )}
                    </span>

                    <span>
                      Score {priority}
                    </span>

                  </div>


                  {/* ========================================
                      EVIDENCE
                  ========================================= */}

                  {complaintEvidence.length >
                    0 && (

                    <div className="evidence-section">

                      <h4>
                        Evidence
                      </h4>

                      <div className="evidence-list">

                        {complaintEvidence.map(
                          (item) => {

                            const evidenceUrl =
                              item.file_url ||
                              getEvidenceUrl(
                                item.file_path
                              );

                            if (
                              !evidenceUrl
                            ) {
                              return null;
                            }

                            return (
                              <div
                                key={item.id}
                                className="evidence-item"
                              >

                                {isImage(
                                  item.file_type,
                                  item.file_path
                                ) ? (

                                  <a
                                    href={
                                      evidenceUrl
                                    }
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    <img
                                      src={
                                        evidenceUrl
                                      }
                                      alt={`Evidence for complaint #${complaint.id}`}
                                      className="evidence-image"
                                    />
                                  </a>

                                ) : (

                                  <a
                                    href={
                                      evidenceUrl
                                    }
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="evidence-link"
                                  >
                                    View Evidence
                                  </a>

                                )}

                              </div>
                            );
                          }
                        )}

                      </div>

                    </div>
                  )}


                  {/* ========================================
                      STATUS CONTROL
                  ========================================= */}

                  <div className="status-section">

                    <label
                      htmlFor={`status-${complaint.id}`}
                    >
                      Update status
                    </label>

                    <select
                      id={`status-${complaint.id}`}
                      className="status-select"
                      value={
                        complaint.status ||
                        "Pending"
                      }
                      disabled={
                        updatingId ===
                        complaint.id
                      }
                      onChange={(event) =>
                        handleStatusChange(
                          complaint.id,
                          event.target.value
                        )
                      }
                    >

                      <option value="Pending">
                        Pending
                      </option>

                      <option value="In Progress">
                        In Progress
                      </option>

                      <option value="Resolved">
                        Resolved
                      </option>

                    </select>

                    {updatingId ===
                      complaint.id && (
                      <small>
                        Updating status...
                      </small>
                    )}

                  </div>

                </article>
              );
            }
          )
        )}

      </section>

      {/* =====================================================
          PARTICIPATORY BUDGETING PANEL
      ====================================================== */}
      <section className="complaints-section pb-admin-section" style={{ marginTop: "40px" }}>
        <div className="section-header">
          <div>
            <span className="section-label">COMMUNITY PRIORITIES</span>
            <h2>Participatory Budgeting</h2>
            <p className="section-description">
              Top civic issues prioritized by citizen votes.
            </p>
          </div>
        </div>

        <div className="pb-admin-list">
          {pbLoading ? (
            <div className="complaints-empty">Loading priorities...</div>
          ) : pbPriorities.length === 0 ? (
            <div className="complaints-empty">No participatory budgeting votes yet.</div>
          ) : (
            pbPriorities.map((issue, index) => {
              const maxSupports = pbPriorities[0]?.supports || 1;
              const percentage = Math.round((issue.supports / maxSupports) * 100);

              return (
                <article key={issue.id} className="pb-admin-card" style={{
                  background: "white",
                  border: "1px solid var(--cp-border)",
                  borderRadius: "12px",
                  padding: "20px",
                  marginBottom: "16px",
                  display: "flex",
                  gap: "20px",
                  alignItems: "flex-start"
                }}>
                  <div className="pb-rank" style={{
                    fontSize: "1.5rem",
                    fontWeight: "bold",
                    color: index === 0 ? "#f59e0b" : index === 1 ? "#94a3b8" : index === 2 ? "#b45309" : "#64748b",
                    minWidth: "40px",
                    textAlign: "center"
                  }}>
                    #{index + 1}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                      <h3 style={{ margin: 0, fontSize: "1.1rem" }}>{issue.category}</h3>
                      <span style={{ fontWeight: "bold", color: "var(--cp-green-dark)" }}>{issue.supports} votes</span>
                    </div>
                    <p style={{ margin: "0 0 12px 0", color: "var(--cp-text-light)", fontSize: "0.95rem" }}>
                      {issue.description}
                    </p>
                    <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
                      <span className="complaint-meta">📍 {issue.location}</span>
                      <span className={`complaint-status ${getStatusClass(issue.status)}`}>{issue.status}</span>
                    </div>
                    {/* Progress Bar */}
                    <div style={{
                      width: "100%",
                      height: "8px",
                      background: "var(--cp-background)",
                      borderRadius: "4px",
                      overflow: "hidden"
                    }}>
                      <div style={{
                        height: "100%",
                        width: `${percentage}%`,
                        background: "var(--cp-green)",
                        borderRadius: "4px",
                        transition: "width 0.5s ease"
                      }}></div>
                    </div>
                  </div>
                </article>
              );
            })
          )}
        </div>
      </section>

    </div>
  );
}

export default AdminDashboard;
