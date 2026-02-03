export function ProjectCard() {
  return (
    <div className="dashboard-card">
      <h3 className="dashboard-card-title">Recent Projects</h3>
      <div className="project-list">
        <div className="project-empty">
          <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Open a .blend, .stl, or .gltf file in the Viewport to see it here.
          </span>
        </div>
      </div>
    </div>
  )
}
