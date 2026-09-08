import React, { useEffect, useState, useRef } from "react";
import "./RegionModal.css";
import { INDIAN_STATES } from "../utils/constants";

const REGION_KEY = "civicpulse_region";

export function getSavedRegion() {
  return localStorage.getItem(REGION_KEY) || null;
}

export function saveRegion(region) {
  if (region) {
    localStorage.setItem(REGION_KEY, region);
  } else {
    localStorage.removeItem(REGION_KEY);
  }
}

/*
 * RegionModal (Now acting as State Modal)
 */
function RegionModal({ onComplete }) {
  const [selected, setSelected] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [animateIn, setAnimateIn] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    setAnimateIn(true);
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  function handleConfirm() {
    const region = selected.trim();
    if (!region) return;

    saveRegion(region);
    onComplete(region);
  }

  function handleSkip() {
    onComplete(null);
  }

  const isValid = selected.length > 0;

  return (
    <div className={`region-overlay ${animateIn ? "region-overlay--in" : ""}`}>

      <div className="region-modal">

        {/* Icon */}
        <div className="region-modal__icon">
          <span>📍</span>
        </div>


        {/* Header */}
        <div className="region-modal__header">
          <h2>Where are you from?</h2>
          <p>
            We'll show you civic issues reported in your area so
            you can stay informed and take action locally.
          </p>
        </div>


        {/* Selector */}
        <div className="region-modal__body">
          <div className="region-modal__field region-custom-select-group" ref={dropdownRef}>
            <label htmlFor="region-state-trigger">
              SELECT YOUR STATE
            </label>

            <button
              type="button"
              id="region-state-trigger"
              className={`region-select-trigger ${isOpen ? "open" : ""} ${!selected ? "placeholder" : ""}`}
              onClick={() => setIsOpen((prev) => !prev)}
              aria-haspopup="listbox"
              aria-expanded={isOpen}
            >
              <span>{selected || "— Choose a state —"}</span>
              <svg
                className={`region-chevron ${isOpen ? "rotated" : ""}`}
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

            {isOpen && (
              <ul className="region-select-menu" role="listbox">
                {INDIAN_STATES.map((state) => (
                  <li
                    key={state}
                    role="option"
                    aria-selected={selected === state}
                    className={`region-select-option ${selected === state ? "selected" : ""}`}
                    onClick={() => {
                      setSelected(state);
                      setIsOpen(false);
                    }}
                  >
                    {state}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>


        {/* Actions */}
        <div className="region-modal__actions">
          <button
            type="button"
            className="region-modal__btn region-modal__btn--skip"
            onClick={handleSkip}
          >
            Skip for now
          </button>

          <button
            type="button"
            className="region-modal__btn region-modal__btn--confirm"
            disabled={!isValid}
            onClick={handleConfirm}
          >
            <span>📍</span> Set My State
          </button>
        </div>

      </div>

    </div>
  );
}

export default RegionModal;

