"""Structural invariants that used to be checked only by manual grep."""

from __future__ import annotations

import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "syntalk"


def test_only_gui_module_imports_gi():
    hits = [p for p in SRC.rglob("*.py") if "import gi" in p.read_text()]
    assert hits == [SRC / "gui.py"]


def test_no_hardcoded_default_sample_rate():
    offenders = [p for p in SRC.rglob("*.py") if "22050" in p.read_text()]
    assert offenders == []


def test_gui_imports_headless_with_correct_app_id():
    from syntalk.gui import APP_ID

    assert APP_ID == "nl.syntec.SynTalk"
