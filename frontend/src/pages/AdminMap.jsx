import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { getGeoComplaints, getRegions } from "../services/apiClient";
import Navbar from "../components/Navbar";
import "./AdminMap.css";


// ============================================================
// CUSTOM MARKER ICONS (color-coded by status)
// ============================================================

function createIcon(color) {
  return L.divIcon({
    className: "map-marker-icon",
    html: `<div style="
      width: 28px;
      height: 28px;
      border-radius: 50% 50% 50% 0;
      background: ${color};
      transform: rotate(-45deg);
      border: 3px solid white;
      box-shadow: 0 3px 10px rgba(0,0,0,0.25);
    "></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -30],
  });
}

const STATUS_ICONS = {
  Pending: createIcon("#e8a838"),
  "In Progress": createIcon("#3b82f6"),
  Resolved: createIcon("#22c55e"),
};

function getMarkerIcon(status) {
  return STATUS_ICONS[status] || STATUS_ICONS.Pending;
}


// ============================================================
// AUTO-FIT MAP BOUNDS
// ============================================================

function FitBounds({ complaints }) {
  const map = useMap();

  useEffect(() => {
    if (complaints.length === 0) return;

    const bounds = L.latLngBounds(
      complaints.map((c) => [c.latitude, c.longitude])
    );

    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
  }, [complaints, map]);

  return null;
}


// ============================================================
// PRIORITY LABEL
// ============================================================

function getPriorityLabel(priority = 0) {
  const value = Number(priority ?? 0);

  if (value >= 5) return "High";
  if (value >= 2) return "Medium";
  return "Low";
}

function getPriorityClass(priority = 0) {
  const value = Number(priority ?? 0);

  if (value >= 5) return "map-priority-high";
  if (value >= 2) return "map-priority-medium";
  return "map-priority-low";
}


// ============================================================
// ADMIN MAP COMPONENT
// ============================================================

function AdminMap() {
  const [complaints, setComplaints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [statusFilter, setStatusFilter] = useState("All");
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [stateFilter, setStateFilter] = useState("All");
  const [availableStates, setAvailableStates] = useState([]);

  // ----------------------------------------------------------
  // LOAD AVAILABLE STATES (from complaints in DB)
  // ----------------------------------------------------------

  useEffect(() => {
    async function loadStates() {
      try {
        const data = await getRegions();
        setAvailableStates(data?.regions || []);
      } catch {
        setAvailableStates([]);
      }
    }
    loadStates();
  }, []);

  // ----------------------------------------------------------
  // LOAD DATA
  // ----------------------------------------------------------

  async function loadComplaints() {
    try {
      setLoading(true);
      setError(null);

      const filters = {};

      if (statusFilter !== "All") {
        filters.status = statusFilter;
      }

      if (categoryFilter !== "All") {
        filters.category = categoryFilter;
      }

      if (stateFilter !== "All") {
        filters.state = stateFilter;
      }

      const data = await getGeoComplaints(filters);

      setComplaints(data || []);
    } catch (err) {
      console.error("Failed to load geo complaints:", err);
      setError("Failed to load map data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadComplaints();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, categoryFilter, stateFilter]);

  // ----------------------------------------------------------
  // CATEGORY OPTIONS
  // ----------------------------------------------------------

  const categoryOptions = useMemo(() => {
    const categories = complaints
      .map((c) => c.category?.trim())
      .filter(Boolean);

    return [...new Set(categories)].sort();
  }, [complaints]);

  // ----------------------------------------------------------
  // STATS
  // ----------------------------------------------------------

  const stats = useMemo(() => {
    return {
      total: complaints.length,
      pending: complaints.filter((c) => c.status === "Pending").length,
      inProgress: complaints.filter((c) => c.status === "In Progress").length,
      resolved: complaints.filter((c) => c.status === "Resolved").length,
    };
  }, [complaints]);

  // ----------------------------------------------------------
  // DEFAULT CENTER (India)
  // ----------------------------------------------------------

  const defaultCenter = [20.5937, 78.9629];
  const defaultZoom = 5;

  // ----------------------------------------------------------
  // RENDER
  // ----------------------------------------------------------

  return (
    <div className="admin-map-page">
      <Navbar />

      {/* HEADER */}
      <header className="admin-map-header">
        <div>
          <span className="admin-map-label">
            CIVICPULSE · ADMINISTRATION
          </span>

          <h1>Issue Map</h1>

          <p>
            View all geolocated civic reports on an
            interactive map. Filter by state to zoom in.
          </p>
        </div>

        <Link
          to="/admin"
          className="admin-map-back"
        >
          ← Back to Dashboard
        </Link>
      </header>

      {/* FILTERS + STATS BAR */}
      <section className="admin-map-toolbar">
        <div className="admin-map-filters">

          {/* STATE FILTER */}
          <div className="admin-map-filter-group">
            <label htmlFor="map-state-filter">
              State
            </label>

            <select
              id="map-state-filter"
              value={stateFilter}
              onChange={(e) =>
                setStateFilter(e.target.value)
              }
            >
              <option value="All">All States</option>

              {availableStates.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          {/* STATUS FILTER */}
          <div className="admin-map-filter-group">
            <label htmlFor="map-status-filter">
              Status
            </label>

            <select
              id="map-status-filter"
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value)
              }
            >
              <option value="All">All</option>
              <option value="Pending">Pending</option>
              <option value="In Progress">
                In Progress
              </option>
              <option value="Resolved">Resolved</option>
            </select>
          </div>

          {/* CATEGORY FILTER */}
          <div className="admin-map-filter-group">
            <label htmlFor="map-category-filter">
              Category
            </label>

            <select
              id="map-category-filter"
              value={categoryFilter}
              onChange={(e) =>
                setCategoryFilter(e.target.value)
              }
            >
              <option value="All">All</option>

              {categoryOptions.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="admin-map-stats">
          <div className="map-stat">
            <strong>{stats.total}</strong>
            <span>Total</span>
          </div>

          <div className="map-stat map-stat-pending">
            <strong>{stats.pending}</strong>
            <span>Pending</span>
          </div>

          <div className="map-stat map-stat-progress">
            <strong>{stats.inProgress}</strong>
            <span>In Progress</span>
          </div>

          <div className="map-stat map-stat-resolved">
            <strong>{stats.resolved}</strong>
            <span>Resolved</span>
          </div>
        </div>
      </section>

      {/* LEGEND */}
      <div className="admin-map-legend">
        <span className="legend-item">
          <span
            className="legend-dot"
            style={{ background: "#e8a838" }}
          />
          Pending
        </span>

        <span className="legend-item">
          <span
            className="legend-dot"
            style={{ background: "#3b82f6" }}
          />
          In Progress
        </span>

        <span className="legend-item">
          <span
            className="legend-dot"
            style={{ background: "#22c55e" }}
          />
          Resolved
        </span>
      </div>

      {/* MAP */}
      {loading ? (
        <div className="admin-map-loading">
          Loading map data…
        </div>
      ) : error ? (
        <div className="admin-map-error">
          {error}
        </div>
      ) : (
        <div className="admin-map-container">
          <MapContainer
            center={defaultCenter}
            zoom={defaultZoom}
            className="admin-map-leaflet"
            scrollWheelZoom={true}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            <FitBounds complaints={complaints} />

            {complaints.map((complaint) => (
              <Marker
                key={complaint.id}
                position={[
                  complaint.latitude,
                  complaint.longitude,
                ]}
                icon={getMarkerIcon(complaint.status)}
              >
                <Popup maxWidth={320}>
                  <div className="map-popup">
                    <div className="map-popup-header">
                      <span
                        className={`map-popup-status map-popup-${complaint.status
                          .toLowerCase()
                          .replace(" ", "-")}`}
                      >
                        {complaint.status}
                      </span>

                      <span
                        className={`map-popup-priority ${getPriorityClass(
                          complaint.priority
                        )}`}
                      >
                        {getPriorityLabel(
                          complaint.priority
                        )}
                      </span>
                    </div>

                    <p className="map-popup-desc">
                      {complaint.description}
                    </p>

                    <div className="map-popup-meta">
                      <span>
                        📁 {complaint.category}
                      </span>

                      {complaint.state && complaint.state !== "Other" && (
                        <span>
                          🗺️ {complaint.state}
                        </span>
                      )}

                      <span>
                        📍 {complaint.location}
                      </span>

                      <span>
                        👍 {complaint.votes} support
                        {complaint.votes !== 1
                          ? "s"
                          : ""}
                      </span>

                      {complaint.location_accuracy && (
                        <span>
                          🎯 ±
                          {Math.round(
                            complaint.location_accuracy
                          )}
                          m accuracy
                        </span>
                      )}
                    </div>

                    <div className="map-popup-id">
                      Report #{complaint.id}
                    </div>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>

          {complaints.length === 0 && (
            <div className="admin-map-empty">
              No geolocated reports found for the
              current filters.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default AdminMap;
