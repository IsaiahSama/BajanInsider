# This file serves to store small utility functions used across the application.
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .logger import get_logger

logger = get_logger(__name__)

SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"

# app/public/sitemap.xml, resolved from this file so it does not depend on the CWD.
DEFAULT_SITEMAP_PATH = Path(__file__).resolve().parent.parent / "public" / "sitemap.xml"


def update_sitemap_lastmod(sitemap_path: Path | None = None) -> None:
    """Updates the `lastmod` date of every URL in the sitemap to today's date.

    A missing sitemap is logged as a warning and otherwise ignored, so startup
    never fails over it.

    Args:
        sitemap_path (Path | None): The sitemap to rewrite. Defaults to the bundled
            `app/public/sitemap.xml`.
    """
    if sitemap_path is None:
        sitemap_path = DEFAULT_SITEMAP_PATH

    if not sitemap_path.is_file():
        logger.warning(f"Sitemap not found at {sitemap_path}; skipping lastmod update")
        return

    # Register the default namespace so the file is written back with a plain
    # xmlns="..." instead of an ns0: prefix on every element.
    ET.register_namespace("", SITEMAP_NAMESPACE)

    tree = ET.parse(sitemap_path)
    root = tree.getroot()

    # The namespace is important for finding the elements
    namespace = {"sitemap": SITEMAP_NAMESPACE}
    today = datetime.now().astimezone().strftime("%Y-%m-%d")

    for url in root.findall("sitemap:url", namespace):
        lastmod = url.find("sitemap:lastmod", namespace)
        if lastmod is not None:
            lastmod.text = today

    tree.write(sitemap_path, xml_declaration=True, encoding="UTF-8")
    logger.info(f"Updated sitemap lastmod to {today} in {sitemap_path}")
