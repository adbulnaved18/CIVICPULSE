import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  submitComplaint,
  checkDuplicate,
  getComplaints,
  uploadEvidence,
  voteComplaint,
  transcribeReport,
  analyzeReport,
  submitAnalyzedReport,
} from "../services/apiClient";
import { useAuth } from "../context/AuthContext";

import "./SubmitComplaint.css";
import Navbar from "../components/Navbar";
import { INDIAN_STATES } from "../utils/constants";

const CATEGORIES = [
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

function SubmitComplaint() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    description: "",
    category: "",
    state: "",
    location: "",
    language: "en",
  });

  const [isCategoryOpen, setIsCategoryOpen] = useState(false);
  const categoryDropdownRef = useRef(null);
  
  const [isStateOpen, setIsStateOpen] = useState(false);
  const stateDropdownRef = useRef(null);

  const [photo, setPhoto] = useState(null);

  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");

  const [complaints, setComplaints] = useState([]);
  const [duplicateMatches, setDuplicateMatches] = useState([]);

  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");

  const [loading, setLoading] = useState(false);
  const [loadingComplaints, setLoadingComplaints] = useState(true);
  const [votingId, setVotingId] = useState(null);

  // --------------------------------------------------
  // VOICE RECORDING STATE
  // idle | recording | transcribing | ready | error
  // --------------------------------------------------
  const [voiceState, setVoiceState] = useState("idle");
  const [voiceError, setVoiceError] = useState("");
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // --------------------------------------------------
  // AI ANALYSIS STATE
  // idle | analyzing | suggested | needs-review | error
  // --------------------------------------------------
  const [aiState, setAiState] = useState("idle");
  const [aiResult, setAiResult] = useState(null);  // AnalyzeResponse
  const [aiError, setAiError] = useState("");
  // analysis_id to include in the final submission
  const [analysisId, setAnalysisId] = useState(null);


  // Close custom dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (
        categoryDropdownRef.current &&
        !categoryDropdownRef.current.contains(event.target)
      ) {
        setIsCategoryOpen(false);
      }
      
      if (
        stateDropdownRef.current &&
        !stateDropdownRef.current.contains(event.target)
      ) {
        setIsStateOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // --------------------------------------------------
  // LOCATION CAPTURE
  // --------------------------------------------------
  const [geoLocation, setGeoLocation] = useState({
    latitude: null,
    longitude: null,
    accuracy: null,
    capturedAt: null,
    status: "idle",    // idle | loading | captured | denied | error
    error: null,
  });

  function captureLocation() {
    if (!navigator.geolocation) {
      setGeoLocation((prev) => ({
        ...prev,
        status: "error",
        error: "Geolocation is not supported by this browser.",
      }));
      return;
    }

    setGeoLocation((prev) => ({
      ...prev,
      status: "loading",
      error: null,
    }));

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setGeoLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          capturedAt: new Date().toISOString(),
          status: "captured",
          error: null,
        });
      },
      (err) => {
        const isDenied = err.code === err.PERMISSION_DENIED;

        setGeoLocation((prev) => ({
          ...prev,
          status: isDenied ? "denied" : "error",
          error: isDenied
            ? "Location permission denied."
            : "Unable to determine your location.",
        }));
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000,
      }
    );
  }

  useEffect(() => {
    loadComplaints();
    captureLocation();
  }, []);

  async function loadComplaints() {
    try {
      setLoadingComplaints(true);

      const data = await getComplaints();

      const sortedData = [...(data || [])].sort((a, b) => {
        const priorityA = Number(a.priority ?? 0);
        const priorityB = Number(b.priority ?? 0);

        if (priorityB !== priorityA) {
          return priorityB - priorityA;
        }

        return Number(a.id) - Number(b.id);
      });

      setComplaints(sortedData);
    } catch (error) {
      console.error("Failed to load complaints:", error);

      setMessage("Unable to load complaints.");
      setMessageType("error");
    } finally {
      setLoadingComplaints(false);
    }
  }

  function handleChange(event) {
    const { name, value } = event.target;

    setForm((previousForm) => ({
      ...previousForm,
      [name]: value,
    }));

    // Invalidate AI analysis whenever description is edited.
    if (name === "description") {
      setAnalysisId(null);
      setAiResult(null);
      setAiState("idle");
    }
  }

  function handlePhotoChange(event) {
    const selectedFile = event.target.files?.[0] || null;

    if (!selectedFile) {
      setPhoto(null);
      return;
    }

    if (!selectedFile.type.startsWith("image/")) {
      setMessage("Please select an image file.");
      setMessageType("error");
      setPhoto(null);
      event.target.value = "";
      return;
    }

    setPhoto(selectedFile);
    setMessage("");
    setMessageType("");

    // Invalidate any previous AI analysis when the image changes.
    setAnalysisId(null);
    setAiResult(null);
    setAiState("idle");
  }

  // --------------------------------------------------
  // VOICE RECORDING
  // --------------------------------------------------
  async function startRecording() {
    setVoiceError("");

    if (!isAuthenticated) {
      setVoiceError("Please log in before using voice transcription.");
      setVoiceState("error");
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setVoiceError("Microphone is not supported in this browser.");
      setVoiceState("error");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        audioChunksRef.current = [];
        setVoiceState("transcribing");

        try {
          const result = await transcribeReport(blob, form.language || null);
          const transcript = result?.transcript || "";

          if (transcript) {
            setForm((prev) => ({
              ...prev,
              description: prev.description
                ? prev.description.trim() + " " + transcript
                : transcript,
            }));
            setAnalysisId(null);
            setAiResult(null);
            setAiState("idle");
          }
          setVoiceState("ready");
        } catch (err) {
          console.error("Transcription failed:", err);
          setVoiceError(
            err.message || "Transcription failed. Please type your report."
          );
          setVoiceState("error");
        }
      };

      recorder.start();
      setVoiceState("recording");
    } catch (err) {
      const isDenied =
        err.name === "NotAllowedError" || err.name === "PermissionDeniedError";
      setVoiceError(
        isDenied
          ? "Microphone permission denied. Please type your report."
          : "Could not access the microphone."
      );
      setVoiceState("error");
    }
  }

  function stopRecording() {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
    }
  }

  // --------------------------------------------------
  // AI ANALYSIS
  // --------------------------------------------------
  async function handleAnalyzeReport() {
    const description = form.description.trim();

    if (!isAuthenticated) {
      setAiError("Please log in before using AI report analysis.");
      setAiState("error");
      return;
    }

    if (!description && !photo) {
      setAiError(
        "Please enter a description or upload a photo before analyzing."
      );
      return;
    }

    setAiState("analyzing");
    setAiError("");
    setAiResult(null);

    try {
      const result = await analyzeReport({
        description: description || null,
        image: photo || null,
        selectedCategory: form.category || null,
        language: form.language || null,
      });

      setAiResult(result);
      setAnalysisId(result.analysis_id);

      const confidence = result.confidence ?? 0;
      if (confidence >= 0.80) {
        setForm((prev) => ({ ...prev, category: result.suggested_category }));
        setAiState("suggested");
      } else if (confidence >= 0.60) {
        setAiState("suggested");
      } else {
        setAiState("needs-review");
      }
    } catch (err) {
      console.error("AI analysis failed:", err);
      setAiError(
        err.message ||
          "AI analysis unavailable. Please select a category manually."
      );
      setAiState("error");
    }
  }

  function applyAiCategory() {
    if (aiResult?.suggested_category) {
      setForm((prev) => ({ ...prev, category: aiResult.suggested_category }));
    }
  }

  // --------------------------------------------------
  // SUBMIT
  // --------------------------------------------------
  async function handleSubmit(event) {
    event.preventDefault();


    // --------------------------------------------------
    // AUTHENTICATION CHECK
    // --------------------------------------------------
    if (!isAuthenticated) {
      setMessage(
        "Please log in to submit a complaint. Redirecting to login..."
      );
      setMessageType("warning");

      setTimeout(() => {
        navigate("/auth");
      }, 1200);

      return;
    }

    const description = form.description.trim();
    const category = form.category.trim();
    const state = form.state.trim();
    const location = form.location.trim();

    // --------------------------------------------------
    // FORM VALIDATION
    // --------------------------------------------------
    if (!description || !category || !state || !location) {
      setMessage(
        "Please fill in description, category, state, and location."
      );
      setMessageType("error");
      return;
    }

    try {
      setLoading(true);

      await submitAnalyzedReport({
        description,
        category,
        state,
        location,
        language: form.language || "en",
        analysisId,
        image: photo,
        latitude: geoLocation.latitude,
        longitude: geoLocation.longitude,
        locationAccuracy: geoLocation.accuracy,
        locationCapturedAt: geoLocation.capturedAt,
      });

      setMessage("Complaint submitted successfully!");
      setMessageType("success");

      setForm({
        description: "",
        category: "",
        state: "",
        location: "",
        language: "en",
      });

      setPhoto(null);
      setAnalysisId(null);
      setAiResult(null);
      setAiState("idle");
      setAiError("");
      setVoiceState("idle");
      setVoiceError("");

      const fileInput = document.getElementById("photo");
      if (fileInput) {
        fileInput.value = "";
      }

      await loadComplaints();
    } catch (error) {
      console.error("Failed to submit complaint:", error);

      // Handle duplicate from the unified endpoint too.
      let errorMessage =
        error.message || "Failed to submit complaint. Please try again.";

      try {
        const parsed = JSON.parse(error.message);
        if (parsed?.is_duplicate && parsed?.matches) {
          setDuplicateMatches(parsed.matches || []);
          errorMessage =
            "A similar complaint already exists. Please support the existing complaint instead of creating a duplicate.";
          setMessageType("warning");
          setMessage(errorMessage);
          return;
        }
      } catch {
        // Not JSON — fall through.
      }

      setMessage(errorMessage);
      setMessageType("error");
    } finally {
      setLoading(false);
    }
  }

  async function handleVote(complaintId) {
    // --------------------------------------------------
    // AUTHENTICATION CHECK FOR VOTING
    // --------------------------------------------------
    if (!isAuthenticated) {
      setMessage(
        "Please log in to support this complaint. Redirecting to login..."
      );
      setMessageType("warning");

      setTimeout(() => {
        navigate("/auth");
      }, 1200);

      return;
    }

    try {
      setVotingId(complaintId);
      setMessage("");
      setMessageType("");

      const data = await voteComplaint(complaintId);

      if (
        data?.message ===
        "You have already voted for this complaint"
      ) {
        setMessage(
          "You have already supported this complaint."
        );

        setMessageType("warning");
        return;
      }

      setMessage(
        "Thanks! Your support has been added to this complaint."
      );

      setMessageType("success");

      await loadComplaints();
    } catch (error) {
      console.error("Failed to vote:", error);

      if (error.message === "Not authenticated") {
        setMessage(
          "Your session expired. Please log in again."
        );
        setMessageType("warning");

        navigate("/auth");
        return;
      }

      setMessage(
        "Failed to support this complaint."
      );

      setMessageType("error");
    } finally {
      setVotingId(null);
    }
  }

  function getStatusClass(status) {
    if (status === "Resolved") {
      return "status status-resolved";
    }

    if (status === "In Progress") {
      return "status status-progress";
    }

    return "status status-pending";
  }

  function getPriorityLabel(priority = 0) {
    const value = Number(priority);

    if (value >= 5) {
      return "High";
    }

    if (value >= 2) {
      return "Medium";
    }

    return "Low";
  }

  function getPriorityClass(priority = 0) {
    const value = Number(priority);

    if (value >= 5) {
      return "priority priority-high";
    }

    if (value >= 2) {
      return "priority priority-medium";
    }

    return "priority priority-low";
  }

  const normalizedSearch =
    searchTerm.trim().toLowerCase();

  const filteredComplaints =
    complaints.filter((complaint) => {
      const description =
        complaint.description?.toLowerCase() || "";

      const category =
        complaint.category?.toLowerCase() || "";

      const location =
        complaint.location?.toLowerCase() || "";

      const matchesSearch =
        description.includes(normalizedSearch) ||
        category.includes(normalizedSearch) ||
        location.includes(normalizedSearch);

      const matchesStatus =
        statusFilter === "All" ||
        complaint.status === statusFilter;

      return matchesSearch && matchesStatus;
    });

  return (
    <div className="complaints-page">
      <Navbar />

      {/* ==================================================
          HEADER
      ================================================== */}
      <header className="complaints-header">
        <div>
          <span className="page-label">
            CIVICPULSE
          </span>

          <h1>Report a Civic Issue</h1>

          <p>
            Raise issues. Support your community.
            Track progress.
          </p>
        </div>

        <div className="header-stat">
          <strong>{complaints.length}</strong>

          <span>Reported Issues</span>
        </div>
      </header>

      {/* ==================================================
          MESSAGE
      ================================================== */}
      {message && (
        <div
          className={`message ${messageType}`}
          role="alert"
        >
          {message}
        </div>
      )}

      {/* ==================================================
          SUBMIT FORM
      ================================================== */}
      <section className="complaint-form-card">

        <div className="section-heading">
          <div>
            <span className="section-label">
              REPORT
            </span>

            <h2>Tell us what happened</h2>

            <p>
              Provide enough detail so the issue can
              be understood and acted upon.
            </p>
          </div>

          <span className="required-note">
            * Required
          </span>
        </div>

        <form onSubmit={handleSubmit}>

          {/* DESCRIPTION */}
          <div className="form-group">
            <div className="description-header">
              <label htmlFor="description">
                Description *
              </label>
              <div className="voice-controls">
                {voiceState === "idle" || voiceState === "ready" || voiceState === "error" ? (
                  <button
                    type="button"
                    className="voice-btn start-recording"
                    onClick={startRecording}
                    title="Record voice description"
                  >
                    🎙️ Voice
                  </button>
                ) : voiceState === "recording" ? (
                  <button
                    type="button"
                    className="voice-btn stop-recording"
                    onClick={stopRecording}
                    title="Stop recording"
                  >
                    ⏹️ Stop
                  </button>
                ) : (
                  <span className="voice-status transcribing">Transcribing...</span>
                )}
                {voiceError && <span className="voice-error-text">{voiceError}</span>}
              </div>
            </div>

            <textarea
              id="description"
              name="description"
              value={form.description}
              onChange={handleChange}
              placeholder="Describe the issue clearly..."
              rows="5"
              required
            />

            <small>
              Mention what happened, where it happened,
              and any useful details. You can type or use the voice button.
            </small>
          </div>


          {/* CATEGORY + STATE */}
          <div className="form-row">

            <div
              className="form-group custom-select-group"
              ref={categoryDropdownRef}
            >
              <label htmlFor="category">
                Category *
              </label>

              <button
                type="button"
                id="category"
                className={`custom-select-trigger ${
                  isCategoryOpen ? "open" : ""
                } ${!form.category ? "placeholder" : ""}`}
                onClick={() =>
                  setIsCategoryOpen((prev) => !prev)
                }
                aria-haspopup="listbox"
                aria-expanded={isCategoryOpen}
              >
                <span>
                  {form.category || "Select a category"}
                </span>

                <svg
                  className={`dropdown-chevron ${
                    isCategoryOpen ? "rotated" : ""
                  }`}
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>

              {isCategoryOpen && (
                <ul
                  className="custom-select-menu"
                  role="listbox"
                >
                  {CATEGORIES.map((cat) => (
                    <li
                      key={cat}
                      role="option"
                      aria-selected={form.category === cat}
                      className={`custom-select-option ${
                        form.category === cat
                          ? "selected"
                          : ""
                      }`}
                      onClick={() => {
                        setForm((prev) => ({
                          ...prev,
                          category: cat,
                        }));
                        setIsCategoryOpen(false);
                      }}
                    >
                      {cat}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div
              className="form-group custom-select-group"
              ref={stateDropdownRef}
            >
              <label htmlFor="state">
                State *
              </label>

              <button
                type="button"
                id="state"
                className={`custom-select-trigger ${
                  isStateOpen ? "open" : ""
                } ${!form.state ? "placeholder" : ""}`}
                onClick={() =>
                  setIsStateOpen((prev) => !prev)
                }
                aria-haspopup="listbox"
                aria-expanded={isStateOpen}
              >
                <span>
                  {form.state || "Select a state"}
                </span>

                <svg
                  className={`dropdown-chevron ${
                    isStateOpen ? "rotated" : ""
                  }`}
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>

              {isStateOpen && (
                <ul
                  className="custom-select-menu"
                  role="listbox"
                >
                  {INDIAN_STATES.map((state) => (
                    <li
                      key={state}
                      role="option"
                      aria-selected={form.state === state}
                      className={`custom-select-option ${
                        form.state === state
                          ? "selected"
                          : ""
                      }`}
                      onClick={() => {
                        setForm((prev) => ({
                          ...prev,
                          state: state,
                        }));
                        setIsStateOpen(false);
                      }}
                    >
                      {state}
                    </li>
                  ))}
                </ul>
              )}
            </div>

          </div>

          {/* LOCATION + LANGUAGE */}
          <div className="form-row">

            <div className="form-group">
              <label htmlFor="location">
                Specific Location *
              </label>

              <input
                id="location"
                name="location"
                type="text"
                value={form.location}
                onChange={handleChange}
                placeholder="Gate 2, Main Road"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="language">
                Language
              </label>

              <select
                id="language"
                name="language"
                value={form.language}
                onChange={handleChange}
              >
                <option value="en">
                  English
                </option>

                <option value="hi">
                  Hindi
                </option>
              </select>
            </div>

          </div>

          {/* PHOTO EVIDENCE */}
          <div className="form-group">
              <label htmlFor="photo">
                Photo Evidence
              </label>

              <input
                id="photo"
                type="file"
                accept="image/*"
                onChange={handlePhotoChange}
              />

              {photo && (
                <div className="selected-file">
                  <span>📷</span>
                  <span>{photo.name}</span>
                </div>
              )}

              <small>
                Optional. Upload an image that helps
                explain the issue.
              </small>
            </div>

          {/* AI ANALYSIS SECTION */}
          <div className="ai-analysis-section">
            <div className="ai-actions">
              <button
                type="button"
                className="ai-btn analyze-btn"
                onClick={handleAnalyzeReport}
                disabled={aiState === "analyzing" || (!form.description && !photo)}
              >
                {aiState === "analyzing" ? "Analyzing..." : "✨ Analyze Report with AI"}
              </button>
              {aiError && <span className="ai-error-text">{aiError}</span>}
            </div>

            {aiResult && (
              <div className={`ai-suggestion-card ${aiState}`}>
                <div className="ai-suggestion-header">
                  <h3>AI Suggestion</h3>
                  {aiResult.confidence && (
                    <span className="ai-confidence-badge">
                      {Math.round(aiResult.confidence * 100)}% Match
                    </span>
                  )}
                </div>
                
                <div className="ai-suggestion-body">
                  <p><strong>Suggested Category:</strong> {aiResult.suggested_category}</p>
                  <p className="ai-reason">{aiResult.short_reason}</p>
                  
                  {aiState === "suggested" && (
                    <div className="ai-suggestion-actions">
                      <p className="ai-prompt">Would you like to use this category?</p>
                      <button 
                        type="button" 
                        className="ai-btn accept-btn" 
                        onClick={applyAiCategory}
                      >
                        Yes, use {aiResult.suggested_category}
                      </button>
                    </div>
                  )}
                  {aiState === "needs-review" && (
                    <p className="ai-warning">
                      ⚠️ AI confidence is low. Please select the category manually above.
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>


          {/* LOCATION CAPTURE */}
          <div className="location-widget">
            <label>GPS Location</label>

            {geoLocation.status === "loading" && (
              <div className="location-status location-loading">
                <span className="location-spinner" />
                <span>Detecting your location…</span>
              </div>
            )}

            {geoLocation.status === "captured" && (
              <div className="location-status location-captured">
                <span>📍</span>
                <span>
                  {geoLocation.latitude.toFixed(5)},&nbsp;
                  {geoLocation.longitude.toFixed(5)}
                  {geoLocation.accuracy && (
                    <small>
                      &nbsp;(±{Math.round(geoLocation.accuracy)}m)
                    </small>
                  )}
                </span>
                <button
                  type="button"
                  className="location-retry"
                  onClick={captureLocation}
                >
                  Refresh
                </button>
              </div>
            )}

            {(geoLocation.status === "denied" ||
              geoLocation.status === "error") && (
              <div className="location-status location-error">
                <span>⚠</span>
                <span>{geoLocation.error}</span>
                <button
                  type="button"
                  className="location-retry"
                  onClick={captureLocation}
                >
                  Retry
                </button>
              </div>
            )}

            {geoLocation.status === "idle" && (
              <div className="location-status location-idle">
                <span>Location not yet requested.</span>
                <button
                  type="button"
                  className="location-retry"
                  onClick={captureLocation}
                >
                  Detect Location
                </button>
              </div>
            )}

            <small>
              Optional. Helps pinpoint the exact location
              on the admin map.
            </small>
          </div>

          {/* SUBMIT */}
          <div className="form-actions">
            <button
              type="submit"
              className="primary-button"
              disabled={loading}
            >
              {loading
                ? "Submitting..."
                : "Submit Complaint"}
            </button>

            <span className="form-help">
              Similar complaints are checked automatically.
            </span>
          </div>

        </form>
      </section>

      {/* ==================================================
          DUPLICATE MATCHES
      ================================================== */}
      {duplicateMatches.length > 0 && (
        <section className="duplicate-section">

          <div className="section-heading">
            <div>
              <span className="section-label">
                POSSIBLE DUPLICATE
              </span>

              <h2>
                An existing issue may match yours
              </h2>

              <p>
                Supporting an existing complaint keeps
                community reports together and avoids
                duplicate issues.
              </p>
            </div>
          </div>

          <div className="duplicate-list">

            {duplicateMatches.map((complaint) => (
              <article
                key={complaint.id}
                className="duplicate-card"
              >

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

                <h3>
                  {complaint.description}
                </h3>

                <div className="complaint-meta">

                  <span>
                    <strong>Category:</strong>{" "}
                    {complaint.category}
                  </span>

                  <span>
                    <strong>Location:</strong>{" "}
                    {complaint.location}
                  </span>

                  <span>
                    👍 {complaint.votes ?? 0} supports
                  </span>

                </div>

                <button
                  type="button"
                  className="support-button"
                  disabled={
                    votingId === complaint.id
                  }
                  onClick={() =>
                    handleVote(complaint.id)
                  }
                >
                  {votingId === complaint.id
                    ? "Supporting..."
                    : "+1 Support this issue"}
                </button>

              </article>
            ))}

          </div>
        </section>
      )}

      {/* ==================================================
          COMMUNITY COMPLAINTS
      ================================================== */}
      <section className="complaints-list-section">

        <div className="section-header">

          <div>
            <span className="section-label">
              COMMUNITY ISSUES
            </span>

            <h2>
              Submitted Complaints
            </h2>

            <p className="section-description">
              Browse reported issues and support the
              ones that matter to your community.
            </p>
          </div>

          <span className="complaint-count">
            {filteredComplaints.length}{" "}
            {filteredComplaints.length === 1
              ? "complaint"
              : "complaints"}
          </span>

        </div>

        {/* SEARCH + FILTER */}
        <div className="complaint-filters">

          <div className="search-wrapper">
            <span>🔍</span>

            <input
              type="text"
              placeholder="Search by issue, category or location..."
              value={searchTerm}
              onChange={(event) =>
                setSearchTerm(event.target.value)
              }
            />
          </div>

          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value)
            }
          >
            <option value="All">
              All Statuses
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

        </div>

        {/* LOADING */}
        {loadingComplaints ? (

          <div className="empty-state">
            <h3>Loading complaints...</h3>

            <p>
              Please wait while we fetch community issues.
            </p>
          </div>

        ) : filteredComplaints.length === 0 ? (

          <div className="empty-state">
            <h3>No complaints found</h3>

            <p>
              Try changing your search or status filter.
            </p>
          </div>

        ) : (

          <div className="complaints-list">

            {filteredComplaints.map((complaint) => {

              const priority =
                Number(complaint.priority ?? 0);

              const isHighPriority =
                priority >= 5 &&
                complaint.status !== "Resolved";

              return (
                <article
                  key={complaint.id}
                  className={`complaint-card ${
                    isHighPriority
                      ? "high-priority"
                      : ""
                  }`}
                >

                  {/* TOP */}
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

                  {/* DESCRIPTION */}
                  <h3>
                    {complaint.description}
                  </h3>

                  {/* DETAILS */}
                  <div className="complaint-details">

                    <div>
                      <span className="detail-label">
                        Category
                      </span>

                      <span>
                        {complaint.category}
                      </span>
                    </div>

                    <div>
                      <span className="detail-label">
                        Location
                      </span>

                      <span>
                        {complaint.location}
                      </span>
                    </div>

                    <div>
                      <span className="detail-label">
                        Language
                      </span>

                      <span>
                        {complaint.language === "hi"
                          ? "Hindi"
                          : "English"}
                      </span>
                    </div>

                  </div>

                  {/* FOOTER */}
                  <div className="complaint-footer">

                    <div className="complaint-stats">

                      <span>
                        👍 {complaint.votes ?? 0} supports
                      </span>

                      <span
                        className={getPriorityClass(
                          priority
                        )}
                      >
                        Priority:{" "}
                        {getPriorityLabel(priority)}
                      </span>

                    </div>

                    <button
                      type="button"
                      className="support-button"
                      disabled={
                        votingId === complaint.id
                      }
                      onClick={() =>
                        handleVote(complaint.id)
                      }
                    >
                      {votingId === complaint.id
                        ? "Supporting..."
                        : "+1 Support this issue"}
                    </button>

                  </div>

                </article>
              );
            })}

          </div>
        )}

      </section>

    </div>
  );
}

export default SubmitComplaint;
