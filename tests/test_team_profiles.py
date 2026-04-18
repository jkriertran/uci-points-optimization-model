import pytest

from uci_points_model import team_profiles as module


def test_load_team_archetypes_contains_expected_keys() -> None:
    catalog = module.load_team_archetypes()

    assert "balanced_opportunist" in catalog
    assert "classic_sprint_opportunist" in catalog
    assert catalog["classic_sprint_opportunist"]["label"] == "Classics + Sprint Opportunist"
    assert catalog["classic_sprint_opportunist"]["strength_weight_prior"]["sprint_bonus"] == 0.3


def test_load_team_profile_by_path_reads_json_object(tmp_path) -> None:
    profile_path = tmp_path / "demo_profile.json"
    profile_path.write_text('{"archetype_key":"balanced_opportunist"}')

    profile = module.load_team_profile_by_path(profile_path)

    assert profile["archetype_key"] == "balanced_opportunist"


def test_validate_team_profile_fills_catalog_label_and_description() -> None:
    profile = _base_profile()
    profile["archetype_key"] = "classic_sprint_opportunist"

    validated = module.validate_team_profile(profile, module.load_team_archetypes())

    assert validated["archetype_label"] == "Classics + Sprint Opportunist"
    assert "sprint-accessible" in validated["archetype_description"]


def test_validate_team_profile_rejects_bad_weight_sum() -> None:
    profile = _base_profile()
    profile["strength_weights"]["one_day"] = 0.6

    with pytest.raises(ValueError, match="sum to about 1.0"):
        module.validate_team_profile(profile, module.load_team_archetypes())


def test_validate_team_profile_rejects_unknown_archetype() -> None:
    profile = _base_profile()
    profile["archetype_key"] = "mystery_team_type"

    with pytest.raises(ValueError, match="Unknown archetype_key"):
        module.validate_team_profile(profile, module.load_team_archetypes())


def test_validate_team_profile_rejects_invalid_confidence_enum() -> None:
    profile = _base_profile()
    profile["profile_confidence"] = "certain"

    with pytest.raises(ValueError, match="profile_confidence"):
        module.validate_team_profile(profile, module.load_team_archetypes())


def test_infer_archetype_matches_unibet_like_profile() -> None:
    archetype_key = module.infer_archetype(
        {
            "strength_weights": {
                "one_day": 0.30,
                "stage_hunter": 0.15,
                "gc": 0.10,
                "time_trial": 0.05,
                "all_round": 0.15,
                "sprint_bonus": 0.25,
            }
        }
    )

    assert archetype_key == "classic_sprint_opportunist"


def test_strength_weights_table_returns_stable_axis_order() -> None:
    table = module.strength_weights_table(_base_profile())

    assert table["axis_key"].tolist() == module.TEAM_PROFILE_SIGNAL_KEYS
    assert set(table.columns) == {"axis_key", "Axis", "Weight"}


def test_write_team_profile_json_uses_stable_key_order(tmp_path) -> None:
    profile_path = tmp_path / "profile.json"
    module.write_team_profile_json(
        profile_path,
        {
            "team_name": "Demo Team",
            "strength_weights": _base_profile()["strength_weights"],
            "archetype_key": "balanced_opportunist",
            "profile_version": "v2_optimizer",
            "weight_fit_summary": {"rmse": 4.2, "known_race_count": 12},
        },
    )

    lines = profile_path.read_text().splitlines()

    assert lines[1].strip() == '"team_name": "Demo Team",'
    assert any('"strength_weights": {' in line for line in lines)
    assert any('"weight_fit_summary": {' in line for line in lines)


def _base_profile() -> dict[str, object]:
    return {
        "archetype_key": "balanced_opportunist",
        "execution_rules": {
            "1.1": 0.4,
            "1.Pro": 0.3,
            "1.UWT": 0.18,
            "2.1": 0.3,
            "2.Pro": 0.25,
            "2.UWT": 0.18,
        },
        "participation_rules": {
            "completed": 1.0,
            "program_confirmed": 0.95,
            "observed_startlist": 0.95,
            "calendar_seed": 0.7,
            "overlap_penalty": 0.8,
        },
        "strength_weights": {
            "one_day": 0.2,
            "stage_hunter": 0.15,
            "gc": 0.15,
            "time_trial": 0.1,
            "all_round": 0.2,
            "sprint_bonus": 0.2,
        },
        "team_fit_floor": 0.7,
        "team_fit_range": 0.3,
    }
