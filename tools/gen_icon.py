# -*- coding: utf-8 -*-
"""生成 App 图标 1024x1024：砂岩纸底 + 变量宽度墨迹笔画 + 信号黄角标（与页面皮肤同语汇）。"""
import io, math, os, sys

from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

W = H = 1024
BG = (230, 225, 213, 255)        # #e6e1d5 砂岩纸
INK = (17, 24, 39, 255)          # #111827 墨黑
INK2 = (31, 41, 55, 255)         # #1f2937
YELLOW = (224, 174, 5, 255)      # #e0ae05 信号黄
CONTOUR = (38, 32, 20, 18)

img = Image.new("RGBA", (W, H), BG)
d = ImageDraw.Draw(img)

# 等高线感背景：几圈不规则圆弧
cx0, cy0 = 820, 180
for r in range(140, 720, 86):
    pts = []
    for a in range(0, 360, 6):
        rad = math.radians(a)
        wob = r + 26 * math.sin(3 * rad + r * 0.011) + 14 * math.cos(5 * rad + r * 0.005)
        pts.append((cx0 + wob * math.cos(rad), cy0 + wob * math.sin(rad)))
    d.line(pts, fill=CONTOUR, width=3)

# 网格点阵（右下角）
for gx in range(960, 1010, 24):
    for gy in range(960, 1010, 24):
        d.ellipse((gx - 3, gy - 3, gx + 3, gy + 3), fill=CONTOUR)


def ribbon(draw, pts_widths, color):
    """变量宽度带状填充：中心线 pts[(x,y,w)]，沿法线两侧偏移半宽后整体填充。"""
    m = len(pts_widths)
    if m < 2:
        return
    left, right = [], []
    for i, (x, y, w) in enumerate(pts_widths):
        if i == 0:
            px, py = pts_widths[1][0] - x, pts_widths[1][1] - y
        elif i == m - 1:
            px, py = x - pts_widths[i - 1][0], y - pts_widths[i - 1][1]
        else:
            px, py = pts_widths[i + 1][0] - pts_widths[i - 1][0], pts_widths[i + 1][1] - pts_widths[i - 1][1]
        L = math.hypot(px, py) or 1.0
        nx, ny = -py / L, px / L
        hw = w / 2
        left.append((x + nx * hw, y + ny * hw))
        right.append((x - nx * hw, y - ny * hw))
    draw.polygon(left + right[::-1], fill=color)
    for (x, y, w) in (pts_widths[0], pts_widths[-1]):
        r = max(1.0, w / 2)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


# 一道从左下扫到右上的墨迹笔画（三次贝塞尔加密采样，中间最粗）
p0, p1, p2, p3 = (170, 800), (330, 240), (600, 900), (860, 230)
curve = []
N = 120
for i in range(N + 1):
    t = i / N
    u = 1 - t
    x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
    w = 150 * math.sin(math.pi * (0.12 + 0.76 * t)) ** 0.7   # 两端收尖
    curve.append((x, y, max(8.0, w)))
ribbon(d, curve, INK)

# 笔尖高光：笔画末端的小黄方块（信号黄点缀）
sx, sy = 848, 252
d.rectangle((sx, sy, sx + 56, sy + 56), fill=YELLOW, outline=INK2, width=6)

# 细边框（endfield 全直角语汇）
d.rectangle((28, 28, W - 28, H - 28), outline=(30, 26, 16, 70), width=6)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ios", "Resources", "Assets.xcassets", "AppIcon.appiconset", "icon1024.png")
img.convert("RGB").save(out, "PNG")
print("icon written:", os.path.normpath(out))
