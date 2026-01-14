"""Visual cadence diagram generation.

Generates Mermaid and DOT (Graphviz) diagrams from Cadence definitions.

Example:
    from cadence import Cadence
    from cadence.diagram import to_mermaid, to_dot, render_svg

    cadence = (
        Cadence("checkout", OrderScore)
        .then("validate", validate)
        .sync("enrich", [fetch_user, fetch_inventory])
        .split("route", is_premium, [priority], [standard])
        .then("finalize", finalize)
    )

    # Generate Mermaid diagram
    mermaid_code = to_mermaid(cadence)
    print(mermaid_code)

    # Generate DOT diagram
    dot_code = to_dot(cadence)

    # Render to SVG (requires graphviz)
    svg = render_svg(cadence)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cadence.cadence import Cadence


class MeasureShape(Enum):
    """Shape styles for different measure types."""

    SINGLE = "rectangle"
    PARALLEL = "parallelogram"
    SEQUENCE = "rectangle"
    BRANCH = "diamond"
    CHILD = "subroutine"


@dataclass
class DiagramNode:
    """Represents a measure in the diagram."""

    id: str
    label: str
    measure_type: str
    shape: MeasureShape
    children: list[DiagramNode] | None = None
    branches: dict[str, list[DiagramNode]] | None = None

    def __post_init__(self) -> None:
        if self.children is None:
            self.children = []
        if self.branches is None:
            self.branches = {}


def _extract_measures(cadence: Cadence[Any]) -> list[DiagramNode]:
    """Extract diagram nodes from a cadence."""
    from cadence.nodes.branch import BranchMeasure
    from cadence.nodes.child import ChildCadenceMeasure
    from cadence.nodes.parallel import ParallelMeasure
    from cadence.nodes.sequence import SequenceMeasure
    from cadence.nodes.single import SingleMeasure

    diagram_nodes = []

    for i, measure in enumerate(cadence._measures):
        measure_id = f"measure_{i}"

        if isinstance(measure, SingleMeasure):
            diagram_nodes.append(
                DiagramNode(
                    id=measure_id,
                    label=measure.name,
                    measure_type="single",
                    shape=MeasureShape.SINGLE,
                )
            )

        elif isinstance(measure, ParallelMeasure):
            children = []
            for j, task in enumerate(measure._tasks):
                task_name = getattr(task, "__name__", f"task_{j}")
                # Strip timing wrapper name if present
                if "[" in task_name:
                    task_name = task_name.split("[")[0] + f"[{j}]"
                children.append(
                    DiagramNode(
                        id=f"{measure_id}_task_{j}",
                        label=task_name,
                        measure_type="task",
                        shape=MeasureShape.SINGLE,
                    )
                )
            diagram_nodes.append(
                DiagramNode(
                    id=measure_id,
                    label=measure.name,
                    measure_type="parallel",
                    shape=MeasureShape.PARALLEL,
                    children=children,
                )
            )

        elif isinstance(measure, SequenceMeasure):
            children = []
            for j, task in enumerate(measure._tasks):
                task_name = getattr(task, "__name__", f"task_{j}")
                if "[" in task_name:
                    task_name = task_name.split("[")[0] + f"[{j}]"
                children.append(
                    DiagramNode(
                        id=f"{measure_id}_task_{j}",
                        label=task_name,
                        measure_type="task",
                        shape=MeasureShape.SINGLE,
                    )
                )
            diagram_nodes.append(
                DiagramNode(
                    id=measure_id,
                    label=measure.name,
                    measure_type="sequence",
                    shape=MeasureShape.SEQUENCE,
                    children=children,
                )
            )

        elif isinstance(measure, BranchMeasure):
            condition_name = getattr(measure._condition, "__name__", "condition")

            if_true_nodes = []
            for j, task in enumerate(measure._if_tasks):
                task_name = getattr(task, "__name__", f"if_true_{j}")
                if_true_nodes.append(
                    DiagramNode(
                        id=f"{measure_id}_true_{j}",
                        label=task_name,
                        measure_type="task",
                        shape=MeasureShape.SINGLE,
                    )
                )

            if_false_nodes = []
            for j, task in enumerate(measure._else_tasks):
                task_name = getattr(task, "__name__", f"if_false_{j}")
                if_false_nodes.append(
                    DiagramNode(
                        id=f"{measure_id}_false_{j}",
                        label=task_name,
                        measure_type="task",
                        shape=MeasureShape.SINGLE,
                    )
                )

            diagram_nodes.append(
                DiagramNode(
                    id=measure_id,
                    label=f"{measure.name}\\n({condition_name})",
                    measure_type="branch",
                    shape=MeasureShape.BRANCH,
                    branches={"true": if_true_nodes, "false": if_false_nodes},
                )
            )

        elif isinstance(measure, ChildCadenceMeasure):
            child_nodes = _extract_measures(measure._child_cadence)
            diagram_nodes.append(
                DiagramNode(
                    id=measure_id,
                    label=f"{measure.name}\\n[{measure._child_cadence._name}]",
                    measure_type="child",
                    shape=MeasureShape.CHILD,
                    children=child_nodes,
                )
            )

    return diagram_nodes


def to_mermaid(
    cadence: Cadence[Any],
    *,
    direction: str = "TD",
    theme: str | None = None,
) -> str:
    """
    Generate a Mermaid flowchart from a Cadence.

    Args:
        cadence: The Cadence to diagram
        direction: Diagram direction - TD (top-down), LR (left-right), etc.
        theme: Optional Mermaid theme

    Returns:
        Mermaid diagram code as a string

    Example:
        mermaid = to_mermaid(my_cadence)
        # Use in markdown: ```mermaid\\n{mermaid}\\n```
    """
    nodes = _extract_measures(cadence)
    lines = [f"flowchart {direction}"]

    if theme:
        lines.insert(0, f"%%{{init: {{'theme': '{theme}'}}}}%%")

    # Add start node
    lines.append(f"    START([{cadence._name}])")

    prev_id = "START"

    for node in nodes:
        if node.measure_type == "single":
            lines.append(f"    {node.id}[{node.label}]")
            lines.append(f"    {prev_id} --> {node.id}")
            prev_id = node.id

        elif node.measure_type == "parallel":
            # Create a fork node
            fork_id = f"{node.id}_fork"
            join_id = f"{node.id}_join"
            lines.append(f"    {fork_id}{{{{parallel: {node.label}}}}}")
            lines.append(f"    {prev_id} --> {fork_id}")

            # Add parallel tasks
            for child in node.children or []:
                lines.append(f"    {child.id}[{child.label}]")
                lines.append(f"    {fork_id} --> {child.id}")
                lines.append(f"    {child.id} --> {join_id}")

            lines.append(f"    {join_id}((join))")
            prev_id = join_id

        elif node.measure_type == "sequence":
            # Add sequence tasks in order
            seq_prev = prev_id
            for child in node.children or []:
                lines.append(f"    {child.id}[{child.label}]")
                lines.append(f"    {seq_prev} --> {child.id}")
                seq_prev = child.id
            prev_id = seq_prev

        elif node.measure_type == "branch":
            lines.append(f"    {node.id}{{{node.label}}}")
            lines.append(f"    {prev_id} --> {node.id}")

            # Create merge point
            merge_id = f"{node.id}_merge"
            branches = node.branches or {}

            # True branch
            if branches.get("true"):
                branch_prev = node.id
                for i, child in enumerate(branches["true"]):
                    lines.append(f"    {child.id}[{child.label}]")
                    if i == 0:
                        lines.append(f"    {node.id} -->|Yes| {child.id}")
                    else:
                        lines.append(f"    {branch_prev} --> {child.id}")
                    branch_prev = child.id
                lines.append(f"    {branch_prev} --> {merge_id}")
            else:
                lines.append(f"    {node.id} -->|Yes| {merge_id}")

            # False branch
            if branches.get("false"):
                branch_prev = node.id
                for i, child in enumerate(branches["false"]):
                    lines.append(f"    {child.id}[{child.label}]")
                    if i == 0:
                        lines.append(f"    {node.id} -->|No| {child.id}")
                    else:
                        lines.append(f"    {branch_prev} --> {child.id}")
                    branch_prev = child.id
                lines.append(f"    {branch_prev} --> {merge_id}")
            else:
                lines.append(f"    {node.id} -->|No| {merge_id}")

            lines.append(f"    {merge_id}((merge))")
            prev_id = merge_id

        elif node.measure_type == "child":
            lines.append(f"    {node.id}[[{node.label}]]")
            lines.append(f"    {prev_id} --> {node.id}")
            prev_id = node.id

    # Add end node
    lines.append("    END([End])")
    lines.append(f"    {prev_id} --> END")

    return "\n".join(lines)


def to_dot(
    cadence: Cadence[Any],
    *,
    rankdir: str = "TB",
    node_color: str = "#4A90D9",
    edge_color: str = "#333333",
) -> str:
    """
    Generate a DOT (Graphviz) diagram from a Cadence.

    Args:
        cadence: The Cadence to diagram
        rankdir: Rank direction - TB (top-bottom), LR (left-right)
        node_color: Default node fill color
        edge_color: Edge/arrow color

    Returns:
        DOT diagram code as a string

    Example:
        dot = to_dot(my_cadence)
        # Render with: dot -Tsvg -o cadence.svg
    """
    nodes = _extract_measures(cadence)

    lines = [
        "digraph cadence {",
        f"    rankdir={rankdir};",
        '    node [shape=box, style=filled, fontname="Arial"];',
        f'    edge [color="{edge_color}"];',
        "",
        f'    START [label="{cadence._name}", shape=oval, fillcolor="#90EE90"];',
    ]

    prev_id = "START"

    for node in nodes:
        if node.measure_type == "single":
            lines.append(f'    {node.id} [label="{node.label}", fillcolor="{node_color}"];')
            lines.append(f"    {prev_id} -> {node.id};")
            prev_id = node.id

        elif node.measure_type == "parallel":
            fork_id = f"{node.id}_fork"
            join_id = f"{node.id}_join"

            lines.append(
                f'    {fork_id} [label="{node.label}", shape=parallelogram, fillcolor="#FFD700"];'
            )
            lines.append(f"    {prev_id} -> {fork_id};")

            lines.append(f"    subgraph cluster_{node.id} {{")
            lines.append('        label="parallel";')
            lines.append("        style=dashed;")

            for child in node.children or []:
                lines.append(
                    f'        {child.id} [label="{child.label}", fillcolor="{node_color}"];'
                )
                lines.append(f"        {fork_id} -> {child.id};")
                lines.append(f"        {child.id} -> {join_id};")

            lines.append("    }")
            lines.append(f'    {join_id} [label="join", shape=circle, fillcolor="#D3D3D3"];')
            prev_id = join_id

        elif node.measure_type == "sequence":
            seq_prev = prev_id
            for child in node.children or []:
                lines.append(f'    {child.id} [label="{child.label}", fillcolor="{node_color}"];')
                lines.append(f"    {seq_prev} -> {child.id};")
                seq_prev = child.id
            prev_id = seq_prev

        elif node.measure_type == "branch":
            # Escape newlines for DOT
            label = node.label.replace("\\n", "\\l")
            lines.append(f'    {node.id} [label="{label}", shape=diamond, fillcolor="#FFA500"];')
            lines.append(f"    {prev_id} -> {node.id};")

            merge_id = f"{node.id}_merge"
            branches = node.branches or {}

            # True branch
            if branches.get("true"):
                branch_prev = node.id
                for i, child in enumerate(branches["true"]):
                    lines.append(f'    {child.id} [label="{child.label}", fillcolor="#90EE90"];')
                    if i == 0:
                        lines.append(f'    {node.id} -> {child.id} [label="Yes"];')
                    else:
                        lines.append(f"    {branch_prev} -> {child.id};")
                    branch_prev = child.id
                lines.append(f"    {branch_prev} -> {merge_id};")
            else:
                lines.append(f'    {node.id} -> {merge_id} [label="Yes"];')

            # False branch
            if branches.get("false"):
                branch_prev = node.id
                for i, child in enumerate(branches["false"]):
                    lines.append(f'    {child.id} [label="{child.label}", fillcolor="#FFB6C1"];')
                    if i == 0:
                        lines.append(f'    {node.id} -> {child.id} [label="No"];')
                    else:
                        lines.append(f"    {branch_prev} -> {child.id};")
                    branch_prev = child.id
                lines.append(f"    {branch_prev} -> {merge_id};")
            else:
                lines.append(f'    {node.id} -> {merge_id} [label="No"];')

            lines.append(f'    {merge_id} [label="merge", shape=circle, fillcolor="#D3D3D3"];')
            prev_id = merge_id

        elif node.measure_type == "child":
            label = node.label.replace("\\n", "\\l")
            lines.append(f'    {node.id} [label="{label}", shape=box3d, fillcolor="#DDA0DD"];')
            lines.append(f"    {prev_id} -> {node.id};")
            prev_id = node.id

    # End node
    lines.append('    END [label="End", shape=oval, fillcolor="#FF6347"];')
    lines.append(f"    {prev_id} -> END;")
    lines.append("}")

    return "\n".join(lines)


def render_svg(
    cadence: Cadence[Any],
    *,
    format: str = "dot",
    **kwargs: Any,
) -> str:
    """
    Render a cadence diagram to SVG.

    Requires graphviz to be installed on the system.

    Args:
        cadence: The Cadence to render
        format: Diagram format - "dot" or "mermaid"
        **kwargs: Additional arguments passed to to_dot or to_mermaid

    Returns:
        SVG content as a string

    Raises:
        RuntimeError: If graphviz is not installed
    """
    import subprocess

    if format == "mermaid":
        # Mermaid requires mmdc (mermaid-cli)
        mermaid_code = to_mermaid(cadence, **kwargs)
        try:
            result = subprocess.run(
                ["mmdc", "-i", "-", "-o", "-", "-e", "svg"],
                input=mermaid_code,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except FileNotFoundError as err:
            raise RuntimeError(
                "mermaid-cli (mmdc) not found. Install with: npm install -g @mermaid-js/mermaid-cli"
            ) from err
    else:
        # Default to DOT/Graphviz
        dot_code = to_dot(cadence, **kwargs)
        try:
            result = subprocess.run(
                ["dot", "-Tsvg"],
                input=dot_code,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except FileNotFoundError as err:
            raise RuntimeError(
                "Graphviz (dot) not found. "
                "Install with: brew install graphviz (macOS) or apt install graphviz (Linux)"
            ) from err


def save_diagram(
    cadence: Cadence[Any],
    path: str,
    *,
    format: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Save a cadence diagram to a file.

    Format is auto-detected from file extension:
    - .mmd, .mermaid -> Mermaid code
    - .dot, .gv -> DOT code
    - .svg -> Rendered SVG (requires graphviz)
    - .png -> Rendered PNG (requires graphviz)
    - .pdf -> Rendered PDF (requires graphviz)

    Args:
        cadence: The Cadence to diagram
        path: Output file path
        format: Override auto-detected format
        **kwargs: Additional arguments passed to diagram generators
    """
    import subprocess
    from pathlib import Path

    output_path = Path(path)
    ext = format or output_path.suffix.lower()

    if ext in (".mmd", ".mermaid"):
        content = to_mermaid(cadence, **kwargs)
        output_path.write_text(content)

    elif ext in (".dot", ".gv"):
        content = to_dot(cadence, **kwargs)
        output_path.write_text(content)

    elif ext == ".svg":
        content = render_svg(cadence, **kwargs)
        output_path.write_text(content)

    elif ext in (".png", ".pdf"):
        dot_code = to_dot(cadence, **kwargs)
        try:
            subprocess.run(
                ["dot", f"-T{ext[1:]}", "-o", str(output_path)],
                input=dot_code,
                text=True,
                check=True,
            )
        except FileNotFoundError as err:
            raise RuntimeError("Graphviz (dot) not found.") from err

    else:
        raise ValueError(f"Unknown format: {ext}")


def print_cadence(cadence: Cadence[Any]) -> None:
    """
    Print a text representation of a cadence to stdout.

    Useful for quick debugging.
    """
    nodes = _extract_measures(cadence)
    print(f"\n=== Cadence: {cadence._name} ===\n")

    for i, node in enumerate(nodes):
        prefix = "├──" if i < len(nodes) - 1 else "└──"

        if node.measure_type == "single":
            print(f"{prefix} [{node.label}]")

        elif node.measure_type == "parallel":
            print(f"{prefix} ⫘ PARALLEL: {node.label}")
            children = node.children or []
            for j, child in enumerate(children):
                child_prefix = "│   ├──" if j < len(children) - 1 else "│   └──"
                print(f"{child_prefix} {child.label}")

        elif node.measure_type == "sequence":
            print(f"{prefix} ▶ SEQUENCE: {node.label}")
            children = node.children or []
            for j, child in enumerate(children):
                child_prefix = "│   ├──" if j < len(children) - 1 else "│   └──"
                print(f"{child_prefix} {child.label}")

        elif node.measure_type == "branch":
            print(f"{prefix} ◇ BRANCH: {node.label}")
            branches = node.branches or {}
            if branches.get("true"):
                print("│   ├── YES:")
                for child in branches["true"]:
                    print(f"│   │   └── {child.label}")
            if branches.get("false"):
                print("│   └── NO:")
                for child in branches["false"]:
                    print(f"│       └── {child.label}")

        elif node.measure_type == "child":
            print(f"{prefix} ⊞ CHILD FLOW: {node.label}")

    print()
