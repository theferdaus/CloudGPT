#!/usr/bin/env python3
"""Test cloud baseline workflows with disposable data; never calls paid APIs."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import zipfile
from audit import write_private


def run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, timeout=60)


def verify(output):
    results = []
    artifacts = Path(output).resolve().parent / "verification-artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    def check(name, function):
        try:
            detail = function()
            results.append({"workflow": name, "status": "passed", "detail": detail})
        except (ImportError, FileNotFoundError) as exc:
            results.append({"workflow": name, "status": "blocked", "reason": type(exc).__name__})
        except Exception as exc:
            # Do not export raw subprocess output, URLs or environment diagnostics.
            results.append({"workflow": name, "status": "failed", "reason": type(exc).__name__})

    with tempfile.TemporaryDirectory(prefix="cloudgpt-verify-") as directory:
        work = Path(directory)

        def python_sqlite():
            with sqlite3.connect(work / "basic.db") as db:
                db.execute("create table sample(value integer)")
                db.execute("insert into sample values(42)")
                assert db.execute("select sum(value) from sample").fetchone()[0] == 42
            return "SQLite insert, commit and query"

        def javascript():
            run(["node", "-e", "const fs=require('node:fs');fs.writeFileSync('node.json',JSON.stringify({value:6*7}))"], work)
            assert json.loads((work / "node.json").read_text())["value"] == 42
            return "Node computation and filesystem output"

        def video():
            run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10", "-t", "0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "test.mp4"], work)
            run(["ffmpeg", "-v", "error", "-i", "test.mp4", "-frames:v", "1", "frame.png"], work)
            assert (work / "frame.png").stat().st_size > 0
            shutil.copy2(work / "test.mp4", artifacts / "test.mp4")
            return "H.264 encode and PNG decode"

        def documents():
            (work / "test.md").write_text("# CloudGPT verification\n\nPortable document conversion works.\n")
            run(["pandoc", "test.md", "-o", "test.docx"], work)
            with zipfile.ZipFile(work / "test.docx") as archive:
                assert b"Portable document conversion works" in archive.read("word/document.xml")
            shutil.copy2(work / "test.docx", artifacts / "test.docx")
            return "Markdown to DOCX, then inspect Word XML"

        def containers():
            p = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], check=True, capture_output=True, text=True, timeout=20)
            assert p.stdout.strip()
            return "Docker daemon reachable; image builds not tested"

        def browser():
            from playwright.sync_api import sync_playwright
            dbpath = work / "browser.db"
            with sqlite3.connect(dbpath) as db:
                db.execute("create table submissions(value text)")

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass

                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b'''<!doctype html><html><title>CloudGPT verification</title><label>Value <input id="value"></label><button id="save">Save</button><output id="result"></output><script>document.querySelector('#save').onclick=async()=>{const response=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:document.querySelector('#value').value})});document.querySelector('#result').textContent=(await response.json()).value}</script></html>''')

                def do_POST(self):
                    data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    with sqlite3.connect(dbpath) as db:
                        db.execute("insert into submissions values(?)", (data["value"],))
                        value = db.execute("select value from submissions order by rowid desc limit 1").fetchone()[0]
                    payload = json.dumps({"value": value}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(payload)

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    executable = shutil.which("chromium") or shutil.which("google-chrome")
                    options = {"headless": True}
                    if executable:
                        options["executable_path"] = executable
                    if os.getuid() == 0:
                        options["args"] = ["--no-sandbox"]
                    instance = playwright.chromium.launch(**options)
                    page = instance.new_page()
                    page.goto(f"http://127.0.0.1:{server.server_port}")
                    page.get_by_label("Value").fill("cloudgpt-verified")
                    page.get_by_role("button", name="Save").click()
                    page.locator("#result").filter(has_text="cloudgpt-verified").wait_for()
                    assert page.locator("#result").inner_text() == "cloudgpt-verified"
                    page.screenshot(path=str(artifacts / "browser.png"))
                    instance.close()
                with sqlite3.connect(dbpath) as db:
                    assert db.execute("select value from submissions").fetchall() == [("cloudgpt-verified",)]
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            return "Chromium form → POST API → SQLite insert/query → rendered response; screenshot saved"

        for name, fn in [("python_sqlite", python_sqlite), ("javascript", javascript), ("video", video), ("documents", documents), ("docker_daemon", containers), ("browser_api_database_response", browser)]:
            check(name, fn)
    data = {"schema_version": 1, "scope": "disposable_baseline_smoke_workflows_only", "actual_user_workflow_parity": "not_verified", "results": results,
            "artifacts": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(artifacts.iterdir()) if p.is_file()]}
    write_private(output, data)
    print(json.dumps({x["workflow"]: x["status"] for x in results}))
    return all(x["status"] == "passed" for x in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    raise SystemExit(0 if verify(parser.parse_args().output) else 1)
