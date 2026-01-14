"""Tests for diagram generation module.

Tests cover:
- DiagramNode dataclass
- MeasureShape enum
- Measure extraction from cadences
- Mermaid diagram generation
- DOT diagram generation
- SVG rendering (with mocked subprocess)
- File saving (with mocked filesystem/subprocess)
- Text printing
"""

import io
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from cadence import Cadence, Score, note
from cadence.diagram import (
    DiagramNode,
    MeasureShape,
    _extract_measures,
    print_cadence,
    render_svg,
    save_diagram,
    to_dot,
    to_mermaid,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class DiagramTestScore(Score):
    """Score for diagram tests."""
    value: str = ""
    flag: bool = True


@pytest.fixture
def diagram_score() -> DiagramTestScore:
    """Provide a fresh score for each test."""
    score = DiagramTestScore()
    score.__post_init__()
    return score


# Sample notes for building cadences
@note
async def note_a(score: DiagramTestScore) -> None:
    """First note."""
    score.value += "A"


@note
async def note_b(score: DiagramTestScore) -> None:
    """Second note."""
    score.value += "B"


@note
async def note_c(score: DiagramTestScore) -> None:
    """Third note."""
    score.value += "C"


def is_flag_true(score: DiagramTestScore) -> bool:
    """Condition for branching."""
    return score.flag


# =============================================================================
# Test: DiagramNode Dataclass
# =============================================================================


class TestDiagramNode:
    """Tests for DiagramNode dataclass."""

    def test_basic_creation(self):
        """DiagramNode should be creatable with required fields."""
        node = DiagramNode(
            id="test_id",
            label="Test Label",
            measure_type="single",
            shape=MeasureShape.SINGLE,
        )

        assert node.id == "test_id"
        assert node.label == "Test Label"
        assert node.measure_type == "single"
        assert node.shape == MeasureShape.SINGLE

    def test_default_children(self):
        """DiagramNode should default children to empty list."""
        node = DiagramNode(
            id="test",
            label="Test",
            measure_type="single",
            shape=MeasureShape.SINGLE,
        )

        assert node.children == []

    def test_default_branches(self):
        """DiagramNode should default branches to empty dict."""
        node = DiagramNode(
            id="test",
            label="Test",
            measure_type="single",
            shape=MeasureShape.SINGLE,
        )

        assert node.branches == {}

    def test_with_children(self):
        """DiagramNode should accept children list."""
        child = DiagramNode(
            id="child",
            label="Child",
            measure_type="task",
            shape=MeasureShape.SINGLE,
        )
        parent = DiagramNode(
            id="parent",
            label="Parent",
            measure_type="parallel",
            shape=MeasureShape.PARALLEL,
            children=[child],
        )

        assert len(parent.children) == 1
        assert parent.children[0].id == "child"

    def test_with_branches(self):
        """DiagramNode should accept branches dict."""
        true_branch = DiagramNode(
            id="true_node",
            label="True",
            measure_type="task",
            shape=MeasureShape.SINGLE,
        )
        node = DiagramNode(
            id="branch",
            label="Branch",
            measure_type="branch",
            shape=MeasureShape.BRANCH,
            branches={"true": [true_branch], "false": []},
        )

        assert len(node.branches["true"]) == 1
        assert node.branches["false"] == []


# =============================================================================
# Test: MeasureShape Enum
# =============================================================================


class TestMeasureShape:
    """Tests for MeasureShape enum."""

    def test_single_shape(self):
        """SINGLE should be rectangle."""
        assert MeasureShape.SINGLE.value == "rectangle"

    def test_parallel_shape(self):
        """PARALLEL should be parallelogram."""
        assert MeasureShape.PARALLEL.value == "parallelogram"

    def test_sequence_shape(self):
        """SEQUENCE should be rectangle."""
        assert MeasureShape.SEQUENCE.value == "rectangle"

    def test_branch_shape(self):
        """BRANCH should be diamond."""
        assert MeasureShape.BRANCH.value == "diamond"

    def test_child_shape(self):
        """CHILD should be subroutine."""
        assert MeasureShape.CHILD.value == "subroutine"


# =============================================================================
# Test: Measure Extraction
# =============================================================================


class TestMeasureExtraction:
    """Tests for _extract_measures function."""

    def test_extract_single_measure(self, diagram_score: DiagramTestScore):
        """Should extract single measures."""
        cadence = Cadence("single_test", diagram_score).then("single_note", note_a)

        nodes = _extract_measures(cadence)

        assert len(nodes) == 1
        assert nodes[0].measure_type == "single"
        assert nodes[0].label == "single_note"
        assert nodes[0].shape == MeasureShape.SINGLE

    def test_extract_parallel_measure(self, diagram_score: DiagramTestScore):
        """Should extract parallel measures with children."""
        cadence = Cadence("parallel_test", diagram_score).sync(
            "parallel_notes", [note_a, note_b]
        )

        nodes = _extract_measures(cadence)

        assert len(nodes) == 1
        assert nodes[0].measure_type == "parallel"
        assert nodes[0].shape == MeasureShape.PARALLEL
        assert len(nodes[0].children) == 2

    def test_extract_sequence_measure(self, diagram_score: DiagramTestScore):
        """Should extract sequence measures with children."""
        cadence = Cadence("sequence_test", diagram_score).sequence(
            "seq_notes", [note_a, note_b, note_c]
        )

        nodes = _extract_measures(cadence)

        assert len(nodes) == 1
        assert nodes[0].measure_type == "sequence"
        assert nodes[0].shape == MeasureShape.SEQUENCE
        assert len(nodes[0].children) == 3

    def test_extract_branch_measure(self, diagram_score: DiagramTestScore):
        """Should extract branch measures with both branches."""
        cadence = Cadence("branch_test", diagram_score).split(
            "branch_decision",
            is_flag_true,
            [note_a],
            [note_b],
        )

        nodes = _extract_measures(cadence)

        assert len(nodes) == 1
        assert nodes[0].measure_type == "branch"
        assert nodes[0].shape == MeasureShape.BRANCH
        assert "true" in nodes[0].branches
        assert "false" in nodes[0].branches
        assert len(nodes[0].branches["true"]) == 1
        assert len(nodes[0].branches["false"]) == 1

    def test_extract_child_measure(self, diagram_score: DiagramTestScore):
        """Should extract child cadence measures."""
        child_score = DiagramTestScore()
        child_score.__post_init__()
        child_cadence = Cadence("inner", child_score).then("inner_note", note_a)

        def merge(parent: DiagramTestScore, child: DiagramTestScore) -> None:
            parent.value = child.value

        cadence = Cadence("parent_test", diagram_score).child(
            "child_step", child_cadence, merge
        )

        nodes = _extract_measures(cadence)

        assert len(nodes) == 1
        assert nodes[0].measure_type == "child"
        assert nodes[0].shape == MeasureShape.CHILD
        # Child nodes extracted from inner cadence
        assert len(nodes[0].children) == 1

    def test_extract_multiple_measures(self, diagram_score: DiagramTestScore):
        """Should extract multiple measures in order."""
        cadence = (
            Cadence("multi_test", diagram_score)
            .then("first", note_a)
            .then("second", note_b)
            .then("third", note_c)
        )

        nodes = _extract_measures(cadence)

        assert len(nodes) == 3
        assert nodes[0].label == "first"
        assert nodes[1].label == "second"
        assert nodes[2].label == "third"

    def test_extract_empty_cadence(self, diagram_score: DiagramTestScore):
        """Should return empty list for cadence with no measures."""
        cadence = Cadence("empty_test", diagram_score)

        nodes = _extract_measures(cadence)

        assert nodes == []


# =============================================================================
# Test: Mermaid Diagram Generation
# =============================================================================


class TestMermaidGeneration:
    """Tests for to_mermaid function."""

    def test_basic_mermaid(self, diagram_score: DiagramTestScore):
        """Should generate basic Mermaid flowchart."""
        cadence = Cadence("basic", diagram_score).then("step", note_a)

        mermaid = to_mermaid(cadence)

        assert "flowchart TD" in mermaid
        assert "START([basic])" in mermaid
        assert "[step]" in mermaid
        assert "END([End])" in mermaid

    def test_mermaid_direction(self, diagram_score: DiagramTestScore):
        """Should respect direction parameter."""
        cadence = Cadence("lr_test", diagram_score).then("step", note_a)

        mermaid = to_mermaid(cadence, direction="LR")

        assert "flowchart LR" in mermaid

    def test_mermaid_theme(self, diagram_score: DiagramTestScore):
        """Should add theme initialization."""
        cadence = Cadence("theme_test", diagram_score).then("step", note_a)

        mermaid = to_mermaid(cadence, theme="dark")

        assert "%%{init: {'theme': 'dark'}}%%" in mermaid

    def test_mermaid_parallel_fork_join(self, diagram_score: DiagramTestScore):
        """Should create fork/join for parallel measures."""
        cadence = Cadence("parallel", diagram_score).sync("fork", [note_a, note_b])

        mermaid = to_mermaid(cadence)

        assert "_fork" in mermaid
        assert "_join" in mermaid
        assert "{{parallel:" in mermaid

    def test_mermaid_branch_yes_no(self, diagram_score: DiagramTestScore):
        """Should create yes/no branches."""
        cadence = Cadence("branch", diagram_score).split(
            "decision", is_flag_true, [note_a], [note_b]
        )

        mermaid = to_mermaid(cadence)

        assert "-->|Yes|" in mermaid
        assert "-->|No|" in mermaid
        assert "_merge" in mermaid

    def test_mermaid_sequence_chain(self, diagram_score: DiagramTestScore):
        """Should chain sequence tasks with arrows."""
        cadence = Cadence("sequence", diagram_score).sequence(
            "steps", [note_a, note_b]
        )

        mermaid = to_mermaid(cadence)

        # Should have arrows connecting tasks
        assert "-->" in mermaid

    def test_mermaid_child_subroutine(self, diagram_score: DiagramTestScore):
        """Should use subroutine syntax for child cadences."""
        child_score = DiagramTestScore()
        child_score.__post_init__()
        child = Cadence("inner", child_score).then("inner_step", note_a)

        def merge(parent: DiagramTestScore, child: DiagramTestScore) -> None:
            pass

        cadence = Cadence("outer", diagram_score).child("nested", child, merge)

        mermaid = to_mermaid(cadence)

        # Subroutine syntax: [[label]]
        assert "[[" in mermaid
        assert "]]" in mermaid

    def test_mermaid_complex_workflow(self, diagram_score: DiagramTestScore):
        """Should handle complex multi-step workflows."""
        cadence = (
            Cadence("complex", diagram_score)
            .then("first", note_a)
            .sync("parallel_step", [note_a, note_b])
            .split("decision", is_flag_true, [note_a], [note_b])
            .then("final", note_c)
        )

        mermaid = to_mermaid(cadence)

        # Should have all elements
        assert "START" in mermaid
        assert "END" in mermaid
        assert "fork" in mermaid
        assert "decision" in mermaid


# =============================================================================
# Test: DOT Diagram Generation
# =============================================================================


class TestDotGeneration:
    """Tests for to_dot function."""

    def test_basic_dot(self, diagram_score: DiagramTestScore):
        """Should generate basic DOT digraph."""
        cadence = Cadence("basic", diagram_score).then("step", note_a)

        dot = to_dot(cadence)

        assert "digraph cadence {" in dot
        assert "rankdir=TB" in dot
        assert 'START [label="basic"' in dot
        assert 'END [label="End"' in dot

    def test_dot_rankdir(self, diagram_score: DiagramTestScore):
        """Should respect rankdir parameter."""
        cadence = Cadence("lr_test", diagram_score).then("step", note_a)

        dot = to_dot(cadence, rankdir="LR")

        assert "rankdir=LR" in dot

    def test_dot_colors(self, diagram_score: DiagramTestScore):
        """Should respect color parameters."""
        cadence = Cadence("color_test", diagram_score).then("step", note_a)

        dot = to_dot(cadence, node_color="#FF0000", edge_color="#00FF00")

        assert "#FF0000" in dot
        assert "#00FF00" in dot

    def test_dot_parallel_subgraph(self, diagram_score: DiagramTestScore):
        """Should create subgraph for parallel measures."""
        cadence = Cadence("parallel", diagram_score).sync("fork", [note_a, note_b])

        dot = to_dot(cadence)

        assert "subgraph cluster_" in dot
        assert 'label="parallel"' in dot

    def test_dot_branch_diamond(self, diagram_score: DiagramTestScore):
        """Should use diamond shape for branch."""
        cadence = Cadence("branch", diagram_score).split(
            "decision", is_flag_true, [note_a], [note_b]
        )

        dot = to_dot(cadence)

        assert "shape=diamond" in dot
        assert '[label="Yes"]' in dot
        assert '[label="No"]' in dot

    def test_dot_child_box3d(self, diagram_score: DiagramTestScore):
        """Should use box3d shape for child cadences."""
        child_score = DiagramTestScore()
        child_score.__post_init__()
        child = Cadence("inner", child_score).then("inner_step", note_a)

        def merge(parent: DiagramTestScore, child: DiagramTestScore) -> None:
            pass

        cadence = Cadence("outer", diagram_score).child("nested", child, merge)

        dot = to_dot(cadence)

        assert "shape=box3d" in dot


# =============================================================================
# Test: SVG Rendering (Mocked)
# =============================================================================


class TestSvgRendering:
    """Tests for render_svg function with mocked subprocess."""

    def test_render_svg_dot_success(self, diagram_score: DiagramTestScore):
        """Should call dot command for SVG rendering."""
        cadence = Cadence("test", diagram_score).then("step", note_a)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="<svg>test</svg>")

            result = render_svg(cadence)

            mock_run.assert_called_once()
            args = mock_run.call_args
            assert args[0][0] == ["dot", "-Tsvg"]

    def test_render_svg_mermaid_success(self, diagram_score: DiagramTestScore):
        """Should call mmdc command for Mermaid rendering."""
        cadence = Cadence("test", diagram_score).then("step", note_a)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="<svg>mermaid</svg>")

            result = render_svg(cadence, format="mermaid")

            mock_run.assert_called_once()
            args = mock_run.call_args
            assert "mmdc" in args[0][0]

    def test_render_svg_dot_not_found(self, diagram_score: DiagramTestScore):
        """Should raise RuntimeError when dot not found."""
        cadence = Cadence("test", diagram_score).then("step", note_a)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("dot not found")

            with pytest.raises(RuntimeError, match="Graphviz.*not found"):
                render_svg(cadence)

    def test_render_svg_mermaid_not_found(self, diagram_score: DiagramTestScore):
        """Should raise RuntimeError when mmdc not found."""
        cadence = Cadence("test", diagram_score).then("step", note_a)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("mmdc not found")

            with pytest.raises(RuntimeError, match="mermaid-cli.*not found"):
                render_svg(cadence, format="mermaid")


# =============================================================================
# Test: Save Diagram (Mocked)
# =============================================================================


class TestSaveDiagram:
    """Tests for save_diagram function."""

    def test_save_mermaid_file(self, diagram_score: DiagramTestScore, tmp_path):
        """Should save Mermaid code to .mmd file."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.mmd"

        save_diagram(cadence, str(filepath))

        content = filepath.read_text()
        assert "flowchart" in content

    def test_save_mermaid_extension(self, diagram_score: DiagramTestScore, tmp_path):
        """Should recognize .mermaid extension."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.mermaid"

        save_diagram(cadence, str(filepath))

        content = filepath.read_text()
        assert "flowchart" in content

    def test_save_dot_file(self, diagram_score: DiagramTestScore, tmp_path):
        """Should save DOT code to .dot file."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.dot"

        save_diagram(cadence, str(filepath))

        content = filepath.read_text()
        assert "digraph" in content

    def test_save_gv_extension(self, diagram_score: DiagramTestScore, tmp_path):
        """Should recognize .gv extension."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.gv"

        save_diagram(cadence, str(filepath))

        content = filepath.read_text()
        assert "digraph" in content

    def test_save_svg_file(self, diagram_score: DiagramTestScore, tmp_path):
        """Should render and save SVG file."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.svg"

        with patch("cadence.diagram.render_svg") as mock_render:
            mock_render.return_value = "<svg>test</svg>"

            save_diagram(cadence, str(filepath))

            mock_render.assert_called_once()

    def test_save_png_file(self, diagram_score: DiagramTestScore, tmp_path):
        """Should call dot for PNG output."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.png"

        with patch("subprocess.run") as mock_run:
            save_diagram(cadence, str(filepath))

            mock_run.assert_called_once()
            args = mock_run.call_args
            assert "-Tpng" in args[0][0]

    def test_save_pdf_file(self, diagram_score: DiagramTestScore, tmp_path):
        """Should call dot for PDF output."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.pdf"

        with patch("subprocess.run") as mock_run:
            save_diagram(cadence, str(filepath))

            mock_run.assert_called_once()
            args = mock_run.call_args
            assert "-Tpdf" in args[0][0]

    def test_save_unknown_format(self, diagram_score: DiagramTestScore, tmp_path):
        """Should raise ValueError for unknown format."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.xyz"

        with pytest.raises(ValueError, match="Unknown format"):
            save_diagram(cadence, str(filepath))

    def test_save_graphviz_not_found(self, diagram_score: DiagramTestScore, tmp_path):
        """Should raise RuntimeError when graphviz not found for PNG/PDF."""
        cadence = Cadence("test", diagram_score).then("step", note_a)
        filepath = tmp_path / "test.png"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("dot not found")

            with pytest.raises(RuntimeError, match="Graphviz.*not found"):
                save_diagram(cadence, str(filepath))


# =============================================================================
# Test: Print Cadence
# =============================================================================


class TestPrintCadence:
    """Tests for print_cadence function."""

    def test_print_single_measure(self, diagram_score: DiagramTestScore):
        """Should print single measure with brackets."""
        cadence = Cadence("print_test", diagram_score).then("single_step", note_a)

        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_cadence(cadence)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "=== Cadence: print_test ===" in output
        assert "[single_step]" in output

    def test_print_parallel_measure(self, diagram_score: DiagramTestScore):
        """Should print parallel measure with symbol."""
        cadence = Cadence("parallel_print", diagram_score).sync(
            "parallel_step", [note_a, note_b]
        )

        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_cadence(cadence)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "⫘ PARALLEL:" in output

    def test_print_sequence_measure(self, diagram_score: DiagramTestScore):
        """Should print sequence measure with symbol."""
        cadence = Cadence("seq_print", diagram_score).sequence(
            "seq_step", [note_a, note_b]
        )

        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_cadence(cadence)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "▶ SEQUENCE:" in output

    def test_print_branch_measure(self, diagram_score: DiagramTestScore):
        """Should print branch measure with YES/NO."""
        cadence = Cadence("branch_print", diagram_score).split(
            "decision", is_flag_true, [note_a], [note_b]
        )

        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_cadence(cadence)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "◇ BRANCH:" in output
        assert "YES:" in output
        assert "NO:" in output

    def test_print_child_measure(self, diagram_score: DiagramTestScore):
        """Should print child measure with symbol."""
        child_score = DiagramTestScore()
        child_score.__post_init__()
        child = Cadence("inner", child_score).then("inner_step", note_a)

        def merge(parent: DiagramTestScore, child: DiagramTestScore) -> None:
            pass

        cadence = Cadence("child_print", diagram_score).child("nested", child, merge)

        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_cadence(cadence)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "⊞ CHILD FLOW:" in output

    def test_print_complex_workflow(self, diagram_score: DiagramTestScore):
        """Should print complex workflow with tree structure."""
        cadence = (
            Cadence("complex_print", diagram_score)
            .then("first", note_a)
            .sync("parallel", [note_a, note_b])
            .then("last", note_c)
        )

        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_cadence(cadence)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "├──" in output  # Tree prefix
        assert "└──" in output  # Last item prefix

    def test_print_empty_cadence(self, diagram_score: DiagramTestScore):
        """Should handle empty cadence."""
        cadence = Cadence("empty", diagram_score)

        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_cadence(cadence)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "=== Cadence: empty ===" in output
