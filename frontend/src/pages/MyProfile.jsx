import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getMyComplaints } from "../services/apiClient";
import Navbar from "../components/Navbar";
import "./MyProfile.css";

function MyProfile() {
  const { user } = useAuth();
  const [complaints, setComplaints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchComplaints() {
      try {
        const data = await getMyComplaints();
        setComplaints(data);
      } catch (err) {
        setError("Failed to load your complaints.");
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    
    if (user) {
      fetchComplaints();
    }
  }, [user]);

  if (!user) {
    return (
      <>
        <Navbar />
        <div className="loading">Please log in to view this page.</div>
      </>
    );
  }

  return (
    <>
      <Navbar />
      <div className="my-profile-page">
        <div style={{ marginBottom: "16px" }}>
          <Link to="/" style={{ color: "#065f46", textDecoration: "none", fontWeight: 600, fontSize: "0.9rem" }}>
            ← Back to Home
          </Link>
        </div>
        <div className="profile-header">
        <span className="profile-badge">YOUR REPORTS</span>
        <h1>My Complaints</h1>
        <p>Track the status of every issue you've reported to CivicPulse.</p>
      </div>

      {loading ? (
        <div className="loading">Loading your reports...</div>
      ) : error ? (
        <div className="auth-error">{error}</div>
      ) : complaints.length === 0 ? (
        <div className="empty-state">
          <h3>No complaints yet</h3>
          <p>You haven't reported any issues to CivicPulse yet.</p>
        </div>
      ) : (
        <div className="complaints-list">
          {complaints.map((complaint) => {
            const statusClass = (complaint.status || "pending")
              .toLowerCase()
              .replace(" ", "_");
              
            return (
              <div key={complaint.id} className="complaint-card">
                <div className="card-header">
                  <span className="category">
                    {complaint.category || "General"}
                  </span>
                  <span className={`status-badge ${statusClass}`}>
                    {complaint.status}
                  </span>
                </div>
                
                <h3 className="description">{complaint.description}</h3>
                
                <div className="card-footer">
                  <div className="footer-item">
                    <span>📍</span> {complaint.location}
                  </div>
                  {complaint.state && (
                    <div className="footer-item">
                      <span>🗺️</span> {complaint.state}
                    </div>
                  )}
                  <div className="footer-item">
                    <span>👍</span> {complaint.votes} supports
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
      </div>
    </>
  );
}

export default MyProfile;
