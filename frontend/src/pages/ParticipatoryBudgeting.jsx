import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getParticipatoryBudgetingPriorities,
  submitParticipatoryPriorities,
} from "../services/apiClient";

import { getSavedRegion } from "../components/RegionModal";

import "./ParticipatoryBudgeting.css";
import Navbar from "../components/Navbar";

const CATEGORIES = [
  "All",
  "Drainage & Waterlogging",
  "Environment",
  "Footpaths & Pedestrian Safety",
  "Parks & Public Spaces",
  "Public Health & Hygiene",
  "Public Infrastructure",
  "Roads & Potholes",
  "Sanitation & Waste",
  "Stray Animals",
  "Streetlights & Electricity",
  "Traffic & Transportation",
  "Water Supply",
];

function ParticipatoryBudgeting() {
  const [issues, setIssues] = useState([]);
  const [selectedIssues, setSelectedIssues] = useState([]);

  const [selectedCategory, setSelectedCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [submitted, setSubmitted] = useState(false);

  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");

  // ============================================================
  // LOAD / REFRESH COMMUNITY PRIORITIES
  // ============================================================

  const loadPriorities = useCallback(
    async ({ silent = false, category = selectedCategory, search = searchQuery } = {}) => {
      try {
        if (silent) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }

        const savedState = getSavedRegion();
        const data =
          await getParticipatoryBudgetingPriorities(savedState, category, search);

        const normalizedData = Array.isArray(data)
          ? data
          : Array.isArray(data?.priorities)
          ? data.priorities
          : Array.isArray(data?.issues)
          ? data.issues
          : [];

        const cleanedData = normalizedData
          .map((issue) => ({
            ...issue,

            id: Number(issue?.id),

            supports: Number(
              issue?.supports ??
                issue?.support_count ??
                issue?.votes ??
                0
            ),

            priority: Number(
              issue?.priority ?? 0
            ),
          }))
          .filter((issue) =>
            Number.isInteger(issue.id)
          );

        setIssues(cleanedData);

        return cleanedData;
      } catch (error) {
        console.error(
          "Failed to load participatory budgeting priorities:",
          error
        );

        setIssues([]);

        if (!silent) {
          setMessage(
            error?.message ||
              "Unable to load community priorities. Please try again."
          );

          setMessageType("error");
        }

        return [];
      } finally {
        if (silent) {
          setRefreshing(false);
        } else {
          setLoading(false);
        }
      }
    },
    [selectedCategory, searchQuery]
  );

  useEffect(() => {
    loadPriorities();
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadPriorities({
        silent: true,
        category: selectedCategory,
        search: searchQuery,
      });
    }, 250);

    return () => clearTimeout(timer);
  }, [selectedCategory, searchQuery]);

  function handleCategorySelect(cat) {
    setSelectedCategory(cat);
  }

  function handleClearFilters() {
    setSelectedCategory("All");
    setSearchQuery("");
  }

  // ============================================================
  // SELECT / UNSELECT ISSUE
  // ============================================================

  function toggleIssue(issueId) {
    if (submitting) {
      return;
    }

    const numericIssueId = Number(issueId);

    setSubmitted(false);

    setSelectedIssues((previous) => {
      const alreadySelected =
        previous.includes(numericIssueId);

      if (alreadySelected) {
        setMessage("");
        setMessageType("");

        return previous.filter(
          (id) => id !== numericIssueId
        );
      }

      if (previous.length >= 3) {
        setMessage(
          "You can select a maximum of 3 civic issues."
        );

        setMessageType("warning");

        return previous;
      }

      setMessage("");
      setMessageType("");

      return [
        ...previous,
        numericIssueId,
      ];
    });
  }

  // ============================================================
  // SUBMIT PRIORITIES
  // ============================================================

  async function handleSubmit(event) {
    event.preventDefault();

    if (submitting) {
      return;
    }

    const cleanedSelectedIssues =
      selectedIssues
        .map((id) => Number(id))
        .filter((id) =>
          Number.isInteger(id)
        );

    if (cleanedSelectedIssues.length === 0) {
      setMessage(
        "Please select at least one civic issue before submitting."
      );

      setMessageType("warning");

      return;
    }

    if (cleanedSelectedIssues.length > 3) {
      setMessage(
        "You can select a maximum of 3 civic issues."
      );

      setMessageType("warning");

      return;
    }

    try {
      setSubmitting(true);
      setSubmitted(false);
      setMessage("");
      setMessageType("");

      // --------------------------------------------------------
      // 1. SUBMIT TO BACKEND
      // --------------------------------------------------------

      const result =
        await submitParticipatoryPriorities(
          cleanedSelectedIssues
        );

      // --------------------------------------------------------
      // 2. SHOW SUCCESS
      // --------------------------------------------------------

      setSubmitted(true);

      setMessage(
        result?.message ||
          "Your community priorities have been recorded successfully."
      );

      setMessageType("success");

      // --------------------------------------------------------
      // 3. VERY IMPORTANT:
      // FETCH FRESH DATA FROM BACKEND
      //
      // This updates:
      // - Total Supports
      // - Issue supports
      // - Ranking
      // - Progress percentages
      // - Community recommendation
      // --------------------------------------------------------

      await loadPriorities({
        silent: true,
      });

      // --------------------------------------------------------
      // 4. CLEAR USER SELECTION
      // --------------------------------------------------------

      setSelectedIssues([]);

    } catch (error) {
      console.error(
        "Failed to submit community priorities:",
        error
      );

      setSubmitted(false);

      const errorMessage =
        error?.message ||
        "Failed to submit your priorities. Please try again.";

      setMessage(errorMessage);
      setMessageType("error");
    } finally {
      setSubmitting(false);
    }
  }

  // ============================================================
  // MANUAL REFRESH
  // ============================================================

  async function handleRefresh() {
    if (refreshing || submitting) {
      return;
    }

    setMessage("");
    setMessageType("");

    await loadPriorities({
      silent: true,
    });
  }

  // ============================================================
  // RANK ISSUES
  // ============================================================

  const rankedIssues = useMemo(() => {
    return [...issues].sort((a, b) => {
      const supportsA = Number(
        a?.supports ?? 0
      );

      const supportsB = Number(
        b?.supports ?? 0
      );

      if (supportsB !== supportsA) {
        return supportsB - supportsA;
      }

      const priorityA = Number(
        a?.priority ?? 0
      );

      const priorityB = Number(
        b?.priority ?? 0
      );

      if (priorityB !== priorityA) {
        return priorityB - priorityA;
      }

      return (
        Number(a?.id ?? 0) -
        Number(b?.id ?? 0)
      );
    });
  }, [issues]);

  // ============================================================
  // TOTAL COMMUNITY SUPPORT
  // ============================================================

  const totalSupports = useMemo(() => {
    return issues.reduce(
      (total, issue) => {
        return (
          total +
          Number(issue?.supports ?? 0)
        );
      },
      0
    );
  }, [issues]);

  // ============================================================
  // TOP PRIORITY
  // ============================================================

  const topPriority =
    rankedIssues.length > 0
      ? rankedIssues[0]
      : null;

  // ============================================================
  // SUPPORT PERCENTAGE
  // ============================================================

  function getPercentage(supports) {
    const numericSupports = Number(
      supports ?? 0
    );

    if (
      totalSupports <= 0 ||
      numericSupports <= 0
    ) {
      return 0;
    }

    return Math.round(
      (numericSupports /
        totalSupports) *
        100
    );
  }

  // ============================================================
  // RANK CLASS
  // ============================================================

  function getRankClass(index) {
    if (index === 0) {
      return "rank rank-first";
    }

    if (index === 1) {
      return "rank rank-second";
    }

    if (index === 2) {
      return "rank rank-third";
    }

    return "rank";
  }

  // ============================================================
  // ISSUE TITLE
  // ============================================================

  function getIssueTitle(issue) {
    return (
      issue?.title ||
      issue?.description ||
      "Untitled civic issue"
    );
  }

  // ============================================================
  // ISSUE CATEGORY
  // ============================================================

  function getIssueCategory(issue) {
    return (
      issue?.category ||
      "General"
    );
  }

  // ============================================================
  // ISSUE LOCATION
  // ============================================================

  function getIssueLocation(issue) {
    return (
      issue?.location ||
      "Location not specified"
    );
  }

  // ============================================================
  // LOADING STATE
  // ============================================================

  if (loading) {
    return (
      <main className="participatory-budgeting">
        <section className="pb-loading-card">
          <div className="pb-loading-icon">
            <span />
          </div>

          <div>
            <span className="pb-eyebrow">
              CIVICPULSE
            </span>

            <h1>
              Participatory Budgeting
            </h1>

            <p>
              Loading the latest community
              priorities...
            </p>
          </div>
        </section>
      </main>
    );
  }

  // ============================================================
  // MAIN UI
  // ============================================================

  return (
    <main className="participatory-budgeting">
      <Navbar />

      {/* ======================================================
          HERO
      ====================================================== */}

      <header className="pb-hero">

        <div className="pb-hero-content">

          <span className="pb-hero-label">
            CIVICPULSE · COMMUNITY PARTICIPATION
          </span>

          <h1>
            Participatory
            <br />
            Budgeting
          </h1>

          <p>
            Help identify the civic issues that
            deserve attention first and make
            community priorities visible.
          </p>

        </div>

        <div
          className="pb-hero-decoration"
          aria-hidden="true"
        >
          <span />
          <span />
          <span />
        </div>

      </header>

      {/* ======================================================
          STATUS BAR
      ====================================================== */}

      <section className="pb-status-bar">

        <div className="pb-status-left">

          <span className="pb-live-dot" />

          <strong>
            Community priorities are live
          </strong>

          <span>
            Your input helps identify recurring
            civic needs.
          </span>

        </div>

        <div className="pb-status-right">

          <span>
            <strong>
              {issues.length}
            </strong>{" "}
            Issues
          </span>

          <span>
            <strong>
              {totalSupports}
            </strong>{" "}
            Supports
          </span>

          <button
            type="button"
            onClick={handleRefresh}
            disabled={
              refreshing ||
              submitting
            }
            className="pb-refresh-button"
          >
            {refreshing
              ? "Refreshing..."
              : "Refresh"}
          </button>

        </div>

      </section>

      {/* ======================================================
          MESSAGE
      ====================================================== */}

      {message && (
        <div
          className={`pb-message ${messageType}`}
          role="alert"
        >
          <span className="pb-message-icon">
            {messageType === "success"
              ? "✓"
              : messageType === "warning"
              ? "!"
              : "×"}
          </span>

          <span>
            {message}
          </span>
        </div>
      )}

      {/* ======================================================
          INTRODUCTION
      ====================================================== */}

      <section className="pb-intro-card">

        <div className="pb-intro-mark">
          <span>
            01
          </span>
        </div>

        <div className="pb-intro-content">

          <span className="pb-section-label">
            HOW IT WORKS
          </span>

          <h2>
            Your voice helps shape
            community priorities.
          </h2>

          <p>
            CivicPulse allows residents to identify
            and prioritize recurring civic problems.
            Your selection contributes to a community
            preference signal that can help authorities
            understand which issues need attention.
          </p>

          <p className="pb-disclaimer">
            Community priorities are advisory.
            Final budget allocation and implementation
            decisions remain with the authorized
            authority.
          </p>

        </div>

      </section>

      {/* ======================================================
          SEARCH & FILTER BY CATEGORY
      ====================================================== */}

      <section className="pb-filter-section">

        <div className="pb-filter-header">

          <div className="pb-filter-heading">
            <span className="pb-section-label">
              FILTER & SEARCH
            </span>
            <h2>Search by Category</h2>
            <p>
              Filter community priorities by civic category or search by keywords.
            </p>
          </div>

          {(selectedCategory !== "All" || searchQuery.trim() !== "") && (
            <button
              type="button"
              className="pb-reset-btn"
              onClick={handleClearFilters}
              aria-label="Reset all search and category filters"
            >
              Reset Filters
            </button>
          )}

        </div>

        <div className="pb-filter-controls">

          <div className="pb-search-container">
            <span className="pb-search-icon" aria-hidden="true">
              🔍
            </span>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search reports by title, category, or location..."
              className="pb-search-input"
              aria-label="Search reports by keyword"
            />
            {searchQuery && (
              <button
                type="button"
                className="pb-search-clear-btn"
                onClick={() => setSearchQuery("")}
                aria-label="Clear search input"
              >
                ✕
              </button>
            )}
          </div>

          <div className="pb-dropdown-container">
            <label htmlFor="pb-category-select" className="pb-dropdown-label">
              Category:
            </label>
            <select
              id="pb-category-select"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="pb-category-dropdown"
            >
              {CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat === "All" ? "All Categories" : cat}
                </option>
              ))}
            </select>
          </div>

        </div>

        {/* CATEGORY PILLS */}
        <div className="pb-category-chips-wrapper">
          <div className="pb-category-chips" role="tablist" aria-label="Quick Category Filter">
            {CATEGORIES.map((cat) => {
              const isActive = selectedCategory === cat;
              return (
                <button
                  key={cat}
                  type="button"
                  className={`pb-category-chip ${isActive ? "is-active" : ""}`}
                  onClick={() => handleCategorySelect(cat)}
                  role="tab"
                  aria-selected={isActive}
                >
                  {cat === "All" ? "All Categories" : cat}
                </button>
              );
            })}
          </div>
        </div>

        <div className="pb-filter-summary">
          <span>
            Showing <strong>{rankedIssues.length}</strong> {rankedIssues.length === 1 ? "issue" : "issues"}
            {selectedCategory !== "All" ? ` in ${selectedCategory}` : ""}
            {searchQuery.trim() ? ` matching "${searchQuery.trim()}"` : ""}
          </span>
        </div>

      </section>

      {/* ======================================================
          COMMUNITY SIGNAL
      ====================================================== */}

      <section className="pb-section">

        <div className="pb-section-header">

          <div>

            <span className="pb-section-label">
              COMMUNITY SIGNAL
            </span>

            <h2>
              Current Civic Priorities
            </h2>

            <p>
              Issues are ranked using current
              community support and priority signals.
            </p>

          </div>

          <div className="pb-stat-card">

            <strong>
              {totalSupports}
            </strong>

            <span>
              Total Supports
            </span>

          </div>

        </div>

        {rankedIssues.length === 0 ? (

          <div className="pb-empty-state">

            <div className="pb-empty-icon">
              —
            </div>

            <h3>
              {selectedCategory !== "All" || searchQuery.trim() !== ""
                ? "No matching civic issues found"
                : "No civic issues available"}
            </h3>

            <p>
              {selectedCategory !== "All" || searchQuery.trim() !== ""
                ? `No reports found for ${
                    selectedCategory !== "All" ? `category "${selectedCategory}"` : ""
                  }${selectedCategory !== "All" && searchQuery.trim() ? " and " : ""}${
                    searchQuery.trim() ? `keyword "${searchQuery.trim()}"` : ""
                  }. Try selecting another category or clearing filters.`
                : "Community priorities will appear here once civic complaints have been submitted."}
            </p>

            {(selectedCategory !== "All" || searchQuery.trim() !== "") && (
              <button
                type="button"
                className="pb-empty-reset-btn"
                onClick={handleClearFilters}
              >
                Clear Search & Filters
              </button>
            )}

          </div>

        ) : (

          <div className="pb-priority-list">

            {rankedIssues.map(
              (issue, index) => {

                const supports =
                  Number(
                    issue?.supports ?? 0
                  );

                const percentage =
                  getPercentage(
                    supports
                  );

                const isTopIssue =
                  index === 0;

                return (
                  <article
                    key={issue.id}
                    className={`pb-priority-card ${
                      isTopIssue
                        ? "is-top-priority"
                        : ""
                    }`}
                  >

                    {/* CARD HEADER */}

                    <div className="pb-priority-header">

                      <span
                        className={getRankClass(
                          index
                        )}
                      >
                        {String(
                          index + 1
                        ).padStart(2, "0")}
                      </span>

                      <div className="pb-priority-heading">

                        <span className="pb-category">
                          {getIssueCategory(
                            issue
                          )}
                        </span>

                        <h3>
                          {getIssueTitle(
                            issue
                          )}
                        </h3>

                      </div>

                      <div className="pb-support-count">

                        <strong>
                          {supports}
                        </strong>

                        <span>
                          supports
                        </span>

                      </div>

                    </div>

                    {/* DESCRIPTION */}

                    <p className="pb-priority-description">
                      {issue?.description ||
                        "No additional description available."}
                    </p>

                    {/* LOCATION */}

                    <div className="pb-priority-location">

                      <span className="location-icon">
                        ●
                      </span>

                      <span>
                        {getIssueLocation(
                          issue
                        )}
                      </span>

                    </div>

                    {/* SUPPORT PROGRESS */}

                    <div className="pb-progress-row">

                      <div className="pb-progress-track">

                        <div
                          className="pb-progress-fill"
                          style={{
                            width: `${percentage}%`,
                          }}
                        />

                      </div>

                      <span className="pb-progress-value">
                        {percentage}%
                      </span>

                    </div>

                  </article>
                );
              }
            )}

          </div>
        )}

      </section>

      {/* ======================================================
          CITIZEN PRIORITY SELECTION
      ====================================================== */}

      <section className="pb-voting-section">

        <div className="pb-section-header">

          <div>

            <span className="pb-section-label">
              YOUR PRIORITIES
            </span>

            <h2>
              What should receive attention first?
            </h2>

            <p>
              Select up to 3 recurring civic issues
              that you believe deserve greater attention.
            </p>

          </div>

          <div
            className={`pb-selection-counter ${
              selectedIssues.length > 0
                ? "has-selection"
                : ""
            }`}
          >
            <strong>
              {selectedIssues.length}
            </strong>

            <span>
              / 3 selected
            </span>

          </div>

        </div>

        {issues.length === 0 ? (

          <div className="pb-empty-state">

            <div className="pb-empty-icon">
              —
            </div>

            <h3>
              Nothing to prioritize yet
            </h3>

            <p>
              Civic issues will become available
              once complaints are submitted.
            </p>

          </div>

        ) : (

          <form onSubmit={handleSubmit}>

            <div className="pb-issue-grid">

              {rankedIssues.map(
                (issue) => {

                  const selected =
                    selectedIssues.includes(
                      Number(issue.id)
                    );

                  return (
                    <button
                      key={issue.id}
                      type="button"
                      className={`pb-issue-option ${
                        selected
                          ? "selected"
                          : ""
                      }`}
                      onClick={() =>
                        toggleIssue(
                          issue.id
                        )
                      }
                      disabled={
                        submitting
                      }
                      aria-pressed={
                        selected
                      }
                      aria-label={`${
                        selected
                          ? "Remove"
                          : "Select"
                      } ${getIssueTitle(
                        issue
                      )}`}
                    >

                      <span
                        className="pb-selection-check"
                        aria-hidden="true"
                      >
                        {selected
                          ? "✓"
                          : ""}
                      </span>

                      <span className="pb-option-content">

                        <span className="pb-option-category">
                          {getIssueCategory(
                            issue
                          )}
                        </span>

                        <span className="pb-option-title">
                          {getIssueTitle(
                            issue
                          )}
                        </span>

                        <span className="pb-option-description">
                          {issue?.description ||
                            "No description available."}
                        </span>

                        <span className="pb-option-meta">

                          <span>
                            {Number(
                              issue?.supports ??
                                0
                            )}{" "}
                            supports
                          </span>

                          <span>
                            {getIssueLocation(
                              issue
                            )}
                          </span>

                        </span>

                      </span>

                    </button>
                  );
                }
              )}

            </div>

            {/* =================================================
                SUBMIT AREA
                ================================================= */}

            <div className="pb-submit-area">

              <div className="pb-submit-copy">

                <span className="pb-section-label">
                  BEFORE YOU SUBMIT
                </span>

                <p>
                  Your selection represents community
                  preference. It does not directly allocate
                  public funds or guarantee implementation.
                </p>

              </div>

              <button
                type="submit"
                className="pb-submit-button"
                disabled={
                  submitting ||
                  selectedIssues.length === 0
                }
              >

                <span>
                  {submitting
                    ? "Submitting..."
                    : submitted
                    ? "Priorities Submitted"
                    : "Submit My Priorities"}
                </span>

                {!submitting &&
                  !submitted && (
                    <span
                      className="submit-arrow"
                      aria-hidden="true"
                    >
                      →
                    </span>
                  )}

              </button>

            </div>

          </form>
        )}

      </section>

      {/* ======================================================
          COMMUNITY RECOMMENDATION
      ====================================================== */}

      {topPriority && (

        <section className="pb-recommendation">

          <div className="pb-recommendation-number">
            01
          </div>

          <div className="pb-recommendation-content">

            <span className="pb-section-label">
              COMMUNITY RECOMMENDATION
            </span>

            <h2>
              Current leading priority
            </h2>

            <p>
              Based on current community support,
              <strong>
                {" "}
                {getIssueTitle(
                  topPriority
                )}
              </strong>{" "}
              currently has the strongest
              priority signal.
            </p>

            <small>
              This recommendation is advisory.
              Final budget and implementation decisions
              remain with the authorized authority.
            </small>

          </div>

          <div className="pb-recommendation-stat">

            <strong>
              {Number(
                topPriority?.supports ?? 0
              )}
            </strong>

            <span>
              supports
            </span>

          </div>

        </section>
      )}

    </main>
  );
}

export default ParticipatoryBudgeting;