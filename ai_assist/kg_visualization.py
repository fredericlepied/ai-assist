"""Knowledge graph visualization using vis.js"""

import json
import webbrowser

from .config import get_config_dir
from .knowledge_graph import Entity, KnowledgeGraph

ENTITY_TYPE_STYLES = {
    "dci_job": {"color": "#e74c3c", "shape": "box"},
    "dci_component": {"color": "#3498db", "shape": "diamond"},
    "component": {"color": "#3498db", "shape": "diamond"},
    "jira_ticket": {"color": "#f39c12", "shape": "triangle"},
    "user_preference": {"color": "#2ecc71", "shape": "dot"},
    "lesson_learned": {"color": "#9b59b6", "shape": "star"},
    "project_context": {"color": "#1abc9c", "shape": "hexagon"},
    "decision_rationale": {"color": "#e67e22", "shape": "square"},
}

_DEFAULT_STYLE = {"color": "#95a5a6", "shape": "dot"}


def _get_entity_label(entity: Entity) -> str:
    """Extract a short label from an entity's data"""
    data = entity.data

    # Jira tickets: use key
    if "key" in data and entity.entity_type in ("jira_ticket",):
        return data["key"]

    # Components: type + version
    if "type" in data and "version" in data:
        return f"{data['type']} {data['version']}"

    # Jobs with status: prefix + status
    if "status" in data:
        return f"{entity.entity_type}: {data['status']}"

    # Fallback: last 16 chars of entity ID
    return entity.id[-16:]


def generate_kg_html(kg: KnowledgeGraph) -> str:
    """Generate an interactive HTML visualization of the knowledge graph"""
    entities = kg.get_all_current_entities()
    relationships = kg.get_all_current_relationships()

    if not entities and not relationships:
        return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Knowledge Graph</title>
<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#1a1a2e;color:#e0e0e0;}
.msg{text-align:center;}.msg h1{font-size:2em;margin-bottom:0.5em;}.msg p{color:#888;}</style>
</head><body><div class="msg"><h1>Knowledge Graph is empty</h1><p>No entities or relationships stored yet.</p></div></body></html>"""

    # Build nodes
    nodes = []
    for entity in entities:
        style = ENTITY_TYPE_STYLES.get(entity.entity_type, _DEFAULT_STYLE)
        label = _get_entity_label(entity)
        tooltip = f"ID: {entity.id}\\nType: {entity.entity_type}\\nData: {json.dumps(entity.data, default=str)}"
        nodes.append(
            {
                "id": entity.id,
                "label": label,
                "title": tooltip,
                "color": style["color"],
                "shape": style["shape"],
                "group": entity.entity_type,
            }
        )

    # Build edges
    edges = []
    entity_ids = {e.id for e in entities}
    for rel in relationships:
        # Only include edges where both endpoints exist
        if rel.source_id in entity_ids and rel.target_id in entity_ids:
            tooltip = f"Type: {rel.rel_type}\\nProperties: {json.dumps(rel.properties, default=str)}"
            edges.append(
                {
                    "from": rel.source_id,
                    "to": rel.target_id,
                    "label": rel.rel_type,
                    "title": tooltip,
                    "arrows": "to",
                }
            )

    entity_count = len(entities)
    rel_count = len(relationships)

    # Build legend HTML
    legend_items = []
    # Only show types that exist in the data
    seen_types = {e.entity_type for e in entities}
    for etype, style in ENTITY_TYPE_STYLES.items():
        if etype in seen_types:
            legend_items.append(f'<span style="color:{style["color"]};margin-right:16px;">' f"&#9679; {etype}</span>")

    legend_html = " ".join(legend_items)

    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Knowledge Graph Visualization</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
body {{ margin: 0; font-family: sans-serif; background: #1a1a2e; color: #e0e0e0; }}
#stats {{ padding: 10px 20px; background: #16213e; border-bottom: 1px solid #0f3460; font-size: 14px; }}
#legend {{ padding: 8px 20px; background: #0f3460; font-size: 13px; }}
#graph {{ width: 100%; height: calc(100vh - 80px); }}
</style>
</head>
<body>
<div id="stats">{entity_count} entities | {rel_count} relationships</div>
<div id="legend">{legend_html}</div>
<div id="graph"></div>
<script>
var nodes = new vis.DataSet({nodes_json});
var edges = new vis.DataSet({edges_json});
var container = document.getElementById("graph");
var data = {{ nodes: nodes, edges: edges }};
var options = {{
    physics: {{
        solver: "barnesHut",
        barnesHut: {{ gravitationalConstant: -3000, springLength: 150 }}
    }},
    interaction: {{ hover: true, tooltipDelay: 200 }},
    edges: {{ font: {{ size: 10, color: "#888" }}, color: {{ color: "#555", highlight: "#aaa" }} }},
    nodes: {{ font: {{ color: "#e0e0e0" }} }}
}};
var network = new vis.Network(container, data, options);
</script>
</body>
</html>"""


def open_kg_visualization(kg: KnowledgeGraph) -> str:
    """Generate and open knowledge graph visualization in the browser

    Returns:
        Path to the generated HTML file
    """
    html = generate_kg_html(kg)
    filepath = get_config_dir() / "kg_visualization.html"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(html)
    webbrowser.open(f"file://{filepath}")
    return str(filepath)
