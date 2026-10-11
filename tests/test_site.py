import json

from cqp.site import build_site


def test_site_builds_with_relative_links(tmp_path):
    entries = build_site(tmp_path / "site", rebuild=True)
    out = tmp_path / "site"
    assert (out / "index.html").exists() and (out / ".nojekyll").exists()
    assert (out / "viewer" / "index.html").exists()
    assert (out / "viewer" / "vendor" / "three" / "three.module.min.js").exists()
    assert json.loads((out / "projects.json").read_text()) == entries
    for e in entries:
        page = (out / e["slug"] / "index.html").read_text()
        assert "../viewer/index.html?" in page
        assert 'href="/' not in page and 'src="/' not in page  # must work under /pr-N/
        assert any(f.suffix == ".glb" for f in (out / e["slug"]).iterdir())
