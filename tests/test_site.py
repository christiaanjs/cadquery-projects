import json
import re

from cqp.site import build_site


def _check_links(page_path, root):
    """Every relative href/src on a page resolves to a file in the site (no absolute URLs)."""
    page = page_path.read_text()
    assert 'href="/' not in page and 'src="/' not in page  # must work under /pr-N/
    for url in re.findall(r'(?:href|src)="([^"#?]+)', page):
        if url.startswith(("data:", "http")):
            continue
        target = (page_path.parent / url).resolve()
        if url.endswith("/"):
            target = target / "index.html"
        assert target.exists(), f"{page_path.relative_to(root)} links to missing {url}"


def test_site_builds_with_relative_links(tmp_path):
    entries = build_site(tmp_path / "site", rebuild=True)
    out = tmp_path / "site"
    assert (out / "index.html").exists() and (out / ".nojekyll").exists()
    assert (out / "viewer" / "index.html").exists()
    assert (out / "viewer" / "vendor" / "three" / "three.module.min.js").exists()
    assert json.loads((out / "projects.json").read_text()) == entries
    _check_links(out / "index.html", out)
    for e in entries:
        page = (out / e["slug"] / "index.html").read_text()
        _check_links(out / e["slug"] / "index.html", out)
        pages = [out / e["slug"] / v / "index.html" for v in e["variants"]]
        if not e["variants"]:
            pages = [out / e["slug"] / "index.html"]
        for p in pages:
            _check_links(p, out)
            html = p.read_text()
            assert "viewer/index.html?" in html
            glbs = re.findall(r"model=\.\./([^&\"]+\.glb)", html)
            assert glbs and all((out / g).exists() for g in glbs)  # viewer-relative model paths
        if e["variants"]:
            assert all(f'href="{v}/"' in page for v in e["variants"])
