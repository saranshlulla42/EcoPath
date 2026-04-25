"use client";

export function MigrationLegend() {
  return (
    <div className="migration-legend">
      <div className="legend-title">Map guide</div>
      <div className="legend-subtitle">eBird observation proxy</div>

      <div className="legend-section-title">Traffic density</div>
      <div className="legend-body">
        <div className="legend-gradient" />
        <div className="legend-scale">
          <span>High</span>
          <span>Medium</span>
          <span>Low</span>
        </div>
      </div>

      <div className="legend-items">
        <div className="legend-item">
          <span className="legend-arrow">
            <svg width="12" height="14" viewBox="0 0 64 64" aria-hidden="true">
              <polygon points="32,4 52,52 32,40 12,52" fill="currentColor" />
            </svg>
          </span>
          <span>Movement direction</span>
        </div>
        <div className="legend-item">
          <span className="legend-line" />
          <span>Sunrise / sunset line</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot legend-dot-active" />
          <span>Active observation cluster</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot legend-dot-inactive" />
          <span>Inactive cluster</span>
        </div>
      </div>
    </div>
  );
}
