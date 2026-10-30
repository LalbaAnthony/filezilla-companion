import xml.etree.ElementTree as ET
from typing import List

from filezilla_companion.commands.base import Context
from filezilla_companion.filezilla.server import Server
from filezilla_companion.filezilla.sitemanager import SiteManager


def make_context(servers: List[Server]) -> Context:
    """Return a Context over the servers, backed by an in-memory site manager that is never saved."""
    return Context(SiteManager("sitemanager.xml", ET.ElementTree(ET.Element("FileZilla3")), servers))
