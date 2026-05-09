"""Jinja2 HTML renderer for tearsheets."""
from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"


def render(tearsheet: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(["html"]))
    return env.get_template("tearsheet.html.j2").render(ts=tearsheet)
