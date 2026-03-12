from kade.main import bootstrap_config


def test_bootstrap_loads_planning_tracking_review_configs() -> None:
    cfg = bootstrap_config()

    assert "planning.yaml" in cfg
    assert "tracking.yaml" in cfg
    assert "review.yaml" in cfg


def test_tracking_transition_defaults_are_wired() -> None:
    cfg = bootstrap_config()
    transitions = cfg["tracking.yaml"]["tracking"]["transitions"]

    assert "auto_triggered_to_active" in transitions
    assert "active_execution_states" in transitions
