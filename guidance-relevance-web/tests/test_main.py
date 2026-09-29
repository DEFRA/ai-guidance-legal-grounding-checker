from guidance_relevance_web.settings import Settings


def test_bind_defaults_localhost(monkeypatch) -> None:
    monkeypatch.delenv("GRF_HOST", raising=False)
    monkeypatch.delenv("GRF_PORT", raising=False)
    settings = Settings(_env_file=None)
    assert settings.grf_host == "127.0.0.1"
    assert settings.grf_port == 8000
    assert settings.grf_llm_mode == "batch"
    assert settings.grf_sync_concurrency == 10


def test_main_uses_host_port(monkeypatch) -> None:
    monkeypatch.setenv("GRF_HOST", "0.0.0.0")
    monkeypatch.setenv("GRF_PORT", "9000")
    seen: dict = {}

    def fake_run(*_args, **kwargs) -> None:
        seen.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)
    from guidance_relevance_web.__main__ import main

    main()
    assert seen["host"] == "0.0.0.0"
    assert seen["port"] == 9000
    assert seen["factory"] is True
