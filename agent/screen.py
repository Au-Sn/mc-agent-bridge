#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
screen.py — 眼睛与手：看游戏窗口的真实画面，并在需要时点击

为什么需要它（用户提出的真问题）：
  科技包里**很多机器自带 UI**，Carpet 假人开不了界面 ✗（没有客户端）✓
  于是"要不要为了界面放弃推广"就成了必须回答的问题 ✓ 答案是两条腿：

  A 线（首选）：绕开界面 —— 用机器自己的自动化接口
      物品进出 → 漏斗/管道 ✓（假人只要"丢/放" ✓ 已验证）
      按需合成 → AE2 的 ME Bridge 等 CC 外设 ✓（craftItem ✓ 零界面 ✓）
  B 线（兜底，本文件）：**我来操作界面** ——
      截图 → 我看图（本模型有视觉能力）→ 说出像素坐标与理由 → 点击 ✓
      这样任何 UI 都能用 ✓ 而且顺带获得一个**独立于 CC 的验证通道** ✓

关键的工程细节（都踩过坑）：
  1. **普通 BitBlt 抓不到游戏画面** ✗ —— 用了独立翻转/硬件覆盖层的游戏只会拍到桌面 ✓
     必须用 PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT=2) ✓（tools/grab_window.ps1 已实现 ✓）
     并且**必须检查平均亮度** ✓ 全黑就是抓失败 ✓ 不能当成"游戏没开" ✓
  2. 窗口可能停在 (-32000,-32000) 且尺寸退化成 160x28 ✓ —— 那是"保存位置跑到屏幕外"的故障 ✓
     此时要先 Rescue 回可见位置 ✓ 否则抓到的是垃圾 ✓
  3. 点击坐标是**屏幕绝对坐标** ✓ 不是图像坐标 ✓ 必须用窗口当前位置做映射 ✓
     窗口一旦移动，旧坐标立刻作废 ✓ 所以每次点击前重新取窗口矩形 ✓

安全默认（重要）：
  **默认只看不点** ✓ click() 的 dry_run 默认为 True ✓
  要真点必须显式 live=True ✓ 并且每次点击都会写进行动日志 ✓
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory import Journal  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GRAB_PS1 = ROOT / "tools" / "grab_window.ps1"
DEFAULT_OUT = ROOT / "logs" / "game-window.png"

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _window_class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _window_title(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def find_game_window() -> dict | None:
    """找最大的那个可见 GLFW30 窗口（Minecraft 的窗口类）。

    不按标题找 ✗：标题会随"单人游戏/多人游戏/存档名"变化 ✓ 类名才是稳定的 ✓
    """
    best: dict | None = None
    found: list[dict] = []

    def cb(hwnd, _lparam):
        nonlocal best
        if _window_class(hwnd) != "GLFW30":
            return True
        title = _window_title(hwnd)
        if "GLFW message window" in title:
            return True
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        info = {"hwnd": int(hwnd), "title": title, "x": r.left, "y": r.top, "w": w, "h": h,
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "minimized": bool(user32.IsIconic(hwnd)),
                "offscreen": (r.left <= -30000 or r.top <= -30000),
                "degenerate": (w < 400 or h < 300)}
        found.append(info)
        if best is None or info["w"] * info["h"] > best["w"] * best["h"]:
            best = info
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return best


def powershell_exe() -> str:
    """找 PowerShell 可执行文件。

    这里踩过坑 ✓：**这台机器上是 Windows PowerShell 5.1**，可执行文件叫 `powershell.exe` ✗
    而不是 `pwsh`（那是 PowerShell 7 ✗）✓ 硬写 `pwsh` 会得到 WinError 2 ✓
    所以按顺序探测 ✓ 找不到就明确报错 ✓ 不静默降级 ✓
    """
    for name in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("找不到任何 PowerShell 可执行文件（试过 powershell.exe / pwsh）")


class Screen:
    def __init__(self, out: Path = DEFAULT_OUT, verbose: bool = True):
        self.out = Path(out)
        self.verbose = verbose
        self.journal = Journal("screen")

    # -- 眼睛 ---------------------------------------------------------------- #

    def geometry(self) -> dict | None:
        return find_game_window()

    def healthy(self) -> tuple[bool, str]:
        g = self.geometry()
        if not g:
            return False, "找不到 GLFW30 游戏窗口（游戏没开？）"
        if g["degenerate"]:
            return False, ("窗口退化到 %dx%d @(%d,%d) —— 这是「保存位置跑到屏幕外」的故障，"
                           "先跑 tools/grab_window.ps1 -Fix 救回来" % (g["w"], g["h"], g["x"], g["y"]))
        if g["minimized"]:
            return False, "窗口最小化了 → 先 -Fix 恢复"
        return True, "窗口 %dx%d @(%d,%d) 可见" % (g["w"], g["h"], g["x"], g["y"])

    def look(self, out: Path | None = None, rescue: bool = False) -> Path:
        """抓一张真实游戏画面（复用已验证的 PrintWindow 工具）。

        刻意用 stdio 继承而不是管道：受限环境里管道捕获子进程输出会被拒 ✗
        （stdio='inherit' 的 spawn 是允许的 ✓）
        """
        out = Path(out or self.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", str(GRAB_PS1), "-Out", str(out)]
        if rescue:
            cmd.append("-Fix")
        subprocess.run(cmd, check=False)
        if not out.is_file():
            raise RuntimeError("抓图失败：没有产出文件 %s" % out)
        self.journal.write("look", summary="抓图 %s" % out)
        return out

    # -- 手 ------------------------------------------------------------------ #

    def to_screen(self, img_x: float, img_y: float, img_w: int, img_h: int) -> tuple[int, int]:
        """图像坐标 → 屏幕绝对坐标。每次都用**当前**窗口矩形换算 ✓"""
        g = self.geometry()
        if not g:
            raise RuntimeError("找不到游戏窗口，无法换算坐标")
        sx = g["x"] + img_x * (g["w"] / float(img_w))
        sy = g["y"] + img_y * (g["h"] / float(img_h))
        return int(round(sx)), int(round(sy))

    def click(self, x: int, y: int, live: bool = False, note: str = "",
              button: str = "left") -> dict:
        """点击屏幕绝对坐标。**默认只看不点** ✓

        为什么要 dry_run 默认：在别人的游戏里点击是**有副作用**的动作 ✓
        点错一下可能丢掉物品、打开错误的界面、甚至误触危险操作 ✓
        所以默认必须"先说出要点哪里、为什么" ✓ 再由人放行 ✓
        """
        g = self.geometry()
        info = {"x": x, "y": y, "live": bool(live), "note": note, "button": button,
                "window": g}
        if not live:
            self.journal.write("click_dry", summary="【只看不点】(%d,%d) %s" % (x, y, note))
            if self.verbose:
                print("[只看不点] 目标屏幕坐标 (%d,%d)  %s" % (x, y, note))
            return {"ok": True, "dry_run": True, **info}
        flags = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}.get(button, (0x0002, 0x0004))
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.12)
        user32.mouse_event(flags[0], 0, 0, 0, 0)   # down
        time.sleep(0.06)
        user32.mouse_event(flags[1], 0, 0, 0, 0)   # up
        self.journal.write("click", summary="点击 (%d,%d) %s" % (x, y, note))
        if self.verbose:
            print("[点击] (%d,%d) %s" % (x, y, note))
        return {"ok": True, "dry_run": False, **info}

    def click_image(self, img_x: int, img_y: int, img_w: int, img_h: int,
                    live: bool = False, note: str = "") -> dict:
        sx, sy = self.to_screen(img_x, img_y, img_w, img_h)
        return self.click(sx, sy, live=live, note=note)


def main(argv: list[str]) -> int:
    sc = Screen()
    live = "--live" in argv
    if not argv or argv[0] == "look":
        ok, msg = sc.healthy()
        print(("窗口正常：" if ok else "窗口有问题：") + msg)
        p = sc.look(rescue=("--fix" in argv))
        print("已抓图：%s（用 read_image 看它）" % p)
        return 0 if ok else 1
    if argv[0] == "geom":
        print(json.dumps(sc.geometry(), ensure_ascii=False, indent=1))
        return 0
    if argv[0] == "click" and len(argv) >= 3:
        r = sc.click(int(argv[1]), int(argv[2]), live=live, note="CLI")
        print(json.dumps(r, ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
