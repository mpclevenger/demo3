"""Upload made-up provider files to a TRUST site and update each month (owner, 5 Nov 2026).

    python tools/upload_test_data.py --site https://trust-test.example.com --folder demo-files
    python tools/upload_test_data.py --site http://127.0.0.1:5000 --folder demo-files --months 2026-10 --by "Pat"
    python tools/upload_test_data.py --site https://… --folder demo-files --header "X-Sam: pat.lee" --header "X-Groups: TRUST-TR"

Reads demo-files/manifest.json (written by tools/make_test_data.py), posts every file to /api/upload with the
header the site expects (X-TRUST: 1), then presses Update the scorecard for each month and waits for it to finish.
Standard library only. Only for the TEST site: never point it at production.

If the site sits behind the identity add-on with roles switched on, run it from somewhere the add-on lets through,
or pass the headers the add-on would set with --header (the site must be told to trust them; see
docs/wiki/roles-and-permissions.md). Uploads need the Tech Risk role.
"""
import argparse
import json
import mimetypes
import pathlib
import sys
import time
import urllib.error
import urllib.request
import uuid


def _request(site, path, headers, data=None, content_type=None):
    req = urllib.request.Request(site.rstrip("/") + path, data=data, method="POST" if data is not None else "GET")
    req.add_header("X-TRUST", "1")
    if content_type:
        req.add_header("Content-Type", content_type)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(body).get("error", body)
        except ValueError:
            pass
        raise SystemExit(f"{path}: HTTP {e.code}: {body[:300]}")


def _multipart(fields, filename, content):
    boundary = "----trust-" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def main(argv=None):
    p = argparse.ArgumentParser(description="Upload made-up files to the TRUST TEST site and update each month.")
    p.add_argument("--site", required=True, help="the TEST site's address, e.g. https://trust-test.example.com")
    p.add_argument("--folder", default="demo-files", help="folder written by tools/make_test_data.py")
    p.add_argument("--months", nargs="*", help="only these months (default: every month in the folder)")
    p.add_argument("--by", default="Test data", help="the name recorded on each upload and update")
    p.add_argument("--header", action="append", default=[], help='extra request header, "Name: value" (repeatable)')
    p.add_argument("--no-update", action="store_true", help="upload only; don't press Update the scorecard")
    a = p.parse_args(argv)

    folder = pathlib.Path(a.folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    headers = dict(h.split(":", 1) for h in a.header)
    headers = {k.strip(): v.strip() for k, v in headers.items()}
    months = a.months or sorted(manifest["months"])
    print(f"Site {a.site}: {len(months)} months, CTO in the files is {manifest['cto_sam']} "
          f"(the site needs TRUST_HR_ROOT_SAM_ACCOUNT={manifest['cto_sam']}).")

    for month in months:
        files = manifest["months"].get(month)
        if not files:
            raise SystemExit(f"{month} isn't in {folder}/manifest.json")
        print(f"\n{month}")
        for feed, name in files.items():
            body, ctype = _multipart({"feed": feed, "month": month, "by": a.by}, name, (folder / month / name).read_bytes())
            r = _request(a.site, "/api/upload", headers, body, ctype)
            warn = len((r.get("checks") or {}).get("warnings", []))
            print(f"  {feed:12} {name:34} {r.get('note', '')[:60]}{f'  ({warn} warnings)' if warn else ''}")
        if a.no_update:
            continue
        r = _request(a.site, "/api/update", headers, json.dumps({"month": month, "by": a.by}).encode(), "application/json")
        job = r.get("job")
        state = r.get("state")
        t0 = time.time()
        while state == "running" and time.time() - t0 < 1200:
            time.sleep(3)
            s = _request(a.site, f"/api/update/{month}/{job}", headers)
            state = s.get("state")
            if state in ("failed", "stopped"):
                raise SystemExit(f"  update {state}: {s.get('message')}")
        print(f"  updated ({state}, {round(time.time() - t0)} s)")
    print("\nDone. Open the site: the months are scored and published. Lock them on This month if you want the locked look.")


if __name__ == "__main__":
    sys.exit(main())
