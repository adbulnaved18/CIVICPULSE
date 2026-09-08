// ============================================================
// CivicPulse API Client
// ============================================================

// Local development defaults to FastAPI on port 8000. For a deployed frontend,
// set VITE_API_URL to the public backend URL before running `npm run build`.
const API_URL = (
  import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

// ============================================================
// INTERNAL ERROR HANDLER
// ============================================================

async function getErrorMessage(response, defaultMessage) {
  try {
    const data = await response.json();

    if (data?.detail) {
      if (typeof data.detail === "string") {
        return data.detail;
      }

      return JSON.stringify(data.detail);
    }

    if (data?.message) {
      return data.message;
    }

    if (data?.error) {
      return data.error;
    }
  } catch {
    // Ignore JSON parsing errors
  }

  return defaultMessage;
}

// ============================================================
// GENERIC REQUEST HELPER
// ============================================================

async function apiRequest(
  endpoint,
  options = {},
  defaultMessage = "Something went wrong"
) {
  const response = await fetch(
    `${API_URL}${endpoint}`,
    {
      credentials: "include",
      ...options,
      headers: {
        ...(options.body instanceof FormData
          ? {}
          : {
              "Content-Type": "application/json",
            }),
        ...(options.headers || {}),
      },
    }
  );

  if (!response.ok) {
    const message = await getErrorMessage(
      response,
      defaultMessage
    );

    throw new Error(message);
  }

  // Some endpoints may return an empty response.
  if (response.status === 204) {
    return null;
  }

  try {
    return await response.json();
  } catch {
    return null;
  }
}

// ============================================================
// COMPLAINTS
// ============================================================

// ------------------------------------------------------------
// SUBMIT COMPLAINT
// ------------------------------------------------------------

export async function submitComplaint(complaint) {
  if (!complaint || typeof complaint !== "object") {
    throw new Error("Invalid complaint data.");
  }

  return apiRequest(
    "/complaints/",
    {
      method: "POST",
      body: JSON.stringify(complaint),
    },
    "Failed to submit complaint."
  );
}

// ------------------------------------------------------------
// GET ALL COMPLAINTS
// ------------------------------------------------------------

export async function getComplaints(state = null, region = null) {
  const params = new URLSearchParams();

  if (state) {
    params.set("state", state);
  }

  if (region) {
    params.set("region", region);
  }

  const query = params.toString();
  const endpoint = query
    ? `/complaints/?${query}`
    : "/complaints/";

  return apiRequest(
    endpoint,
    { method: "GET" },
    "Failed to fetch complaints."
  );
}

// ------------------------------------------------------------
// GET MY COMPLAINTS
// ------------------------------------------------------------

export async function getMyComplaints() {
  return apiRequest(
    "/complaints/my",
    { method: "GET" },
    "Failed to fetch your complaints."
  );
}

// ------------------------------------------------------------
// GET UNIQUE REGIONS
// ------------------------------------------------------------

export async function getRegions() {
  return apiRequest(
    "/complaints/regions",
    { method: "GET" },
    "Failed to fetch regions."
  );
}

// ------------------------------------------------------------
// GET GEO-LOCATED COMPLAINTS (for admin map)
// ------------------------------------------------------------

export async function getGeoComplaints(filters = {}) {
  const params = new URLSearchParams();

  if (filters.status) {
    params.set("status", filters.status);
  }

  if (filters.category) {
    params.set("category", filters.category);
  }

  if (filters.state) {
    params.set("state", filters.state);
  }

  const query = params.toString();
  const endpoint = query
    ? `/complaints/geo?${query}`
    : "/complaints/geo";

  return apiRequest(
    endpoint,
    {
      method: "GET",
    },
    "Failed to fetch geolocated complaints."
  );
}

// ------------------------------------------------------------
// UPDATE COMPLAINT STATUS
// ------------------------------------------------------------

export async function updateComplaintStatus(
  id,
  status
) {
  if (!id) {
    throw new Error("Complaint ID is required.");
  }

  if (!status) {
    throw new Error("Complaint status is required.");
  }

  const query = new URLSearchParams({
    status: String(status),
  });

  return apiRequest(
    `/complaints/${id}/status?${query.toString()}`,
    {
      method: "PATCH",
    },
    "Failed to update complaint status."
  );
}

// ------------------------------------------------------------
// CHECK DUPLICATE COMPLAINT
// ------------------------------------------------------------

export async function checkDuplicate(
  category,
  location,
  description,
  latitude = null,
  longitude = null
) {
  const params = new URLSearchParams({
    category: category || "",
    location: location || "",
    description: description || "",
  });
  if (latitude !== null) params.append("latitude", latitude);
  if (longitude !== null) params.append("longitude", longitude);

  return apiRequest(
    `/complaints/check-duplicate?${params.toString()}`,
    {
      method: "GET",
    },
    "Failed to check duplicate complaint."
  );
}

// ============================================================
// COMPLAINT EVIDENCE
// ============================================================

// ------------------------------------------------------------
// UPLOAD EVIDENCE
// ------------------------------------------------------------

export async function uploadEvidence(
  complaintId,
  photo
) {
  if (!complaintId) {
    throw new Error("Complaint ID is required.");
  }

  if (!photo) {
    throw new Error("No evidence file selected.");
  }

  const formData = new FormData();

  formData.append("file", photo);

  return apiRequest(
    `/complaints/${complaintId}/evidence`,
    {
      method: "POST",
      body: formData,
    },
    "Failed to upload evidence."
  );
}

// ------------------------------------------------------------
// GET COMPLAINT EVIDENCE
// ------------------------------------------------------------

export async function getComplaintEvidence(
  complaintId
) {
  if (!complaintId) {
    throw new Error("Complaint ID is required.");
  }

  return apiRequest(
    `/complaints/${complaintId}/evidence`,
    {
      method: "GET",
    },
    "Failed to fetch complaint evidence."
  );
}

// ============================================================
// COMPLAINT SUPPORT / VOTING
// ============================================================

// ------------------------------------------------------------
// SUPPORT COMPLAINT
// ------------------------------------------------------------

export async function voteComplaint(
  complaintId
) {
  if (!complaintId) {
    throw new Error("Complaint ID is required.");
  }

  /*
   * IMPORTANT:
   *
   * No voter_id is sent from frontend.
   *
   * Backend identifies the logged-in citizen using
   * the httpOnly authentication cookie.
   *
   * credentials: "include" is handled by apiRequest().
   */

  return apiRequest(
    `/complaints/${complaintId}/vote`,
    {
      method: "POST",
    },
    "Failed to support complaint."
  );
}

// ============================================================
// PARTICIPATORY BUDGETING
// ============================================================

// ------------------------------------------------------------
// GET COMMUNITY PRIORITIES
// ------------------------------------------------------------

export async function getParticipatoryBudgetingPriorities(state = null, category = null, search = null) {
  const params = new URLSearchParams();

  if (state) {
    params.set("state", state);
  }

  if (category && category !== "All") {
    params.set("category", category);
  }

  if (search && search.trim()) {
    params.set("search", search.trim());
  }

  const query = params.toString();
  const endpoint = query
    ? `/participatory-budgeting/priorities?${query}`
    : "/participatory-budgeting/priorities";

  return apiRequest(
    endpoint,
    {
      method: "GET",
    },
    "Failed to fetch participatory budgeting priorities."
  );
}

// ------------------------------------------------------------
// SUBMIT COMMUNITY PRIORITIES
// ------------------------------------------------------------

export async function submitParticipatoryPriorities(
  issueIds
) {
  if (!Array.isArray(issueIds)) {
    throw new Error(
      "Invalid civic issue selection."
    );
  }

  if (issueIds.length === 0) {
    throw new Error(
      "Please select at least one civic issue."
    );
  }

  if (issueIds.length > 3) {
    throw new Error(
      "You can prioritize up to 3 civic issues."
    );
  }

  // Remove duplicates and convert IDs to integers.
  const cleanedIssueIds = [
    ...new Set(
      issueIds
        .map((id) => Number(id))
        .filter((id) =>
          Number.isInteger(id)
        )
    ),
  ];

  if (cleanedIssueIds.length === 0) {
    throw new Error(
      "No valid civic issues were selected."
    );
  }

  if (cleanedIssueIds.length > 3) {
    throw new Error(
      "You can prioritize up to 3 civic issues."
    );
  }

  /*
   * IMPORTANT:
   *
   * Backend model:
   *
   * class PrioritySubmission(BaseModel):
   *     issue_ids: list[int]
   *
   * Therefore the request body MUST be:
   *
   * {
   *   "issue_ids": [1, 5, 6]
   * }
   *
   * DO NOT send:
   *
   * {
   *   "citizen_id": "citizen_002",
   *   "issue_ids": [...]
   * }
   *
   * Authentication is handled by the session cookie.
   */

  return apiRequest(
    "/participatory-budgeting/priorities",
    {
      method: "POST",
      body: JSON.stringify({
        issue_ids: cleanedIssueIds,
      }),
    },
    "Failed to submit community priorities."
  );
}

// ------------------------------------------------------------
// PARTICIPATORY BUDGETING HEALTH
// ------------------------------------------------------------

export async function checkParticipatoryBudgetingHealth() {
  return apiRequest(
    "/participatory-budgeting/health",
    {
      method: "GET",
    },
    "Participatory Budgeting API is unavailable."
  );
}

// ============================================================
// AUTHENTICATION
// ============================================================

// ------------------------------------------------------------
// SIGNUP
// ------------------------------------------------------------

export async function signup(
  name,
  email,
  password
) {
  if (!name?.trim()) {
    throw new Error("Name is required.");
  }

  if (!email?.trim()) {
    throw new Error("Email is required.");
  }

  if (!password) {
    throw new Error("Password is required.");
  }

  return apiRequest(
    "/auth/signup",
    {
      method: "POST",
      body: JSON.stringify({
        name: name.trim(),
        email: email.trim(),
        password,
      }),
    },
    "Failed to sign up."
  );
}

// ------------------------------------------------------------
// LOGIN
// ------------------------------------------------------------

export async function login(
  email,
  password
) {
  if (!email?.trim()) {
    throw new Error("Email is required.");
  }

  if (!password) {
    throw new Error("Password is required.");
  }

  /*
   * Backend sets the httpOnly authentication cookie here.
   *
   * credentials: "include" is essential.
   */

  return apiRequest(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify({
        email: email.trim(),
        password,
      }),
    },
    "Failed to log in."
  );
}

// ------------------------------------------------------------
// LOGOUT
// ------------------------------------------------------------

export async function logout() {
  return apiRequest(
    "/auth/logout",
    {
      method: "POST",
    },
    "Failed to log out."
  );
}

// ------------------------------------------------------------
// CURRENT USER
// ------------------------------------------------------------

export async function getMe() {
  return apiRequest(
    "/auth/me",
    {
      method: "GET",
    },
    "Not authenticated."
  );
}

// ============================================================
// API URL HELPER
// ============================================================

export function getApiUrl() {
  return API_URL;
}

// ============================================================
// EVIDENCE FILE URL HELPER
// ============================================================

export function getEvidenceUrl(filePath) {
  if (!filePath) {
    return "";
  }

  const cleanPath = String(filePath).replace(
    /^\/+/,
    ""
  );

  return `${API_URL}/${cleanPath}`;
}

// ============================================================
// AI — TRANSCRIPTION
// ============================================================

/**
 * Send an audio Blob to POST /ai/transcribe.
 *
 * @param {Blob}   audioBlob    - Recording from MediaRecorder
 * @param {string} languageHint - Optional 'en' or 'hi'
 * @returns {{ transcript: string, detected_language: string, model: string }}
 */
export async function transcribeReport(audioBlob, languageHint = null) {
  if (!audioBlob) {
    throw new Error("No audio recording to transcribe.");
  }

  const formData = new FormData();
  formData.append("audio", audioBlob, "recording.webm");

  if (languageHint) {
    formData.append("language_hint", languageHint);
  }

  return apiRequest(
    "/ai/transcribe",
    {
      method: "POST",
      body: formData,
    },
    "Transcription failed. Please try again."
  );
}

// ============================================================
// AI — ANALYZE REPORT
// ============================================================

/**
 * Send description and/or image to POST /ai/analyze-report.
 *
 * @param {{ description?: string, image?: File, selectedCategory?: string, language?: string }}
 * @returns {AnalyzeResponse}
 */
export async function analyzeReport({
  description = null,
  image = null,
  selectedCategory = null,
  language = null,
} = {}) {
  if (!description && !image) {
    throw new Error(
      "Provide a description or a photo to analyze the report."
    );
  }

  const formData = new FormData();

  if (description) {
    formData.append("description", description);
  }

  if (image) {
    formData.append("image", image);
  }

  if (selectedCategory) {
    formData.append("selected_category", selectedCategory);
  }

  if (language) {
    formData.append("language", language);
  }

  return apiRequest(
    "/ai/analyze-report",
    {
      method: "POST",
      body: formData,
    },
    "AI analysis failed. You can still submit manually."
  );
}

// ============================================================
// AI — SUBMIT ANALYZED REPORT (unified endpoint)
// ============================================================

/**
 * Submit the final complaint using the unified multipart endpoint.
 *
 * @param {{ description, category, state, location, language?,
 *           analysisId?, image?, latitude?, longitude?,
 *           locationAccuracy?, locationCapturedAt? }}
 */
export async function submitAnalyzedReport({
  description,
  category,
  state,
  location,
  language = "en",
  analysisId = null,
  image = null,
  latitude = null,
  longitude = null,
  locationAccuracy = null,
  locationCapturedAt = null,
}) {
  const formData = new FormData();

  formData.append("description", description);
  formData.append("category", category);
  formData.append("state", state);
  formData.append("location", location);
  formData.append("language", language);

  if (analysisId) {
    formData.append("analysis_id", analysisId);
  }

  if (image) {
    formData.append("image", image);
  }

  if (latitude !== null && latitude !== undefined) {
    formData.append("latitude", String(latitude));
  }

  if (longitude !== null && longitude !== undefined) {
    formData.append("longitude", String(longitude));
  }

  if (locationAccuracy !== null) {
    formData.append("location_accuracy", String(locationAccuracy));
  }

  if (locationCapturedAt) {
    formData.append("location_captured_at", locationCapturedAt);
  }

  return apiRequest(
    "/complaints/submit-report",
    {
      method: "POST",
      body: formData,
    },
    "Failed to submit complaint."
  );
}

// ============================================================
// AI — HEALTH CHECK
// ============================================================

export async function checkAIHealth() {
  return apiRequest(
    "/ai/health",
    { method: "GET" },
    "AI service unavailable."
  );
}
