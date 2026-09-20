"""Tests for ``app.services.misc.update_sitemap_lastmod``."""

import logging
import os
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")

from app.services.misc import DEFAULT_SITEMAP_PATH, update_sitemap_lastmod

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACKED_SITEMAP = REPO_ROOT / "app" / "public" / "sitemap.xml"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def test_default_sitemap_path_is_resolved_relative_to_the_package():
    assert DEFAULT_SITEMAP_PATH == TRACKED_SITEMAP
    assert DEFAULT_SITEMAP_PATH.is_file()


def test_update_sitemap_lastmod_sets_today_and_preserves_namespace(tmp_path: Path):
    original = TRACKED_SITEMAP.read_bytes()
    target = tmp_path / "sitemap.xml"
    shutil.copy(TRACKED_SITEMAP, target)

    update_sitemap_lastmod(target)

    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    root = ET.parse(target).getroot()
    ns = {"sitemap": SITEMAP_NS}
    lastmods = root.findall("sitemap:url/sitemap:lastmod", ns)
    assert lastmods, "sitemap should still contain <lastmod> elements"
    assert all(lastmod.text == today for lastmod in lastmods)

    # Other fields survive the rewrite.
    loc = root.find("sitemap:url/sitemap:loc", ns)
    changefreq = root.find("sitemap:url/sitemap:changefreq", ns)
    assert loc is not None and loc.text == "https://bajaninsider.onrender.com/"
    assert changefreq is not None and changefreq.text == "daily"

    # The default namespace is written back without an ns0: prefix.
    raw = target.read_text(encoding="utf-8")
    assert f'xmlns="{SITEMAP_NS}"' in raw
    assert "ns0" not in raw
    assert raw.lstrip().startswith("<?xml")

    # The tracked copy in the repo must not have been touched.
    assert TRACKED_SITEMAP.read_bytes() == original


def test_update_sitemap_lastmod_missing_file_warns_instead_of_raising(
    tmp_path: Path, caplog
):
    missing = tmp_path / "does-not-exist.xml"
    caplog.set_level(logging.WARNING, logger="app.services.misc")

    update_sitemap_lastmod(missing)  # must not raise

    assert not missing.exists()
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert str(missing) in caplog.text
