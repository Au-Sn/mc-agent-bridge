# grab_window.ps1
# Capture the Minecraft game window's own pixels, and optionally rescue a window
# whose saved position landed off-screen.
#
# WHY THIS EXISTS (real incident):
#   - A full-screen GDI capture (CopyFromScreen / BitBlt) can NOT capture a game
#     that renders through an independent-flip / hardware-overlay surface.
#     The screen shot then shows only the desktop, which easily causes a false
#     conclusion like "the game is not visible / not running".
#   - PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT=2) asks the window to render
#     itself, which does return the real game frame.
#   - Separately, if a window's *normal* position is (-32000,-32000) then every
#     taskbar click "restores" it off-screen; the user then cannot open it at all.
#
# Usage (in this sandbox child processes are blocked, so run it in-session with &):
#   & .\tools\grab_window.ps1
#   & .\tools\grab_window.ps1 -Out logs\mc.png
#   & .\tools\grab_window.ps1 -ProcId 1234
#   & .\tools\grab_window.ps1 -Fix          # rescue an off-screen window
#   & .\tools\grab_window.ps1 -ListOnly     # just list the java windows
#
# -Fix  : move an off-screen game window back to a sane position and raise it.

param(
    [string]$Out = "",
    [int]$ProcId = 0,   # NOT -Pid: $Pid is a read-only automatic variable in PowerShell
    [switch]$Fix,
    [switch]$ListOnly
)

$ErrorActionPreference = "Stop"

Add-Type -ReferencedAssemblies System.Drawing @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;

public class McGrab {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)]
    public struct WINDOWPLACEMENT {
        public int length; public int flags; public int showCmd;
        public POINT ptMinPosition; public POINT ptMaxPosition; public RECT rcNormalPosition;
    }

    delegate bool EnumProc(IntPtr h, IntPtr l);

    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool GetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT p);
    [DllImport("user32.dll")] public static extern bool SetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT p);

    public class Info {
        public IntPtr Handle;
        public string ClassName = "";
        public string Title = "";
        public bool Visible;
        public bool Minimized;
        public int X, Y, W, H;
        public override string ToString() {
            return string.Format("h={0} class={1} vis={2} min={3} rect=({4},{5}) size={6}x{7} title=[{8}]",
                Handle, ClassName, Visible, Minimized, X, Y, W, H, Title);
        }
    }

    // Enumerate every top-level window owned by a pid.
    public static List<Info> Windows(uint target) {
        var list = new List<Info>();
        EnumWindows((h, l) => {
            uint pid; GetWindowThreadProcessId(h, out pid);
            if (pid == target) {
                var t = new StringBuilder(300); GetWindowTextW(h, t, 300);
                var c = new StringBuilder(300); GetClassNameW(h, c, 300);
                RECT r; GetWindowRect(h, out r);
                list.Add(new Info {
                    Handle = h, ClassName = c.ToString(), Title = t.ToString(),
                    Visible = IsWindowVisible(h), Minimized = IsIconic(h),
                    X = r.Left, Y = r.Top, W = r.Right - r.Left, H = r.Bottom - r.Top
                });
            }
            return true;
        }, IntPtr.Zero);
        return list;
    }

    // The real game window: a visible GLFW30 window, big enough to be the game.
    public static Info FindGameWindow(uint target) {
        Info best = null;
        foreach (var w in Windows(target)) {
            if (w.ClassName != "GLFW30") continue;
            if (w.Title.IndexOf("GLFW message window") >= 0) continue;
            if (best == null || (w.W * w.H) > (best.W * best.H)) best = w;
        }
        return best;
    }

    // Render the window into a PNG. Returns a status line.
    public static string Grab(IntPtr h, string path) {
        RECT r; GetWindowRect(h, out r);
        int w = r.Right - r.Left, ht = r.Bottom - r.Top;
        if (w <= 0 || ht <= 0) return "invalid window size";
        using (var bmp = new Bitmap(w, ht))
        using (var g = Graphics.FromImage(bmp)) {
            IntPtr hdc = g.GetHdc();
            bool ok = PrintWindow(h, hdc, 2); // PW_RENDERFULLCONTENT
            g.ReleaseHdc(hdc);
            long sum = 0; int n = 0;
            for (int y = 0; y < ht; y += 12)
                for (int x = 0; x < w; x += 12) { var c = bmp.GetPixel(x, y); sum += c.R + c.G + c.B; n++; }
            bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            double avg = (double)sum / Math.Max(1, n);
            return string.Format("PrintWindow={0} size={1}x{2} avgBrightness={3:F1}/765 {4}",
                ok, w, ht, avg, avg < 3 ? "(ALL BLACK - capture likely failed)" : "");
        }
    }

    // Set a sane on-screen position, both current and saved (normal) placement.
    public static bool Rescue(IntPtr h, int x, int y, int w, int ht) {
        var wp = new WINDOWPLACEMENT();
        wp.length = Marshal.SizeOf(typeof(WINDOWPLACEMENT));
        GetWindowPlacement(h, ref wp);
        string before = string.Format("showCmd={0} normal=({1},{2})-({3},{4})",
            wp.showCmd, wp.rcNormalPosition.Left, wp.rcNormalPosition.Top,
            wp.rcNormalPosition.Right, wp.rcNormalPosition.Bottom);
        wp.showCmd = 1; // SW_SHOWNORMAL
        wp.rcNormalPosition.Left = x; wp.rcNormalPosition.Top = y;
        wp.rcNormalPosition.Right = x + w; wp.rcNormalPosition.Bottom = y + ht;
        SetWindowPlacement(h, ref wp);
        ShowWindow(h, 1);
        SetWindowPos(h, IntPtr.Zero, x, y, w, ht, 0x40); // SWP_SHOWWINDOW
        SetForegroundWindow(h);
        Console.WriteLine("  before: " + before);
        return true;
    }
}
'@

function Get-JavaPids {
    param([int]$Only)
    if ($Only -gt 0) { return @($Only) }
    $ids = @()
    foreach ($p in Get-Process java -ErrorAction SilentlyContinue) { $ids += $p.Id }
    return $ids
}

$found = $null
foreach ($id in (Get-JavaPids -Only $ProcId)) {
    $w = [McGrab]::FindGameWindow([uint32]$id)
    if ($w -ne $null) { $found = $w; "java pid $id => $w"; break }
}

if ($found -eq $null) {
    "No GLFW game window found. All top-level windows of java processes:"
    foreach ($id in (Get-JavaPids -Only $ProcId)) {
        "-- pid $id --"
        [McGrab]::Windows([uint32]$id) | ForEach-Object { "  $_" }
    }
    exit 2
}

if ($ListOnly) { exit 0 }

if ($Fix) {
    $offScreen = ($found.X -le -30000) -or ($found.Y -le -30000) -or (-not $found.Visible) -or $found.Minimized
    if ($offScreen) {
        "Window is off-screen / hidden -> rescuing to (60,40) 1600x900"
        [void][McGrab]::Rescue($found.Handle, 60, 40, 1600, 900)
        Start-Sleep -Seconds 2
    } else {
        "Window already on screen at ({0},{1}); raising it." -f $found.X, $found.Y
        [void][McGrab]::SetForegroundWindow($found.Handle)
    }
}

if ($Out -eq "") {
    $Out = Join-Path (Split-Path $PSScriptRoot -Parent) "logs\game-window.png"
}
# NOTE: Set-Location does NOT change the .NET process working directory, so a
# relative path would be resolved against the wrong folder and Bitmap.Save would
# fail with "A generic error occurred in GDI+". Always resolve to an absolute path.
if (-not [System.IO.Path]::IsPathRooted($Out)) { $Out = Join-Path (Get-Location).Path $Out }
$Out = [System.IO.Path]::GetFullPath($Out)
$dir = Split-Path $Out -Parent
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
try {
    "Capture: " + [McGrab]::Grab($found.Handle, $Out)
} catch {
    "Capture FAILED: " + $_.Exception.Message
    "  target path was: $Out"
    exit 3
}
"Saved  : $Out"
