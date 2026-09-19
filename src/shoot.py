"""Screenshot the site at real viewport widths, via the DevTools Protocol.

Chrome's `--headless --screenshot --window-size=375,H` does NOT give a 375px
viewport: headless clamps the layout width to a 512px minimum, so the page
lays out at 512 and the capture crops it to 375. Everything then looks
broken at narrow widths when it is not.

Driving the browser over CDP instead lets Emulation.setDeviceMetricsOverride
set a genuine viewport, and Page.captureScreenshot take a clipped, full-page
shot of one section.

    python shoot.py            # all widths, all sections
    python shoot.py 375        # one width
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests
import websocket

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "screenshots"
URL = "http://localhost:8137/"
WIDTHS = [375, 800, 1440]
SECTIONS = [("tool", "#tool"), ("finding", "#finding"), ("costloss", "#costloss"),
            ("seasonal", "#seasonal"), ("map", "#map"), ("era5", "#era5")]
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
MAX_CLIP_H = 4200          # keep any single image manageable


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Tab:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.n = 0

    def send(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method,
                                 "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=True)
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main() -> int:
    chrome = next((c for c in CHROME_CANDIDATES if Path(c).exists()), None)
    if not chrome:
        sys.exit("no Chrome/Edge found")
    widths = [int(a) for a in sys.argv[1:]] or WIDTHS
    OUT.mkdir(exist_ok=True)
    port = free_port()
    profile = Path(os.environ.get("TEMP", "/tmp")) / f"shoot{port}"
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--no-first-run", "--no-default-browser-check",
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         # Chrome rejects CDP websockets whose Origin it does not know;
         # the local debugging port is only bound to loopback anyway
         "--remote-allow-origins=*",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(60):
            try:
                tabs = requests.get(f"http://127.0.0.1:{port}/json",
                                    timeout=2).json()
                page = [t for t in tabs if t.get("type") == "page"]
                if page:
                    ws_url = page[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not ws_url:
            sys.exit("could not reach the DevTools endpoint")

        tab = Tab(ws_url)
        tab.send("Page.enable")
        tab.send("Runtime.enable")
        tab.send("Emulation.setEmulatedMedia", features=[
            {"name": "prefers-color-scheme", "value": "light"}])

        made = []
        for w in widths:
            tab.send("Emulation.setDeviceMetricsOverride", width=w, height=900,
                     deviceScaleFactor=1, mobile=False)
            tab.send("Page.navigate", url=f"{URL}?shot={w}")
            # wait for the sections to be populated, then for the lazy map
            for _ in range(60):
                time.sleep(0.4)
                if tab.js("!!document.querySelector('#chartFar svg')"):
                    break
            real = tab.js("document.documentElement.clientWidth")
            # fill the tool in so its screenshot shows a real answer
            tab.js("""(function(){
              var i=document.querySelector('#tLoc');
              i.value='Nagpur'; i.dispatchEvent(new Event('input',{bubbles:true}));
              var b=document.querySelector('#tSuggest button'); if(b)b.click();
              var L=document.querySelectorAll('#tLead button'); if(L[0])L[0].click();
              var c=document.querySelector('#tCost'), l=document.querySelector('#tLoss');
              c.value='600'; c.dispatchEvent(new Event('input',{bubbles:true}));
              l.value='1000'; l.dispatchEvent(new Event('input',{bubbles:true}));
              return 1;})()""")
            time.sleep(0.8)
            tab.js("window.scrollTo(0, document.querySelector('#map')"
                   ".offsetTop - 40)")
            for _ in range(40):
                time.sleep(0.4)
                if tab.js("document.querySelectorAll('.cell').length > 0"):
                    break
            tab.js("window.scrollTo(0,0)")
            time.sleep(0.6)
            over = tab.js(
                "document.documentElement.scrollWidth - "
                "document.documentElement.clientWidth")
            print(f"  {w}px -> real viewport {real}px, "
                  f"horizontal overflow {over}px")

            for name, sel in SECTIONS:
                expr = (
                    "(function(){var e=document.querySelector(SEL);"
                    "if(!e)return null;var r=e.getBoundingClientRect();"
                    "return {y:r.top+window.scrollY,w:window.innerWidth,"
                    "h:Math.min(r.height,MAXH)};})()"
                ).replace("SEL", json.dumps(sel)).replace("MAXH", str(MAX_CLIP_H))
                box = tab.js(expr)
                if not box:
                    continue
                shot = tab.send(
                    "Page.captureScreenshot", format="png",
                    captureBeyondViewport=True,
                    clip={"x": 0, "y": box["y"], "width": box["w"],
                          "height": box["h"], "scale": 1})
                f = OUT / f"{w:04d}-{name}.png"
                f.write_bytes(base64.b64decode(shot["data"]))
                made.append(f)
        tab.close()
        print(f"\nwrote {len(made)} files to {OUT}")
        for f in made:
            print(f"  {f.name:24} {f.stat().st_size/1024:6.0f} KB")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
