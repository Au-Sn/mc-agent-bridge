#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_ua_probe.py -- ★探一探 HTTP 的 User-Agent 到底是谁✗★（★临时探针 ✓ §79.209 补的职责句✓★）"""
import urllib.request, ssl, time, socket
UA_PY = "Python-urllib/3.11"
UA_BR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_GR = "Gradle/8.1.1 (Windows 10; 10.0; amd64) (Microsoft; 17.0.20.1+1-LTS; 17.0.20.1)"
tests = [
  ("piston-meta", "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"),
  ("libraries",   "https://libraries.minecraft.net/net/minecraftforge/forgespi/4.0.15/forgespi-4.0.15.jar"),
  ("launcher",    "https://launcher.mojang.com/"),
]
for name, url in tests:
    for label, ua in (("py", UA_PY), ("browser", UA_BR), ("gradle", UA_GR)):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=25) as r:
                b = r.read(2000)
            print("%-12s %-8s 200  %5.1fs  %d bytes" % (name, label, time.time()-t0, len(b)))
        except Exception as e:
            print("%-12s %-8s ERR  %5.1fs  %r" % (name, label, time.time()-t0, e))
