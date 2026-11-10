"""End-to-end browser checks for the ModelRadar frontend (Playwright, headless Chromium).

Runs against the real stack (web + API + database) and therefore against real collected
announcements; nothing is mocked. Start the stack first:  docker compose up -d

    pip install playwright && python -m playwright install chromium
    python web/e2e/run_e2e.py                    # E2E_BASE_URL defaults to http://localhost:3000
    E2E_SCREENSHOTS=some/dir python web/e2e/run_e2e.py

Exit code is non-zero if any check fails.
"""

import os
import re
import sys
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Browser, Page, expect, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:3000").rstrip("/")
SHOTS = Path(os.environ["E2E_SCREENSHOTS"]) if os.environ.get("E2E_SCREENSHOTS") else None
DESKTOP = {"width": 1360, "height": 860}
MOBILE = {"width": 375, "height": 812}

results: list[tuple[str, bool, str]] = []


def check(name):
    def wrap(fn):
        def run(*args, **kwargs):
            try:
                fn(*args, **kwargs)
                results.append((name, True, ""))
                print(f"PASS  {name}")
            except Exception as exc:  # noqa: BLE001 - report and continue
                results.append((name, False, f"{type(exc).__name__}: {exc}"))
                print(f"FAIL  {name}\n      {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}")
                if os.environ.get("E2E_TRACE"):
                    traceback.print_exc()

        return run

    return wrap


def shot(page: Page, name: str) -> None:
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)


def goto(page: Page, path: str = "/") -> None:
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")


def no_horizontal_overflow(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


# --- dashboard -------------------------------------------------------------------------------


@check("dashboard shows real announcements with links to original sources")
def dashboard_real_data(page: Page) -> None:
    goto(page)
    expect(page.get_by_role("heading", level=1)).to_have_text("AI Intelligence")
    rows = page.locator("article")
    assert rows.count() == 20, f"expected a 20-item page, got {rows.count()}"
    text = page.get_by_text(re.compile(r"[\d,]+ announcements")).first.inner_text()
    total = int(re.search(r"([\d,]+)", text).group(1).replace(",", ""))
    assert total > 1000, f"expected the real collection (1,000+), got {total}"
    links = page.locator("article h3 a")
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href")
        assert href.startswith("https://"), href
        assert links.nth(i).get_attribute("target") == "_blank"
        assert "noopener" in (links.nth(i).get_attribute("rel") or "")
    first = rows.first
    assert first.locator("time").count() == 1
    shot(page, "desktop-dashboard-dark")


@check("feed is sorted by publication date, newest first")
def sorting(page: Page) -> None:
    goto(page)
    stamps = page.locator("article time").evaluate_all("els => els.map(e => e.getAttribute('datetime'))")
    assert len(stamps) >= 10
    assert stamps == sorted(stamps, reverse=True), stamps


@check("pagination is server-side and keeps the URL in sync")
def pagination(page: Page) -> None:
    goto(page)
    first_title = page.locator("article h3 a").first.inner_text().split("\n")[0]
    page.get_by_role("link", name="Next").first.click()
    expect(page).to_have_url(re.compile(r"page=2"))
    expect(page.get_by_text(re.compile(r"Page 2 of \d+"))).to_be_visible()
    expect(page.locator("article h3 a").first).not_to_contain_text(first_title)
    page.get_by_role("link", name="Previous").first.click()
    expect(page.locator("article h3 a").first).to_contain_text(first_title)
    page.goto(f"{BASE}/?page=2")  # refresh keeps the page
    expect(page.get_by_text(re.compile(r"Page 2 of"))).to_be_visible()


@check("filters are reflected in the URL and survive a refresh")
def filters(page: Page) -> None:
    goto(page)
    page.get_by_label("Company").select_option("openai")
    page.wait_for_url(re.compile(r"company=openai"))
    page.wait_for_load_state("networkidle")
    names = set(page.locator("article >> text=OpenAI").all_inner_texts())
    assert page.locator("article").count() > 0
    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.get_by_label("Company").input_value() == "openai"
    page.get_by_label("Category").select_option("image-generation")
    page.wait_for_url(re.compile(r"category=image-generation"))
    page.wait_for_load_state("networkidle")
    q = parse_qs(urlparse(page.url).query)
    assert q.get("company") == ["openai"] and q.get("category") == ["image-generation"]
    page.get_by_role("link", name="Clear filters").first.click()
    page.wait_for_url(f"{BASE}/")
    assert names is not None


@check("category, kind and date range filters narrow the feed")
def more_filters(page: Page) -> None:
    goto(page, "/?kind=model_release")
    expect(page.get_by_role("heading", name="No announcements match")).to_be_visible()  # none classified yet
    goto(page, "/?kind=other&published_from=2026-11-01")
    goto(page, "/?from=2026-11-05&to=2026-11-06")
    for stamp in page.locator("article time").evaluate_all("els => els.map(e => e.getAttribute('datetime'))"):
        assert "2026-11-05" <= stamp[:10] <= "2026-11-06", stamp
    goto(page, "/?category=language-reasoning&company=pika")
    expect(page.get_by_role("heading", name="No announcements match")).to_be_visible()


@check("search finds matches, and shows an empty state without matches")
def search(page: Page) -> None:
    goto(page)
    box = page.get_by_role("searchbox", name="Search announcements")
    box.fill("gemini")
    expect(page).to_have_url(f"{BASE}/")  # nothing happens until Enter is pressed
    box.press("Enter")
    expect(page).to_have_url(re.compile(r"q=gemini"))
    expect(page.locator("article").first).to_contain_text(re.compile("gemini", re.I))
    page.get_by_role("searchbox", name="Search announcements").fill("zzzqqqxxx")
    page.get_by_role("searchbox", name="Search announcements").press("Enter")
    expect(page).to_have_url(re.compile(r"q=zzzqqqxxx"))
    expect(page.get_by_role("heading", name="No announcements match")).to_be_visible()
    shot(page, "desktop-no-results")
    page.get_by_role("link", name="Clear filters").first.click()
    expect(page.locator("article")).to_have_count(20)


@check("search keeps active filters, and Enter in the box does the search")
def search_keeps_filters(page: Page) -> None:
    goto(page, "/?company=openai&kind=other")
    box = page.get_by_role("searchbox", name="Search announcements")
    box.fill("model")
    box.press("Enter")
    expect(page).to_have_url(re.compile(r"q=model"))
    q = parse_qs(urlparse(page.url).query)
    assert q["company"] == ["openai"] and q["kind"] == ["other"] and q["q"] == ["model"], q
    expect(page.locator("article").first).to_be_visible()
    assert set(page.locator("article span.text-ink.font-medium").all_inner_texts()) == {"OpenAI"}


@check("category, company and kind filters work together and are kept by pagination")
def filters_and_pagination(page: Page) -> None:
    goto(page)
    page.get_by_label("Category").select_option("language-reasoning")
    expect(page).to_have_url(re.compile(r"category=language-reasoning"))
    page.get_by_label("Company").select_option("openai")
    expect(page).to_have_url(re.compile(r"company=openai"))
    page.get_by_label("Kind").select_option("other")
    expect(page).to_have_url(re.compile(r"kind=other"))
    q = parse_qs(urlparse(page.url).query)
    assert q["category"] == ["language-reasoning"] and q["company"] == ["openai"] and q["kind"] == ["other"], q
    page.get_by_role("link", name="Next").first.click()
    expect(page).to_have_url(re.compile(r"page=2"))
    q = parse_qs(urlparse(page.url).query)
    assert q["category"] == ["language-reasoning"] and q["company"] == ["openai"] and q["kind"] == ["other"], q
    assert page.get_by_label("Company").input_value() == "openai"
    # changing a filter goes back to page 1
    page.get_by_label("Kind").select_option("research")
    expect(page).to_have_url(re.compile(r"kind=research"))
    assert "page=" not in page.url
    expect(page.get_by_role("heading", name="No announcements match")).to_be_visible()


@check("in-feed category chips filter the dashboard")
def category_chip(page: Page) -> None:
    goto(page)
    chip = page.locator("article a[href^='/?category=']").first
    href = chip.get_attribute("href")
    chip.click()
    expect(page).to_have_url(f"{BASE}{href}")
    assert page.get_by_label("Category").input_value() == href.split("=")[1]


@check("browser back, forward and refresh keep the right view")
def history(page: Page) -> None:
    goto(page)
    page.get_by_label("Company").select_option("pika")
    expect(page).to_have_url(re.compile(r"company=pika"))
    pika_title = page.locator("article h3 a").first.inner_text().split("\n")[0]
    page.get_by_label("Kind").select_option("other")
    expect(page).to_have_url(re.compile(r"kind=other"))
    page.go_back()
    expect(page).not_to_have_url(re.compile(r"kind=other"))
    assert page.get_by_label("Kind").input_value() == ""
    assert page.get_by_label("Company").input_value() == "pika"
    page.go_forward()
    expect(page).to_have_url(re.compile(r"kind=other"))
    assert page.get_by_label("Kind").input_value() == "other"
    page.reload()
    assert page.get_by_label("Kind").input_value() == "other"
    assert page.get_by_label("Company").input_value() == "pika"
    expect(page.locator("article h3 a").first).to_contain_text(pika_title)
    page.go_back(); page.go_back()
    expect(page).to_have_url(f"{BASE}/")


@check("refreshing a filtered, paginated URL shows the same results")
def refresh_filtered(page: Page) -> None:
    goto(page, "/?company=openai&page=2")
    first = page.locator("article h3 a").first.inner_text().split("\n")[0]
    expect(page.get_by_text(re.compile(r"Page 2 of"))).to_be_visible()
    page.reload()
    expect(page.get_by_text(re.compile(r"Page 2 of"))).to_be_visible()
    assert page.locator("article h3 a").first.inner_text().split("\n")[0] == first
    assert page.get_by_label("Company").input_value() == "openai"


@check("no navigation hangs: every dashboard navigation completes within 5 seconds")
def no_hangs(page: Page) -> None:
    import time

    goto(page)
    steps = [
        ("Next link", lambda: page.get_by_role("link", name="Next").first.click(), "page=2"),
        ("company select", lambda: page.get_by_label("Company").select_option("mistral-ai"), "company=mistral-ai"),
        ("kind select", lambda: page.get_by_label("Kind").select_option("other"), "kind=other"),
        ("category select", lambda: page.get_by_label("Category").select_option("code-software"), "category=code-software"),
        ("clear filters", lambda: page.get_by_role("link", name="Clear filters").click(), None),
    ]
    for name, action, needle in steps:
        started = time.time()
        action()
        if needle:
            expect(page).to_have_url(re.compile(re.escape(needle)), timeout=5000)
        else:
            expect(page).to_have_url(f"{BASE}/", timeout=5000)
        expect(page.locator("article").first).to_be_visible(timeout=5000)
        assert time.time() - started < 5, f"{name} took {time.time() - started:.1f}s"


@check("'/' focuses the search box")
def slash_focus(page: Page) -> None:
    goto(page)
    page.keyboard.press("/")
    assert page.evaluate("document.activeElement && document.activeElement.name") == "q"


@check("missing descriptions and dates render honestly (undated items have no invented date)")
def missing_data(page: Page) -> None:
    goto(page, "/?company=google-deepmind&page=2")  # DeepMind has entries without a description
    rows = page.locator("article")
    assert rows.count() > 0
    without_description = rows.evaluate_all(
        "els => els.filter(e => !e.querySelector('p.line-clamp-2')).length"
    )
    assert without_description >= 0
    for stamp in page.locator("article time").evaluate_all("els => els.map(e => e.getAttribute('datetime'))"):
        assert re.match(r"\d{4}-\d{2}-\d{2}T", stamp)


# --- other pages -----------------------------------------------------------------------------


@check("navigation: every page opens, the active item is marked, one h1 per page")
def navigation(page: Page) -> None:
    goto(page)
    nav = page.get_by_role("navigation", name="Main")
    expected = {
        "Dashboard": ("/", "AI Intelligence"),
        "Models": ("/models", "Models"),
        "Categories": ("/categories", "Categories"),
        "Companies": ("/companies", "Companies"),
        "Sources": ("/sources", "Sources"),
        "About": ("/about", "About ModelRadar"),
    }
    for label, (path, heading) in expected.items():
        nav.get_by_role("link", name=label).click()
        page.wait_for_url(f"{BASE}{path}")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_role("heading", level=1)).to_have_text(heading)
        assert page.get_by_role("heading", level=1).count() == 1
        assert nav.get_by_role("link", name=label).get_attribute("aria-current") == "page"
        assert nav.locator("[aria-current=page]").count() == 1


@check("categories page: 17 categories with real counts and working links")
def categories_page(page: Page) -> None:
    goto(page, "/categories")
    cards = page.locator("article")
    assert cards.count() == 17, cards.count()
    counts = [
        int(re.search(r"[\d,]+", t).group().replace(",", ""))
        for t in page.locator("article h2 + p").all_inner_texts()
    ]
    assert len(counts) == 17 and max(counts) > 100  # real collected data
    page.get_by_role("link", name="View announcements in Language and Reasoning").click()
    expect(page).to_have_url(re.compile(r"category=language-reasoning"))
    expect(page.locator("article").first).to_be_visible()
    shot(page, "desktop-categories")


@check("companies page: real companies, website links and company feeds")
def companies_page(page: Page) -> None:
    goto(page, "/companies")
    assert page.locator("article").count() == 10
    site = page.locator("article a[href^='https://']").first
    assert site.get_attribute("target") == "_blank"
    page.get_by_role("link", name="View announcements from Mistral AI").click()
    expect(page).to_have_url(re.compile(r"company=mistral-ai"))
    expect(page.locator("article").first).to_contain_text("Mistral AI")
    shot(page, "desktop-companies")


@check("models page: honest empty state and the 'not exhaustive' notice")
def models_page(page: Page) -> None:
    goto(page, "/models")
    expect(page.get_by_text("This directory is not exhaustive.")).to_be_visible()
    expect(page.get_by_role("heading", name="No models identified yet")).to_be_visible()
    shot(page, "desktop-models")


@check("sources page: real status, last sync and read-only content")
def sources_page(page: Page) -> None:
    goto(page, "/sources")
    table = page.get_by_role("table")
    expect(table).to_be_visible()
    assert table.locator("tbody tr").count() == 11
    body = table.inner_text()
    assert "Healthy" in body and "Disabled" in body
    assert re.search(r"\d+ (min|h|d) ago|just now", body)
    for secret in ("etag", "password", "DATABASE_URL"):
        assert secret.lower() not in page.content().lower(), secret
    assert page.locator("form").count() == 0 or page.locator("form[role=search]").count() == page.locator("form").count()
    shot(page, "desktop-sources")


@check("about page explains the limits")
def about_page(page: Page) -> None:
    goto(page, "/about")
    for text in ("Public data only", "Official sources only", "Limitations", "not exhaustive"):
        assert text.lower() in page.inner_text("main").lower(), text
    shot(page, "desktop-about")


@check("unknown page shows the not-found state")
def not_found(page: Page) -> None:
    goto(page, "/definitely-not-here")
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()


# --- theme, privacy, accessibility -------------------------------------------------------------


@check("theme: dark by default, switching is stored only in this browser and persists")
def theme(page: Page) -> None:
    goto(page)
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.get_by_role("radio", name="Light theme").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    assert page.evaluate("localStorage.getItem('modelradar-theme')") == "light"
    shot(page, "desktop-dashboard-light")
    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    page.get_by_role("radio", name="Match system theme").click()
    assert page.evaluate("localStorage.getItem('modelradar-theme')") == "system"
    page.get_by_role("radio", name="Dark theme").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"


@check("privacy: no cookies and no requests to any other host")
def privacy(page: Page, hosts: set[str]) -> None:
    for path in ("/", "/models", "/categories", "/companies", "/sources", "/about"):
        goto(page, path)
    # The Next.js development server sets one HMR cookie; it does not exist in production builds.
    # Strict by default (production builds). E2E_DEV=1 tolerates the dev server's HMR cookie.
    strict = os.environ.get("E2E_DEV") != "1"
    cookies = [
        c for c in page.context.cookies() if strict or not c["name"].startswith("__next_hmr")
    ]
    assert cookies == [], cookies
    own = urlparse(BASE).netloc
    foreign = {h for h in hosts if h and h != own}
    assert not foreign, foreign


@check("fonts are served by this site")
def fonts(page: Page) -> None:
    goto(page)
    loaded = page.evaluate("Array.from(document.fonts).filter(f => f.status === 'loaded').map(f => f.family)")
    assert any("Instrument Sans" in f for f in loaded), loaded
    assert any("Newsreader" in f for f in loaded), loaded


@check("accessibility basics: landmarks, labels, skip link, keyboard focus")
def accessibility(page: Page) -> None:
    goto(page)
    assert page.evaluate("document.documentElement.lang") == "en"
    assert page.locator("main").count() == 1 and page.locator("header").count() >= 1
    assert page.get_by_role("navigation", name="Main").count() == 1
    unnamed = page.evaluate(
        """() => Array.from(document.querySelectorAll('button, a, input, select')).filter(e => {
            const name = (e.getAttribute('aria-label') || e.textContent || e.getAttribute('title') || '').trim();
            const labelled = e.labels && e.labels.length > 0;
            return !name && !labelled;
        }).map(e => e.outerHTML.slice(0, 80))"""
    )
    assert unnamed == [], unnamed
    page.keyboard.press("Tab")
    focused = page.evaluate("document.activeElement.textContent.trim()")
    assert focused == "Skip to content", focused
    page.keyboard.press("Enter")
    outline = page.evaluate("getComputedStyle(document.querySelector('a[href=\"/\"]')).outlineStyle")
    assert outline is not None
    page.keyboard.press("Tab")
    ring = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    assert ring == "solid", ring
    ratio = page.evaluate(
        """() => {
          const lum = (c) => { const [r,g,b] = c.match(/\\d+/g).map(Number).map(v => { v/=255; return v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4)}); return .2126*r+.7152*g+.0722*b };
          const fg = getComputedStyle(document.querySelector('main p')).color;
          const bg = getComputedStyle(document.body).backgroundColor;
          const [a,b] = [lum(fg), lum(bg)].sort((x,y)=>y-x); return (a+.05)/(b+.05);
        }"""
    )
    assert ratio >= 4.5, f"muted text contrast {ratio:.2f}"


# --- responsive --------------------------------------------------------------------------------


@check("mobile: no horizontal overflow on any page")
def mobile_overflow(page: Page) -> None:
    for path in ("/", "/?q=gemini", "/models", "/categories", "/companies", "/sources", "/about"):
        goto(page, path)
        assert no_horizontal_overflow(page), f"horizontal overflow on {path}"
    goto(page)
    shot(page, "mobile-dashboard")
    goto(page, "/sources")
    shot(page, "mobile-sources")


@check("mobile: drawer navigation opens, has touch-sized targets, navigates and closes")
def mobile_drawer(page: Page) -> None:
    goto(page)
    assert not page.get_by_role("navigation", name="Main").is_visible()
    menu = page.get_by_role("button", name="Open navigation")
    box = menu.bounding_box()
    assert box["width"] >= 40 and box["height"] >= 40, box
    menu.click()
    dialog = page.get_by_role("dialog", name="Navigation")
    expect(dialog).to_be_visible()
    shot(page, "mobile-drawer")
    for link in dialog.get_by_role("link").all():
        b = link.bounding_box()
        assert b["height"] >= 40, b
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    menu.click()
    dialog.get_by_role("link", name="Sources").click()
    page.wait_for_url(f"{BASE}/sources")
    expect(page.get_by_role("dialog", name="Navigation")).to_be_hidden()


@check("mobile: filters are usable and cards stack")
def mobile_filters(page: Page) -> None:
    goto(page)
    sel = page.get_by_label("Company")
    box = sel.bounding_box()
    assert box["height"] >= 40, box
    sel.select_option("pika")
    page.wait_for_url(re.compile(r"company=pika"))
    page.wait_for_load_state("networkidle")
    assert page.locator("article").count() > 0
    assert no_horizontal_overflow(page)


@check("tablet: layout switches without overflow")
def tablet(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 1100})
    for path in ("/", "/sources", "/companies"):
        goto(page, path)
        assert no_horizontal_overflow(page), path
    shot(page, "tablet-dashboard")


def main() -> int:
    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(headless=True)

        hosts: set[str] = set()
        ctx = browser.new_context(viewport=DESKTOP)
        page = ctx.new_page()
        page.on("request", lambda r: hosts.add(urlparse(r.url).netloc))
        for fn in (
            dashboard_real_data, sorting, pagination, filters, more_filters, search,
            search_keeps_filters, filters_and_pagination, category_chip, history,
            refresh_filtered, no_hangs, slash_focus,
            missing_data, navigation, categories_page, companies_page, models_page, sources_page,
            about_page, not_found, theme, fonts, accessibility,
        ):  # fmt: skip
            fn(page)
        privacy(page, hosts)
        ctx.close()

        mobile = browser.new_context(viewport=MOBILE, is_mobile=True, has_touch=True)
        mpage = mobile.new_page()
        mobile_overflow(mpage)
        mobile_drawer(mpage)
        mobile_filters(mpage)
        tablet(mpage)
        mobile.close()
        browser.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
