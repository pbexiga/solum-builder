"""Parity fixtures: real ngspice, and the app page in headless Chromium for `web/solver.js`
(the UI layer's server and browser, D-047)."""

from tests.sim.conftest import engine
from tests.ui.conftest import base_url, browser, browser_errors, js, page

__all__ = ["base_url", "browser", "browser_errors", "engine", "js", "page"]
