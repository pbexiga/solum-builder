import pytest

from solum.sim.engine import (
    Plot,
    SimError,
    SimResult,
    prepare_netlist,
    singular_nodes,
    stuck_at,
)


def test_prepare_netlist_appends_end_and_drops_star_hash_lines() -> None:
    lines = prepare_netlist("title\n*# echo hi\n  *#\n* normal comment\nR1 a 0 1k\n")
    assert lines == ["title", "* normal comment", "R1 a 0 1k", ".end"]


def test_prepare_netlist_keeps_existing_end() -> None:
    assert prepare_netlist("t\nR1 a 0 1k\n.END\n")[-1] == ".END"


def test_prepare_netlist_rejects_control_blocks() -> None:
    with pytest.raises(SimError, match=r"\.control block"):
        prepare_netlist("t\n.control\nshell rm -rf /\n.endc\n.end")


def test_prepare_netlist_rejects_empty() -> None:
    with pytest.raises(SimError, match="empty"):
        prepare_netlist("  \n*#\n")


def test_prepare_netlist_rejects_repeated_analysis_kinds() -> None:
    with pytest.raises(SimError, match="Run one ac analysis per simulation"):
        prepare_netlist("t\n.op\n.ac dec 5 10 1k\n.AC lin 1 100 100\n.tran 1u 1m")


def test_plot_lookup_by_kind() -> None:
    result = SimResult(plots=[Plot(n, {}) for n in ("tran2", "op2", "ac12")])
    assert [p.kind for p in result.plots] == ["tran", "op", "ac"]
    assert result.plot("ac").name == "ac12"
    with pytest.raises(KeyError, match="no dc plot"):
        result.plot("dc")


def test_sim_error_keeps_log() -> None:
    err = SimError("The simulation failed.", ["stderr Error: x"])
    assert str(err) == "The simulation failed."
    assert err.log == ["stderr Error: x"]
    assert SimError("x").log == []


def test_singular_nodes_from_the_log() -> None:
    log = [
        "stderr Warning: singular matrix:  check node c16_2",
        "stderr Warning: Dynamic gmin stepping failed",
        "stderr Warning: singular matrix:  check node R1_1",
        "stderr Warning: singular matrix:  check node c16_2",
    ]
    assert singular_nodes(log) == ["c16_2", "R1_1"]
    assert singular_nodes(["stdout all fine"]) == []


def test_where_a_failed_run_got_stuck() -> None:
    """D-345: ngspice 44.2's own lines (a latch of absurd transistors): the device or node
    it names on a too-small time step wins over the nodes it stars as not settled."""
    table = [
        "stdout Last Node Voltages",
        "stdout Node                                   Last Voltage        Previous Iter",
        "stdout ----                                   ------------        -------------",
        "stdout a                                                 0         9.88476e+233 *",
        "stdout c                                                 0         9.88476e+233 *",
        "stdout v1#branch                                         0                    9 *",
        "stdout b                                                 9                    9",
    ]
    trouble = (
        "stderr doAnalyses: TRAN:  Timestep too small; initial timepoint: "
        "trouble with dx-instance d1"
    )
    assert stuck_at([*table, trouble]) == ["d1"]
    assert stuck_at(table) == ["a", "c"]  # the branch current and the settled node left out
    node = (
        'stderr Error: Timestep too small; time = 0.01, timestep = 1e-17: trouble with node "xu1.5"'
    )
    assert stuck_at([node, node]) == ["xu1.5"]
    assert stuck_at(["stderr Timestep too small; cause unrecorded.", "stdout all fine"]) == []
