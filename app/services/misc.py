# This file serves to store small utility functions used across the application.
import xml.etree.ElementTree as ET
from datetime import datetime


def update_sitemap_lastmod():
    """
    Updates the 'lastmod' date in the sitemap.xml file to the current date.
    """
    sitemap_path = "public/sitemap.xml"

    # Register namespace to avoid issues with writing the file
    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")

    tree = ET.parse(sitemap_path)
    root = tree.getroot()

    # The namespace is important for finding the elements
    namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    for url in root.findall("sitemap:url", namespace):
        lastmod = url.find("sitemap:lastmod", namespace)
        if lastmod is not None:
            lastmod.text = datetime.now().strftime("%Y-%m-%d")

    tree.write(sitemap_path, xml_declaration=True, encoding="UTF-8")
