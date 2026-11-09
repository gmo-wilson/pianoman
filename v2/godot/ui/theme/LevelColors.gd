## Fallback palette for levels without a colour in the manifest (cycles: index = (level - 1) % size).
extends RefCounted

const COLORS := [
	"#38bdf8", "#0284c7", "#059669", "#10b981", "#f59e0b", "#d97706", "#f43f5e", "#a855f7",
	"#22c55e", "#fb923c", "#64748b", "#f472b6", "#1e293b", "#b45309", "#ec4899", "#e11d48",
	"#8b5cf6", "#0d9488", "#6366f1", "#eab308", "#38bdf8", "#78716c", "#f8fafc", "#ef4444",
	"#06b6d4", "#facc15", "#818cf8", "#c084fc", "#d97706", "#ec4899", "#fbbf24", "#a855f7",
]
