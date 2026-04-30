"""AWL workflow visualization using structured block diagrams"""

import html
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .awl_ast import (
    ASTNode,
    FailNode,
    GoalNode,
    IfNode,
    LoopNode,
    NotifyNode,
    ReturnNode,
    SetNode,
    TaskNode,
    WaitNode,
    WhileNode,
    WorkflowNode,
)
from .awl_parser import AWLParser
from .config import get_config_dir
from .introspection_tools import IntrospectionTools

NODE_STYLES = {
    "task": {"color": "#3498db", "bg": "#1a3a5c", "icon": "⚙", "label": "Task"},
    "if": {"color": "#e67e22", "bg": "#5c3a1a", "icon": "⑂", "label": "Condition"},
    "loop": {"color": "#2ecc71", "bg": "#1a5c3a", "icon": "↻", "label": "Loop"},
    "while": {"color": "#27ae60", "bg": "#1a4c2a", "icon": "↺", "label": "While"},
    "wait": {"color": "#95a5a6", "bg": "#3a3a3a", "icon": "⏳", "label": "Wait"},
    "notify": {"color": "#9b59b6", "bg": "#3a1a5c", "icon": "♪", "label": "Notify"},
    "set": {"color": "#1abc9c", "bg": "#1a4c4c", "icon": "←", "label": "Set"},
    "return": {"color": "#2ecc71", "bg": "#1a5c3a", "icon": "↵", "label": "Return"},
    "fail": {"color": "#e74c3c", "bg": "#5c1a1a", "icon": "✘", "label": "Fail"},
    "goal": {"color": "#f1c40f", "bg": "#5c4c1a", "icon": "⚑", "label": "Goal"},
}


def discover_awl_scripts() -> list[Path]:
    """Discover .awl scripts from CWD, config dir, and installed skills."""
    seen: set[Path] = set()
    results: list[Path] = []

    sources = [
        Path.cwd(),
        get_config_dir(),
    ]

    skills_cache = get_config_dir() / "skills-cache"
    if skills_cache.is_dir():
        sources.append(skills_cache)

    for base in sources:
        if not base.is_dir():
            continue
        for awl_file in sorted(base.rglob("*.awl")):
            resolved = awl_file.resolve()
            if resolved not in seen:
                seen.add(resolved)
                results.append(awl_file)

    return results


def _count_tasks(nodes: list[ASTNode]) -> int:
    """Count total TaskNode instances in an AST."""
    count = 0
    for node in nodes:
        if isinstance(node, TaskNode):
            count += 1
        elif isinstance(node, IfNode):
            count += _count_tasks(node.then_body) + _count_tasks(node.else_body)
        elif isinstance(node, (LoopNode, WhileNode, GoalNode)):
            count += _count_tasks(node.body)
    return count


def _truncate(text: str, max_len: int = 120) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _render_node(node: ASTNode) -> str:
    """Render a single AST node to HTML."""
    renderers: dict[type, Callable[[Any], str]] = {
        TaskNode: _render_task,
        IfNode: _render_if,
        LoopNode: _render_loop,
        WhileNode: _render_while,
        GoalNode: _render_goal,
        SetNode: _render_set,
        WaitNode: _render_wait,
        NotifyNode: _render_notify,
        ReturnNode: _render_return,
        FailNode: _render_fail,
    }
    renderer = renderers.get(type(node))
    if renderer:
        return renderer(node)
    return ""


def _render_body(nodes: list[ASTNode]) -> str:
    return "\n".join(_render_node(n) for n in nodes)


def _render_task(node: TaskNode) -> str:
    s = NODE_STYLES["task"]
    hints_html = ""
    if node.hints:
        tags = " ".join(f'<span class="hint-tag">{html.escape(h)}</span>' for h in node.hints)
        hints_html = f'<span class="hints">{tags}</span>'

    limits = []
    if node.max_tool_calls is not None:
        limits.append(f"max_tool_calls={node.max_tool_calls}")
    if node.max_time is not None:
        limits.append(f"max_time={node.max_time}")
    limits_html = ""
    if limits:
        limits_html = f'<span class="limits">{html.escape(", ".join(limits))}</span>'

    expose_html = ""
    if node.expose:
        expose_html = f'<div class="expose">Expose: {html.escape(", ".join(node.expose))}</div>'

    details_parts = []
    if node.goal:
        details_parts.append(f'<div class="detail-field"><strong>Goal:</strong> {html.escape(node.goal)}</div>')
    if node.context:
        details_parts.append(f'<div class="detail-field"><strong>Context:</strong> {html.escape(node.context)}</div>')
    if node.constraints:
        details_parts.append(
            f'<div class="detail-field"><strong>Constraints:</strong> {html.escape(node.constraints)}</div>'
        )
    if node.success:
        details_parts.append(f'<div class="detail-field"><strong>Success:</strong> {html.escape(node.success)}</div>')
    details_html = "\n".join(details_parts)

    goal_preview = html.escape(_truncate(node.goal)) if node.goal else ""

    return f"""<div class="node task-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <div class="node-header clickable" onclick="toggleDetails(this)">
    <span class="node-icon">{s['icon']}</span>
    <span class="node-title">task: {html.escape(node.task_id)}</span>
    {hints_html}{limits_html}
    <span class="expand-icon">▶</span>
  </div>
  <div class="node-summary">{goal_preview}</div>
  {expose_html}
  <div class="node-details collapsed">{details_html}</div>
</div>"""


def _render_if(node: IfNode) -> str:
    s = NODE_STYLES["if"]
    then_html = _render_body(node.then_body) if node.then_body else '<div class="empty-branch">-</div>'

    else_block = ""
    if node.else_body:
        else_body_html = _render_body(node.else_body)
        else_block = f"""<div class="branch else-branch">
      <div class="branch-label" style="color:{s['color']};">else</div>
      {else_body_html}
    </div>"""

    return f"""<div class="node block-node if-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <div class="node-header">
    <span class="node-icon">{s['icon']}</span>
    <span class="node-title">if {html.escape(node.expression)}</span>
  </div>
  <div class="branches">
    <div class="branch then-branch">
      <div class="branch-label" style="color:{s['color']};">then</div>
      {then_html}
    </div>
    {else_block}
  </div>
</div>"""


def _render_loop(node: LoopNode) -> str:
    s = NODE_STYLES["loop"]
    meta_parts = []
    if node.limit is not None:
        meta_parts.append(f"limit={node.limit}")
    if node.collect:
        collect_str = node.collect
        if node.collect_fields:
            collect_str += f"({', '.join(node.collect_fields)})"
        meta_parts.append(f"collect={collect_str}")
    meta = f' <span class="meta">({html.escape(", ".join(meta_parts))})</span>' if meta_parts else ""

    body_html = _render_body(node.body)

    return f"""<div class="node block-node loop-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <div class="node-header">
    <span class="node-icon">{s['icon']}</span>
    <span class="node-title">loop {html.escape(node.collection)} as {html.escape(node.item_var)}{meta}</span>
  </div>
  <div class="block-body">{body_html}</div>
</div>"""


def _render_while(node: WhileNode) -> str:
    s = NODE_STYLES["while"]
    meta = ""
    if node.max_iterations != 100:
        meta = f' <span class="meta">(max_iterations={node.max_iterations})</span>'

    body_html = _render_body(node.body)

    return f"""<div class="node block-node while-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <div class="node-header">
    <span class="node-icon">{s['icon']}</span>
    <span class="node-title">while {html.escape(node.expression)}{meta}</span>
  </div>
  <div class="block-body">{body_html}</div>
</div>"""


def _render_goal(node: GoalNode) -> str:
    s = NODE_STYLES["goal"]
    body_html = _render_body(node.body)

    return f"""<div class="node block-node goal-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <div class="node-header">
    <span class="node-icon">{s['icon']}</span>
    <span class="node-title">goal: {html.escape(node.goal_id)}</span>
    <span class="meta">(max_actions={node.max_actions})</span>
  </div>
  <div class="node-summary">Success: {html.escape(_truncate(node.success_criteria))}</div>
  <div class="block-body">{body_html}</div>
</div>"""


def _render_set(node: SetNode) -> str:
    s = NODE_STYLES["set"]
    return f"""<div class="node inline-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <span class="node-icon">{s['icon']}</span>
  <span class="node-title">set {html.escape(node.variable)} = {html.escape(_truncate(node.value, 80))}</span>
</div>"""


def _render_wait(node: WaitNode) -> str:
    s = NODE_STYLES["wait"]
    seconds = node.duration_seconds
    if seconds >= 3600 and seconds % 3600 == 0:
        dur = f"{seconds // 3600}h"
    elif seconds >= 60 and seconds % 60 == 0:
        dur = f"{seconds // 60}m"
    else:
        dur = f"{seconds}s"
    return f"""<div class="node inline-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <span class="node-icon">{s['icon']}</span>
  <span class="node-title">wait {dur}</span>
</div>"""


def _render_notify(node: NotifyNode) -> str:
    s = NODE_STYLES["notify"]
    return f"""<div class="node inline-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <span class="node-icon">{s['icon']}</span>
  <span class="node-title">notify: {html.escape(_truncate(node.message, 80))}</span>
</div>"""


def _render_return(node: ReturnNode) -> str:
    s = NODE_STYLES["return"]
    return f"""<div class="node inline-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <span class="node-icon">{s['icon']}</span>
  <span class="node-title">return {html.escape(node.expression)}</span>
</div>"""


def _render_fail(node: FailNode) -> str:
    s = NODE_STYLES["fail"]
    return f"""<div class="node inline-node" style="border-left-color:{s['color']}; background:{s['bg']};">
  <span class="node-icon">{s['icon']}</span>
  <span class="node-title">fail: {html.escape(_truncate(node.message, 80))}</span>
</div>"""


def generate_awl_html(workflow: WorkflowNode, title: str = "AWL Workflow") -> str:
    """Generate an interactive HTML visualization of an AWL workflow."""
    if not workflow.body:
        return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>AWL Workflow</title>
<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#1a1a2e;color:#e0e0e0;}
.msg{text-align:center;}.msg h1{font-size:2em;margin-bottom:0.5em;}.msg p{color:#888;}</style>
</head><body><div class="msg"><h1>Empty Workflow</h1><p>This AWL script has no directives.</p></div></body></html>"""

    task_count = _count_tasks(workflow.body)
    input_vars = IntrospectionTools._awl_input_variables(workflow)
    input_vars_str = ", ".join(sorted(input_vars)) if input_vars else "none"
    max_steps_str = str(workflow.max_steps) if workflow.max_steps else "default"

    body_html = _render_body(workflow.body)

    legend_items = []
    for _key, style in NODE_STYLES.items():
        legend_items.append(
            f'<span class="legend-item"><span class="legend-dot" style="color:{style["color"]};">'
            f'●</span> {style["label"]}</span>'
        )
    legend_html = " ".join(legend_items)

    escaped_title = html.escape(title)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{escaped_title} - AWL Visualization</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; }}
#header {{ padding: 12px 24px; background: #16213e; border-bottom: 1px solid #0f3460; display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }}
#header h1 {{ margin: 0; font-size: 18px; font-weight: 600; }}
#header .stat {{ font-size: 13px; color: #888; }}
#header .stat strong {{ color: #b0b0b0; }}
#legend {{ padding: 8px 24px; background: #0f3460; font-size: 13px; display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }}
.legend-item {{ display: inline-flex; align-items: center; gap: 4px; }}
.legend-dot {{ font-size: 14px; }}
.legend-btn {{ background: #1a2a4e; color: #b0b0b0; border: 1px solid #2a3a5e; border-radius: 4px; padding: 3px 10px; font-size: 12px; cursor: pointer; margin-left: auto; }}
.legend-btn:hover {{ background: #2a3a5e; color: #e0e0e0; }}
.legend-btn + .legend-btn {{ margin-left: 0; }}
#workflow {{ max-width: 1400px; margin: 24px auto; padding: 0 24px 48px; }}
.node {{ margin: 8px 0; border-radius: 6px; border-left: 4px solid; padding: 10px 14px; }}
.inline-node {{ display: flex; align-items: center; gap: 8px; padding: 8px 14px; }}
.block-node {{ padding: 10px 14px 14px; }}
.node-header {{ display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 500; }}
.node-header.clickable {{ cursor: pointer; }}
.node-header.clickable:hover {{ opacity: 0.85; }}
.node-icon {{ font-size: 16px; flex-shrink: 0; }}
.node-title {{ flex: 1; }}
.expand-icon {{ font-size: 10px; color: #666; transition: transform 0.2s; }}
.expanded .expand-icon {{ transform: rotate(90deg); }}
.node-summary {{ font-size: 12px; color: #999; margin-top: 4px; padding-left: 24px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.expose {{ font-size: 12px; color: #7fb3d8; margin-top: 4px; padding-left: 24px; }}
.hint-tag {{ font-size: 10px; background: #2a2a4a; color: #aaa; padding: 1px 6px; border-radius: 3px; margin-left: 4px; }}
.limits {{ font-size: 11px; color: #888; margin-left: 8px; }}
.meta {{ font-size: 12px; color: #888; font-weight: 400; }}
.node-details {{ padding: 8px 24px; font-size: 13px; line-height: 1.6; }}
.node-details.collapsed {{ display: none; }}
.detail-field {{ margin-bottom: 6px; }}
.detail-field strong {{ color: #b0b0b0; }}
.branches {{ margin-top: 8px; }}
.branch {{ margin-bottom: 8px; }}
.branch-label {{ font-size: 12px; font-weight: 600; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }}
.else-branch {{ border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 8px; }}
.block-body {{ margin-top: 8px; padding-left: 8px; border-left: 2px solid rgba(255,255,255,0.08); }}
.empty-branch {{ font-size: 12px; color: #555; padding: 8px; }}
</style>
</head>
<body>
<div id="header">
  <h1>{escaped_title}</h1>
  <span class="stat"><strong>{task_count}</strong> tasks</span>
  <span class="stat">Inputs: <strong>{html.escape(input_vars_str)}</strong></span>
  <span class="stat">Max steps: <strong>{html.escape(max_steps_str)}</strong></span>
</div>
<div id="legend">{legend_html}<button class="legend-btn" onclick="expandAll()">Expand all</button><button class="legend-btn" onclick="collapseAll()">Collapse all</button></div>
<div id="workflow">{body_html}</div>
<script>
function toggleDetails(header) {{
  var node = header.closest('.node');
  var details = node.querySelector('.node-details');
  if (!details) return;
  var collapsed = details.classList.toggle('collapsed');
  node.classList.toggle('expanded', !collapsed);
}}
function expandAll() {{
  document.querySelectorAll('.node-details.collapsed').forEach(function(d) {{
    d.classList.remove('collapsed');
    d.closest('.node').classList.add('expanded');
  }});
}}
function collapseAll() {{
  document.querySelectorAll('.node-details:not(.collapsed)').forEach(function(d) {{
    d.classList.add('collapsed');
    d.closest('.node').classList.remove('expanded');
  }});
}}
</script>
</body>
</html>"""


def open_awl_visualization(script_path: str) -> str:
    """Parse an AWL script and open its visualization in the browser.

    Returns:
        Path to the generated HTML file
    """
    path = Path(script_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    source = path.read_text()
    workflow = AWLParser(source).parse()
    title = path.name

    html_content = generate_awl_html(workflow, title)
    filepath = get_config_dir() / "awl_visualization.html"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(html_content)
    webbrowser.open(f"file://{filepath}")
    return str(filepath)
