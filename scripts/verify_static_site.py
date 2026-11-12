#!/usr/bin/env python3
"""Check a static Sites build without treating source checks as browser QA."""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit
from audit import write_private


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.references = set(), []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        for attr in ["href", "src", "poster"]:
            if attrs.get(attr):
                self.references.append(attrs[attr])
        if attrs.get("srcset"):
            self.references.extend(x.strip().split()[0] for x in attrs["srcset"].split(",") if x.strip())


def verify(root, origin):
    root = Path(root).resolve()
    manifest = json.loads((root / ".openai/hosting.json").read_text())
    dist = root / manifest["static"]["directory"]
    assert (dist / "index.html").is_file()
    pages = {}
    for file in dist.rglob("*.html"):
        page = Page()
        page.feed(file.read_text())
        pages[file.resolve()] = page
    failures, checked = [], 0

    def check(source, value):
        nonlocal checked
        url = urlsplit(value)
        if url.scheme in ["data", "mailto", "tel", "javascript", "blob"] or (url.netloc and url.netloc != urlsplit(origin).netloc):
            return
        if url.path.startswith("/"):
            target = dist / unquote(url.path).lstrip("/")
        elif url.path:
            target = source.parent / unquote(url.path)
        else:
            target = source
        if target.is_dir():
            target = target / "index.html"
        target = target.resolve()
        checked += 1
        if not target.is_relative_to(dist.resolve()) or not target.is_file():
            failures.append({"source": str(source.relative_to(dist)), "reference": value, "error": "missing_local_file"})
        elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
            failures.append({"source": str(source.relative_to(dist)), "reference": value, "error": "missing_fragment"})

    for source, page in pages.items():
        for reference in page.references:
            check(source, reference)
    for source in dist.rglob("*.css"):
        for reference in re.findall(r"url\(([^)]+)\)", source.read_text()):
            check(source, reference.strip(" \"'"))
    scripts = list(dist.rglob("*.js"))
    syntax = []
    for script in scripts:
        result = subprocess.run(["node", "--check", str(script)], capture_output=True)
        syntax.append({"script": str(script.relative_to(dist)), "passed": result.returncode == 0})
    catalog = None
    source = root / "public-content.json"
    if source.exists():
        data = json.loads(source.read_text())
        articles = data["articles"]
        ids = {x["id"] for x in articles}
        references = [ref for group in ["levels", "functions"] for item in data["operations"][group]
                      for field in ["skillIds", "connectorIds", "frameworkIds", "capabilityIds"] for ref in item.get(field, [])]
        catalog = {"article_count": len(articles), "unique_ids": len(ids), "types": dict(Counter(x["type"] for x in articles)),
                   "operation_references": len(references), "operation_references_valid": all(x in ids for x in references),
                   "all_article_pages_present": all((dist / "read" / (x + ".html")).is_file() for x in ids)}
    return {"schema_version": 1, "scope": "static_source_and_asset_checks_only", "rendered_browser_QA": "not_performed",
            "project_id": manifest["project_id"], "html_files": len(pages), "published_files": sum(p.is_file() for p in dist.rglob("*")),
            "local_references_checked": checked, "broken_references": failures, "javascript_syntax": syntax, "catalogue": catalog,
            "passed": not failures and all(x["passed"] for x in syntax) and (catalog is None or (catalog["operation_references_valid"] and catalog["all_article_pages_present"] and catalog["article_count"] == catalog["unique_ids"]))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.checkout, args.origin)
    write_private(args.output, result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
