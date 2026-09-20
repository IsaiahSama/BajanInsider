"""Startup tests: CWD-independent imports and the FastAPI lifespan hooks."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")

import pytest
from fastapi.testclient import TestClient

from app import main as app_main

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"


def _import_app_main(cwd: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT),
        "MONGODB_URL": "mongodb://localhost:27017",
        "GEMINI_API_KEY": "test",
    }
    return subprocess.run(
        [sys.executable, "-c", "import app.main; print('imported')"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("cwd_name", ["repo_root", "tmp_dir", "app_dir"])
def test_import_app_main_is_independent_of_cwd(tmp_path: Path, cwd_name: str):
    cwd = {"repo_root": REPO_ROOT, "tmp_dir": tmp_path, "app_dir": APP_DIR}[cwd_name]

    result = _import_app_main(cwd)

    assert result.returncode == 0, result.stderr
    assert "imported" in result.stdout


def test_base_dir_points_at_the_app_package():
    assert app_main.BASE_DIR == APP_DIR
    assert (app_main.BASE_DIR / "public").is_dir()
    assert (app_main.BASE_DIR / "templates").is_dir()


def test_no_deprecated_on_event_hooks_registered():
    assert getattr(app_main.app.router, "on_startup", []) == []
    assert getattr(app_main.app.router, "on_shutdown", []) == []


def test_lifespan_runs_startup_hooks_exactly_once():
    # Patches are entered before TestClient, so the lifespan sees the mocks.
    with (
        patch.object(app_main, "update_sitemap_lastmod") as sitemap_mock,
        patch.object(
            app_main.client, "ensure_indexes", new_callable=AsyncMock
        ) as indexes_mock,
        TestClient(app_main.app),
    ):
        sitemap_mock.assert_called_once_with()
        indexes_mock.assert_awaited_once_with()

    # Shutdown must not run the startup work a second time.
    sitemap_mock.assert_called_once_with()
    indexes_mock.assert_awaited_once_with()


def test_lifespan_survives_index_creation_failure():
    with (
        patch.object(app_main, "update_sitemap_lastmod"),
        patch.object(
            app_main.client,
            "ensure_indexes",
            new_callable=AsyncMock,
            side_effect=ConnectionError("mongo is down"),
        ) as indexes_mock,
        TestClient(app_main.app) as http,
    ):
        indexes_mock.assert_awaited_once_with()
        # The web tier is still up even though the index creation failed.
        assert http.get("/public/sitemap.xml").status_code == 200


def test_lifespan_survives_sitemap_failure():
    with (
        patch.object(
            app_main, "update_sitemap_lastmod", side_effect=OSError("read-only fs")
        ),
        patch.object(
            app_main.client, "ensure_indexes", new_callable=AsyncMock
        ) as indexes_mock,
        TestClient(app_main.app),
    ):
        indexes_mock.assert_awaited_once_with()
