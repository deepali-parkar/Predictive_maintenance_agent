"""Renders docs/architecture.png (matplotlib)."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
fig, ax = plt.subplots(figsize=(15, 9.5)); ax.set_xlim(0, 100); ax.set_ylim(0, 64); ax.axis("off")
def box(x, y, w, h, t, c="#dbeafe", ec="#1e40af", fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8", fc=c, ec=ec, lw=1.3)); ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=fs)
def arrow(x1, y1, x2, y2, t=""):
    ax.annotate("", (x2, y2), (x1, y1), arrowprops=dict(arrowstyle="-|>", color="#374151", lw=1.2))
    if t: ax.text((x1 + x2) / 2 + .5, (y1 + y2) / 2, t, fontsize=7, color="#374151")
ax.text(50, 62.5, "SENTINEL - Predictive Maintenance Agent (Assist -> Act)", ha="center", fontsize=14, weight="bold")
box(2, 54, 16, 5, "Synthetic / unseen\nsensor CSV", "#fef3c7", "#b45309"); box(22, 54, 16, 5, "Dataset Adapter\nmapping, units, QC", "#fef3c7", "#b45309")
box(42, 54, 16, 5, "SQLite ingestion\n(canonical schema)", "#dcfce7", "#15803d"); box(62, 54, 16, 5, "Deterministic detection\nz-score / slope / thresholds", "#fee2e2", "#b91c1c"); box(82, 54, 16, 5, "Risk Engine\nLOW / MEDIUM / HIGH", "#fee2e2", "#b91c1c")
for a, b in ((18, 22), (38, 42), (58, 62), (78, 82)): arrow(a, 56.5, b, 56.5)
box(28, 41, 44, 8, "SQLite  data/maintenance.db  (single operational source of truth)\nassets | sensor_readings | risk_events | maintenance_history\nwork_orders | spare_parts | audit_log | model_call_logs", "#dcfce7", "#15803d", 8)
arrow(50, 54, 50, 48.2); box(2, 42, 22, 6, "Streamlit dashboard\nOverview | Asset Details (Plotly)\nAI Assistant | Work Orders", "#e0e7ff", "#4338ca"); arrow(30, 45, 24, 45)
box(76, 42, 22, 6, "Maintenance app\nrepositories + services\n(transactions, audit)", "#dcfce7", "#15803d"); arrow(70, 45, 76, 45)
ax.text(2, 38, "User clicks 'Explain Risk' -> LangGraph agent", fontsize=10, weight="bold", color="#4338ca")
y = 31; w = 11.2; gap = 0.9; names = ["initialize", "MCP context\n(7 tools)", "evidence\npreparation", "RAG retrieval\nChromaDB", "MODEL ROUTER\n(risk + complexity)", "LLM analysis\n(Azure Foundry)", "maintenance\ndecision"]
cols = ["#e0e7ff"] * 4 + ["#fde68a"] + ["#e0e7ff"] * 2
for i, n in enumerate(names):
    x = 2 + i * (w + gap); box(x, y, w, 5, n, cols[i], "#4338ca", 8)
    if i: arrow(x - gap, y + 2.5, x, y + 2.5)
box(2, 20, 11.2, 5, "draft generation\n(+ check_spares)", "#e0e7ff", "#4338ca"); box(15, 20, 11.2, 5, "draft validation\n(schema, refs, parts)", "#e0e7ff", "#4338ca"); box(28, 20, 14, 5, "MCP create_draft_\nwork_order (DRAFT only)", "#e0e7ff", "#4338ca"); box(44, 20, 11.2, 5, "finalize", "#e0e7ff", "#4338ca")
arrow(2 + 6 * (w + gap) + 5, 31, 8, 25.2, "CREATE_DRAFT"); arrow(13.2, 22.5, 15, 22.5); arrow(26.2, 22.5, 28, 22.5); arrow(42, 22.5, 44, 22.5)
ax.text(46, 17.6, "MONITOR / INSPECT_FIRST / INSUFFICIENT_EVIDENCE -> finalize (no draft)", fontsize=7.5, color="#6b7280")
box(60, 20, 18, 5, "Azure AI Foundry\nopen model (LOW) | frontier (MED/HIGH, escalations)", "#fde68a", "#b45309", 7.5); box(80, 20, 18, 5, "ChromaDB  data/chroma\nmanuals | historical WOs | embeddings", "#fce7f3", "#be185d", 7.5)
box(2, 6, 30, 8, "Planner review (human-in-the-loop)\nEdit / Approve / Reject DRAFT\nAgent can NEVER approve or execute", "#fee2e2", "#b91c1c"); arrow(49, 20, 17, 14.4); ax.text(33, 16.4, "draft awaits planner", fontsize=7.5, color="#374151"); ax.text(3, 7.0, "writes status + audit_log to SQLite", fontsize=7.5, color="#7f1d1d")
box(40, 6, 28, 8, "MCP server (FastMCP, stdio)\nread tools + create_draft only\nrole permissions, audit, no raw SQL", "#dbeafe", "#1e40af"); box(72, 6, 26, 8, "Evaluation\nprecision/recall/lead time (held-out 20%)\nRAG, agent, routing cost vs frontier-only", "#f3f4f6", "#4b5563", 8)
plt.savefig("docs/architecture.png", dpi=130, bbox_inches="tight")
