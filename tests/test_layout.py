"""Oberflächen-Test im echten Browser: Anmeldung und Layout bei drei Fenstergrößen.

Startet docker/server.py lokal (ohne Hermes – der Agent ist dann „nicht erreichbar“, die Oberfläche läuft trotzdem).
Braucht Playwright:  pip install playwright && python -m playwright install chromium
Eigener Browser statt des Playwright-Chromium:  CHROME_PATH=/usr/bin/google-chrome
Screenshots landen in $LAYOUT_SHOTS (falls gesetzt).
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
DOCKER = Path(__file__).resolve().parent.parent / "docker"
PW = "layout-test-passwort"
SIZES = {"desktop": (1500, 920), "mittel": (1100, 800), "handy": (390, 844)}


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "APP_PASSWORD": PW, "COOKIE_SECURE": "false", "HERMES_URL": "http://127.0.0.1:9",
           "DATA_DIR": str(tmp_path_factory.mktemp("data")), "PORT": str(port), "HOST": "127.0.0.1"}
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=DOCKER, env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait(5)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        yield b
        b.close()


def shot(page, name):
    if os.environ.get("LAYOUT_SHOTS"):
        Path(os.environ["LAYOUT_SHOTS"]).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=f"{os.environ['LAYOUT_SHOTS']}/{name}.png")


def logged_in_page(browser, base_url, size, mobile=False):
    ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Content Security Policy" in m.text else None)
    page.goto(base_url + "/")
    assert page.url.endswith("/login")
    shot(page, f"login-{size[0]}")
    page.fill("#pw", PW)
    page.click("#go")
    page.wait_for_url(base_url + "/")
    page.wait_for_function("document.getElementById('sysHermes').textContent !== '…'")
    return ctx, page, errors


def boxes_overlap(a, b):
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


def test_falsches_passwort(browser, base_url):
    page = browser.new_page()
    page.goto(base_url + "/login")
    page.fill("#pw", "falsch")
    page.click("#go")
    page.wait_for_function("document.getElementById('msg').textContent.length > 0")
    assert "falsch" in page.text_content("#msg")
    page.close()


@pytest.mark.parametrize("name", ["mittel", "handy"])
def test_starthinweis_ueberlappt_status_nicht(browser, base_url, name):
    ctx, page, errors = logged_in_page(browser, base_url, SIZES[name], mobile=name == "handy")
    shot(page, name)
    hint = page.locator("#start > div")
    assert hint.is_visible()
    state = page.locator("#state")
    visible = page.evaluate("getComputedStyle(document.getElementById('state')).visibility") == "visible"
    assert not (visible and boxes_overlap(hint.bounding_box(), state.bounding_box()))
    # Reiter im Panel: Text wird nicht abgeschnitten
    clipped = page.evaluate("[...document.querySelectorAll('.tab')].filter(t => t.offsetParent && t.scrollWidth > t.clientWidth + 1).length")
    assert clipped == 0
    # Abmelden ist erreichbar
    assert page.locator("#logoutBtn").count() == 1 and not page.locator("#logoutBtn").get_attribute("hidden")
    assert not errors, errors
    ctx.close()


def test_desktop_mikrofonpegel_sichtbar(browser, base_url):
    ctx, page, errors = logged_in_page(browser, base_url, SIZES["desktop"])
    shot(page, "desktop")
    meter = page.locator(".meter").bounding_box()
    pane = page.locator("#pane-sys").bounding_box()
    assert meter["y"] + meter["height"] <= pane["y"] + pane["height"]      # Pegel steht im sichtbaren Bereich
    assert meter["y"] + meter["height"] <= SIZES["desktop"][1]
    assert not errors, errors
    ctx.close()


def test_abmelden(browser, base_url):
    ctx, page, _ = logged_in_page(browser, base_url, SIZES["mittel"])
    page.evaluate("document.querySelector('.tab[data-tab=sys]').click()")
    page.click("#logoutBtn")
    page.wait_for_url(base_url + "/login")
    page.goto(base_url + "/")
    assert page.url.endswith("/login")
    ctx.close()
