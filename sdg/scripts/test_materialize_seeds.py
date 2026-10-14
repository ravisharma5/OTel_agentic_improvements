"""Tests for seed materialization against sdg_hub's real input schema.

materialize_tool_seeds() must produce rows matching sdg_hub==0.9.4's actual
Flow.get_dataset_requirements() for the "MCP Server Distillation" flow --
tool_list / mcp_server_name / mcp_server_description -- not the
scenario-per-row shape originally assumed before sdg_hub was ever installed
and run for real. It must also fail loudly on a tool-name mismatch between
seed-scenarios.yaml and the live gateway, since a silent mismatch there was
the actual root cause of every seed failing to resolve in practice.
"""
from __future__ import annotations

import json

import pytest
import yaml

from sdg.scripts.materialize_seeds import materialize_tool_seeds


@pytest.fixture()
def seed_scenarios_file(tmp_path):
    config = {
        "tiers": {
            "single_tool": {
                "complexity": 1,
                "description": "Single-tool calls",
                "scenarios": [
                    {
                        "name": "single_check_alarms",
                        "tool_subset": ["tmf642listAlarm"],
                        "description": "Check for {severity} alarms",
                        "parameters": {"severity": ["critical"]},
                    },
                ],
            },
            "closed_loop": {
                "complexity": 5,
                "description": "Observe-decide-act cycles",
                "scenarios": [
                    {
                        "name": "closed_loop_example",
                        "tool_subset": ["tmf642listAlarm", "nwdafget_nwdaf_analytics"],
                        "description": "Detect alarm, correlate with analytics",
                        "parameters": {},
                    },
                ],
            },
        }
    }
    path = tmp_path / "seed-scenarios.yaml"
    path.write_text(yaml.dump(config))
    return path


@pytest.fixture()
def live_tools():
    return [
        {"name": "tmf642listAlarm", "description": "List or find Alarm objects", "inputSchema": {"type": "object"}},
        {"name": "nwdafget_nwdaf_analytics", "description": "Get NWDAF analytics", "inputSchema": {"type": "object"}},
    ]


class TestRowShapeMatchesSdgHubContract:
    def test_required_columns_present(self, live_tools, seed_scenarios_file, tmp_path) -> None:
        out_path = tmp_path / "out.jsonl"
        count = materialize_tool_seeds(live_tools, seed_scenarios_file, out_path)
        assert count == 2

        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        for row in rows:
            assert "tool_list" in row
            assert "mcp_server_name" in row
            assert "mcp_server_description" in row
            assert isinstance(row["tool_list"], list)

    def test_tool_list_has_full_resolved_tool_objects(self, live_tools, seed_scenarios_file, tmp_path) -> None:
        out_path = tmp_path / "out.jsonl"
        materialize_tool_seeds(live_tools, seed_scenarios_file, out_path)
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]

        # "critical" suffix: the fixture's single parameter value, substituted
        # into the scenario name -- see TestParameterSubstitution below for
        # the expansion behavior itself.
        single = next(r for r in rows if r["scenario_name"] == "single_check_alarms_critical")
        assert single["tool_list"] == [
            {"name": "tmf642listAlarm", "description": "List or find Alarm objects", "inputSchema": {"type": "object"}}
        ]

        closed = next(r for r in rows if r["scenario_name"] == "closed_loop_example")
        assert len(closed["tool_list"]) == 2
        assert {t["name"] for t in closed["tool_list"]} == {"tmf642listAlarm", "nwdafget_nwdaf_analytics"}

    def test_mcp_server_name_is_scenario_name(self, live_tools, seed_scenarios_file, tmp_path) -> None:
        out_path = tmp_path / "out.jsonl"
        materialize_tool_seeds(live_tools, seed_scenarios_file, out_path)
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        for row in rows:
            assert row["mcp_server_name"] == row["scenario_name"]

    def test_mcp_server_description_grounds_scenario_intent(self, live_tools, seed_scenarios_file, tmp_path) -> None:
        out_path = tmp_path / "out.jsonl"
        materialize_tool_seeds(live_tools, seed_scenarios_file, out_path)
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        single = next(r for r in rows if r["scenario_name"] == "single_check_alarms_critical")
        # The {severity} placeholder must be substituted with the real value,
        # not passed through to the Agent unfilled -- 2026-10-14 live finding:
        # an unfilled "{analytics_type}"-style placeholder was silently
        # reaching Gemini verbatim, which then invented its own values.
        assert "Check for critical alarms" in single["mcp_server_description"]
        assert "{severity}" not in single["mcp_server_description"]


class TestPassthroughTrackingColumns:
    def test_tier_complexity_and_intended_tools_present(self, live_tools, seed_scenarios_file, tmp_path) -> None:
        out_path = tmp_path / "out.jsonl"
        materialize_tool_seeds(live_tools, seed_scenarios_file, out_path)
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]

        single = next(r for r in rows if r["scenario_name"] == "single_check_alarms_critical")
        assert single["tier"] == "single_tool"
        assert single["complexity"] == 1
        assert single["intended_tools"] == ["tmf642listAlarm"]

        closed = next(r for r in rows if r["scenario_name"] == "closed_loop_example")
        assert closed["tier"] == "closed_loop"
        assert closed["complexity"] == 5
        assert closed["intended_tools"] == ["tmf642listAlarm", "nwdafget_nwdaf_analytics"]


class TestParameterSubstitution:
    """2026-10-14: `parameters` was dead code -- materialize_tool_seeds()
    never read it, so every scenario declaring it had its description's
    {placeholder} reach the Agent completely unfilled. Confirmed live this
    was why single_get_nwdaf_analytics kept generating questions about event
    types NextGCore's NWDAF doesn't support (Gemini filled the gap itself
    from the tool's schema instead of the values declared here). Fix expands
    each scenario into one seed row per parameter value (not just one
    filled-in row), since a list of options implies real variation is
    wanted, not a single arbitrary pick."""

    @pytest.fixture()
    def multi_value_scenarios_file(self, tmp_path):
        config = {
            "tiers": {
                "single_tool": {
                    "complexity": 1,
                    "description": "Single-tool calls",
                    "scenarios": [
                        {
                            "name": "single_check_alarms",
                            "tool_subset": ["tmf642listAlarm"],
                            "description": "Check for {severity} alarms",
                            "parameters": {"severity": ["critical", "major", "minor"]},
                        },
                    ],
                },
            }
        }
        path = tmp_path / "seed-scenarios.yaml"
        path.write_text(yaml.dump(config))
        return path

    def test_expands_one_row_per_parameter_value(self, live_tools, multi_value_scenarios_file, tmp_path) -> None:
        out_path = tmp_path / "out.jsonl"
        count = materialize_tool_seeds(live_tools, multi_value_scenarios_file, out_path)
        assert count == 3

        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        names = {r["scenario_name"] for r in rows}
        assert names == {
            "single_check_alarms_critical",
            "single_check_alarms_major",
            "single_check_alarms_minor",
        }

    def test_each_row_has_its_own_substituted_description(
        self, live_tools, multi_value_scenarios_file, tmp_path
    ) -> None:
        out_path = tmp_path / "out.jsonl"
        materialize_tool_seeds(live_tools, multi_value_scenarios_file, out_path)
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]

        by_name = {r["scenario_name"]: r for r in rows}
        assert "Check for critical alarms" in by_name["single_check_alarms_critical"]["mcp_server_description"]
        assert "Check for major alarms" in by_name["single_check_alarms_major"]["mcp_server_description"]
        assert "Check for minor alarms" in by_name["single_check_alarms_minor"]["mcp_server_description"]

    def test_mcp_server_name_matches_scenario_name_per_expanded_row(
        self, live_tools, multi_value_scenarios_file, tmp_path
    ) -> None:
        out_path = tmp_path / "out.jsonl"
        materialize_tool_seeds(live_tools, multi_value_scenarios_file, out_path)
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        for row in rows:
            assert row["mcp_server_name"] == row["scenario_name"]

    def test_no_parameters_produces_single_unsuffixed_row(self, live_tools, tmp_path) -> None:
        """Scenarios without `parameters` (or with an empty dict) must keep
        their plain name, unaffected by this change."""
        config = {
            "tiers": {
                "closed_loop": {
                    "complexity": 5,
                    "description": "Observe-decide-act cycles",
                    "scenarios": [
                        {
                            "name": "closed_loop_example",
                            "tool_subset": ["tmf642listAlarm"],
                            "description": "Detect and remediate",
                        },
                    ],
                },
            }
        }
        path = tmp_path / "seed-scenarios.yaml"
        path.write_text(yaml.dump(config))
        out_path = tmp_path / "out.jsonl"
        count = materialize_tool_seeds(live_tools, path, out_path)
        assert count == 1
        rows = [json.loads(line) for line in out_path.read_text().splitlines()]
        assert rows[0]["scenario_name"] == "closed_loop_example"


class TestFailsLoudOnUnresolvedTool:
    """Regression test: a naming-convention mismatch between seed-scenarios.yaml
    and the live gateway (e.g. tmf642_list_alarms vs. the real tmf642listAlarm)
    once caused every single seed to silently fail resolution. This must raise,
    not emit a placeholder '[NOT FOUND IN GATEWAY]' record."""

    def test_raises_on_tool_not_in_gateway(self, seed_scenarios_file, tmp_path) -> None:
        out_path = tmp_path / "out.jsonl"
        with pytest.raises(ValueError, match="not found in the live gateway"):
            materialize_tool_seeds([], seed_scenarios_file, out_path)

    def test_error_names_the_scenario_and_tool(self, seed_scenarios_file, tmp_path) -> None:
        out_path = tmp_path / "out.jsonl"
        with pytest.raises(ValueError) as exc_info:
            materialize_tool_seeds([], seed_scenarios_file, out_path)
        assert "single_check_alarms" in str(exc_info.value)
        assert "tmf642listAlarm" in str(exc_info.value)

    def test_partial_mismatch_still_raises(self, tmp_path) -> None:
        """One resolvable tool in a scenario's subset isn't enough -- any
        unresolved tool in the set should fail the whole materialization."""
        config = {
            "tiers": {
                "parallel": {
                    "complexity": 2,
                    "description": "x",
                    "scenarios": [
                        {
                            "name": "mixed",
                            "tool_subset": ["tmf642listAlarm", "totally_made_up_tool"],
                            "description": "x",
                            "parameters": {},
                        },
                    ],
                },
            }
        }
        scenarios_path = tmp_path / "seeds.yaml"
        scenarios_path.write_text(yaml.dump(config))
        tools = [{"name": "tmf642listAlarm", "description": "x", "inputSchema": {}}]

        with pytest.raises(ValueError, match="totally_made_up_tool"):
            materialize_tool_seeds(tools, scenarios_path, tmp_path / "out.jsonl")
