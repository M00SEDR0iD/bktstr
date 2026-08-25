from bktstr.server import CAPABILITIES


def test_server_entrypoint_runs_only_the_fastapi_factory(monkeypatch):
    # Break caught: the compatibility entrypoint could restore a second HTTP stack.
    from bktstr import server

    calls = []
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    server.main()

    assert calls == [
        (
            ("bktstr.api.app:create_app",),
            {"factory": True, "host": "0.0.0.0", "port": 8123},
        )
    ]


def test_capabilities_v035_contract():
    assert CAPABILITIES["version"]=="0.3.5"
    assert "sentiment_fragility" in CAPABILITIES["regime"]["fields"]
    assert CAPABILITIES["sentiment"]["data_profiles"]["default"]=="clean"
    assert CAPABILITIES["cache"]["derived"]["strategy_decisions_cached"] is False


def test_capabilities_publish_registered_strategy_neutral_contracts():
    research_variables = CAPABILITIES["research_variables"]
    assert research_variables["tiers"]["B"]["immutable"] is True
    assert set(research_variables["tiers"]["B"]["examples"]) >= {
        "regime",
        "sentiment",
        "fragility",
    }
    assert research_variables["automatic_backfill"] is False
    assert CAPABILITIES["strategies"]["baseline"]["id"] == "bktstr.bearish-regime-scalp"
    assert (
        CAPABILITIES["strategies"]["baseline"]["execution_model"]
        == "bktstr.next-bar-open"
    )


def test_v035_release_metadata_contract():
    from bktstr.server import CAPABILITIES

    release = CAPABILITIES["release"]
    assert release["feature_formula_versions"] == {
        "intraday": "intraday-v1",
        "regime": "regime-v1",
        "sentiment": "sentiment-v0.3.3",
    }
    assert release["derived_cache_format_version"] == "derived-frame-cache-v1"
    assert set(release["build"]) == {
        "git_commit", "git_branch", "git_repo", "deployment_id", "build_time"
    }


def test_health_payload_includes_runtime_build_identity(monkeypatch):
    from bktstr import server

    monkeypatch.setenv("BKTSTR_GIT_COMMIT", "acceptance-sha")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "main")
    payload = server.health_payload()

    assert payload["status"] == "ok"
    assert payload["version"] == "0.3.5"
    assert payload["git_commit"] == "acceptance-sha"
    assert payload["git_branch"] == "main"
