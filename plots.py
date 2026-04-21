"""Plotting module for Tonkkabot — temperature charts with a tönkkä-o-meter mascot."""

import io
import math
import random
from typing import BinaryIO

import matplotlib.patheffects as pe
from cachetools import cached, TTLCache
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.patches import (
    Circle,
    Ellipse,
    FancyArrowPatch,
    FancyBboxPatch,
    PathPatch,
    Polygon,
)
from matplotlib.path import Path
from pytz import timezone
import seaborn as sns

import data
from data import TONKKA_THRESHOLD

sns.set_theme(style="whitegrid")

HELSINKI = timezone("Europe/Helsinki")

cache_history = TTLCache(maxsize=100, ttl=60)
cache_forecast = TTLCache(maxsize=100, ttl=60)

# Five mood bands, selected by the max temperature in the plotted window.
MOOD_FREEZING = "freezing"  # < 0°C     — sad, tears, blue tint
MOOD_COLD = "cold"          # 0–10°C    — bored, flat mouth
MOOD_MILD = "mild"          # 10–15°C   — smirk, raised brow
MOOD_WARM = "warm"          # 15–20°C   — grin, sparkles
MOOD_TONKKA = "tonkka"      # ≥ 20°C    — ecstatic, dollar eyes, rocket

_MOOD_BREAKS = [
    (0.0, MOOD_FREEZING),
    (10.0, MOOD_COLD),
    (15.0, MOOD_MILD),
    (TONKKA_THRESHOLD, MOOD_WARM),
]


def _mood_for(max_temp: float) -> str:
    for upper, mood in _MOOD_BREAKS:
        if max_temp < upper:
            return mood
    return MOOD_TONKKA


def _bg_tint(max_temp: float) -> tuple:
    """Axes facecolor — icy blue when freezing, warm peach when tönkkä."""
    # Clamp to [-15, 25] then normalize to [0, 1]
    t = max(-15.0, min(25.0, max_temp))
    x = (t + 15.0) / 40.0
    # Interpolate between cold and hot ends
    cold = (0.82, 0.90, 0.98)
    mid = (0.97, 0.97, 0.97)
    hot = (1.00, 0.87, 0.78)
    if x < 0.5:
        k = x / 0.5
        return tuple(c * (1 - k) + m * k for c, m in zip(cold, mid))
    k = (x - 0.5) / 0.5
    return tuple(m * (1 - k) + h * k for m, h in zip(mid, hot))


# Single closed outline of a wine glass — usable as a scatter marker or to
# draw large instances. Coordinates roughly fit inside a 1.4 × 2.0 box.
_WINE_GLASS_MARKER = Path(
    vertices=[
        (-0.55, 0.70),   # rim left
        (0.55, 0.70),    # rim right
        (0.08, -0.12),   # right of bowl → top-right of stem
        (0.08, -0.55),   # stem right bottom
        (0.40, -0.55),   # base top-right
        (0.40, -0.72),   # base bottom-right
        (-0.40, -0.72),  # base bottom-left
        (-0.40, -0.55),  # base top-left
        (-0.08, -0.55),  # stem left bottom
        (-0.08, -0.12),  # stem left top → back into bowl
        (-0.55, 0.70),   # close to rim left
    ],
    codes=[Path.MOVETO] + [Path.LINETO] * 9 + [Path.CLOSEPOLY],
)


def _draw_decor(ax, mood: str) -> None:
    """Decorative doodles — snowflakes when cold, sparkles + wine glasses when hot.

    Markers are matplotlib vector paths so rendering doesn't depend on any
    font. Everything is laid out in axes-fraction coordinates.
    """
    seeds = {"freezing": 1, "cold": 2, "mild": 3, "warm": 4, "tonkka": 5}
    rng = random.Random(seeds[mood])

    def scatter_markers(count, marker, color, size_range, alpha):
        xs = [rng.uniform(0.02, 0.98) for _ in range(count)]
        ys = [rng.uniform(0.05, 0.95) for _ in range(count)]
        sizes = [rng.uniform(*size_range) for _ in range(count)]
        kwargs = {"s": sizes, "marker": marker, "color": color,
                  "alpha": alpha, "transform": ax.transAxes, "zorder": 1}
        # Wine-glass marker gets a dark outline; "+" is unfilled and can't take one.
        if marker is _WINE_GLASS_MARKER:
            kwargs["edgecolors"] = "#3a1418"
        elif marker != "+":
            kwargs["edgecolors"] = "none"
        ax.scatter(xs, ys, **kwargs)

    if mood == MOOD_FREEZING:
        scatter_markers(26, "*", "#6aa7d6", (60, 220), 0.45)
        scatter_markers(14, "+", "#4d87b8", (40, 160), 0.55)
    elif mood == MOOD_COLD:
        scatter_markers(10, "*", "#6aa7d6", (60, 160), 0.35)
    elif mood == MOOD_WARM:
        scatter_markers(10, "*", "#ff8a3d", (80, 200), 0.35)
        scatter_markers(8, _WINE_GLASS_MARKER, "#722f37", (120, 280), 0.45)
    elif mood == MOOD_TONKKA:
        scatter_markers(14, "*", "#ffb84d", (100, 260), 0.40)
        scatter_markers(16, _WINE_GLASS_MARKER, "#722f37", (200, 520), 0.50)


def _draw_tear(ax, x: float, y: float) -> None:
    """A single teardrop — pointy top, round bottom."""
    path = Path(
        [(x, y), (x - 0.08, y - 0.22), (x, y - 0.32),
         (x + 0.08, y - 0.22), (x, y)],
        [Path.MOVETO, Path.CURVE3, Path.CURVE3, Path.CURVE3, Path.CURVE3],
    )
    ax.add_patch(PathPatch(
        path, facecolor="#6ec1ff", edgecolor="#2a6db0", linewidth=1, alpha=0.9, zorder=5,
    ))


def _draw_sweat(ax, x: float, y: float, color: str = "#7cc2ff") -> None:
    """Anime-style sweat drop — slightly bigger than a tear."""
    path = Path(
        [(x, y), (x - 0.10, y - 0.18), (x, y - 0.30),
         (x + 0.10, y - 0.18), (x, y)],
        [Path.MOVETO, Path.CURVE3, Path.CURVE3, Path.CURVE3, Path.CURVE3],
    )
    ax.add_patch(PathPatch(
        path, facecolor=color, edgecolor="#333", linewidth=1, alpha=0.95, zorder=5,
    ))


def _draw_rays(ax, cx: float, cy: float) -> None:
    """Radial rays behind an ecstatic head — anime reaction style."""
    for i in range(14):
        ang = i * (360 / 14)
        r0 = 0.95
        r1 = 1.6
        x0 = cx + r0 * math.cos(math.radians(ang))
        y0 = cy + r0 * math.sin(math.radians(ang))
        x1 = cx + r1 * math.cos(math.radians(ang))
        y1 = cy + r1 * math.sin(math.radians(ang))
        ax.plot([x0, x1], [y0, y1],
                color="#ffcf33", linewidth=2.4, alpha=0.75, zorder=1,
                solid_capstyle="round")


def _draw_rocket(ax, x: float, y: float) -> None:
    """Tiny rocket — body, nose cone, flame."""
    # Body
    ax.add_patch(FancyBboxPatch(
        (x - 0.08, y - 0.18), 0.16, 0.28,
        boxstyle="round,pad=0.01,rounding_size=0.04",
        facecolor="#eeeeee", edgecolor="#222", linewidth=1, zorder=6,
    ))
    # Nose cone
    ax.add_patch(Polygon(
        [(x - 0.08, y + 0.10), (x + 0.08, y + 0.10), (x, y + 0.26)],
        closed=True, facecolor="#c8102e", edgecolor="#222", linewidth=1, zorder=6,
    ))
    # Window
    ax.add_patch(Circle(
        (x, y + 0.02), 0.035,
        facecolor="#6ec1ff", edgecolor="#222", linewidth=0.8, zorder=7,
    ))
    # Flame
    ax.add_patch(Polygon(
        [(x - 0.055, y - 0.18), (x + 0.055, y - 0.18), (x, y - 0.34)],
        closed=True, facecolor="#ff8a3d", edgecolor="#c8102e", linewidth=1, zorder=6,
    ))


def _skin_color(mood: str) -> str:
    """Mood-dependent face color, shading blue for freezing."""
    return {
        MOOD_FREEZING: "#b6c8d9",  # blue-ish
        MOOD_COLD: "#cdbfaa",
        MOOD_MILD: "#d9bea0",
        MOOD_WARM: "#e4c8aa",
        MOOD_TONKKA: "#eccf9c",
    }[mood]


def _draw_mascot(fig, mood: str) -> None:
    """Draw the tönkkä-o-meter mascot in the top-right corner.

    Five moods: freezing → cold → mild → warm → tönkkä. Each drives face
    geometry (eyebrows, mouth, pupils), props (tears, sweat, rocket),
    and background effects (rays).
    """
    ax = fig.add_axes([0.73, 0.68, 0.24, 0.30])
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.3, 1.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.patch.set_alpha(0.0)

    # Rays behind the head when ecstatic
    if mood == MOOD_TONKKA:
        _draw_rays(ax, 0.0, 0.15)

    _draw_mascot_arrow(ax, mood)
    _draw_mascot_suit(ax, mood)
    _draw_mascot_head(ax, mood)
    _draw_eyes(ax, mood)
    ax.plot([0.0, 0.06], [0.10, -0.06],
            color="#8a6b4a", linewidth=1.5, solid_capstyle="round", zorder=5)
    _draw_mouth(ax, mood)
    _draw_mascot_props(ax, mood)
    _draw_mascot_caption(ax, mood)


_ARROW_BY_MOOD = {
    MOOD_FREEZING: ((-0.85, 1.00), (-1.25, -0.45), "#3a6fa0", 0.75),
    MOOD_COLD: None,
    MOOD_MILD: ((-1.25, -0.40), (-0.85, 0.65), "#ffa64d", 0.80),
    MOOD_WARM: ((-1.25, -0.55), (-0.85, 0.95), "#ff8a3d", 0.90),
    MOOD_TONKKA: ((-1.28, -0.65), (-0.95, 1.20), "#ff2d1f", 0.95),
}


def _draw_mascot_arrow(ax, mood: str) -> None:
    """Upward (or downward for freezing) arrow beside the mascot."""
    arrow = _ARROW_BY_MOOD.get(mood)
    if arrow is None:
        return
    start, end, color, alpha = arrow
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=22,
        linewidth=3.5, color=color, alpha=alpha, zorder=2,
    ))


_TIE_COLOR = {
    MOOD_FREEZING: "#3a6fa0",
    MOOD_COLD: "#4a7ca8",
    MOOD_MILD: "#2970ff",
    MOOD_WARM: "#ff5a1f",
    MOOD_TONKKA: "#ffcf33",
}


def _draw_mascot_suit(ax, mood: str) -> None:
    """Suit jacket, shirt V, and mood-colored tie."""
    ax.add_patch(FancyBboxPatch(
        (-1.0, -1.25), 2.0, 0.7,
        boxstyle="round,pad=0.02,rounding_size=0.18",
        facecolor="#1a1a1a", edgecolor="black", linewidth=1.5, zorder=3,
    ))
    ax.add_patch(Polygon(
        [(-0.24, -0.55), (0.0, -0.95), (0.24, -0.55)],
        closed=True, facecolor="white", edgecolor="#1a1a1a", linewidth=1.2, zorder=4,
    ))
    ax.add_patch(Polygon(
        [(-0.08, -0.68), (0.08, -0.68), (0.12, -0.95),
         (0.0, -1.15), (-0.12, -0.95)],
        closed=True, facecolor=_TIE_COLOR[mood], edgecolor="black",
        linewidth=1, zorder=5,
    ))


def _draw_mascot_head(ax, mood: str) -> None:
    """Head ellipse and cheek blush."""
    ax.add_patch(Ellipse(
        (0, 0.15), width=1.4, height=1.65,
        facecolor=_skin_color(mood), edgecolor="#2b1e14", linewidth=1.8, zorder=4,
    ))
    if mood == MOOD_FREEZING:
        cheek = "#7aaad6"
    elif mood in (MOOD_WARM, MOOD_TONKKA):
        cheek = "#ff8a8a"
    else:
        return
    for cx in (-0.42, 0.42):
        ax.add_patch(Ellipse(
            (cx, 0.02), 0.22, 0.12,
            facecolor=cheek, edgecolor="none", alpha=0.55, zorder=5,
        ))


def _draw_mascot_props(ax, mood: str) -> None:
    """Extra props keyed to mood — tears, sweat drops, rockets, and a nose icicle."""
    if mood == MOOD_FREEZING:
        # Twin tears from both eyes
        _draw_tear(ax, -0.32, 0.12)
        _draw_tear(ax, 0.32, 0.12)
        # Icicle hanging off the nose
        ax.add_patch(Polygon(
            [(-0.05, 0.05), (0.10, 0.00), (0.02, -0.28)],
            closed=True, facecolor="#b8e0ff", edgecolor="#4a8cba",
            linewidth=1, alpha=0.9, zorder=5,
        ))
    elif mood == MOOD_WARM:
        _draw_sweat(ax, 0.58, 0.50)
        _draw_sweat(ax, -0.60, 0.45, color="#9ad0ff")
    elif mood == MOOD_TONKKA:
        # Rocket + tears of joy + cluster of sweat beads
        _draw_rocket(ax, 1.05, 0.55)
        _draw_tear(ax, -0.48, 0.10)
        _draw_tear(ax, 0.48, 0.10)
        _draw_sweat(ax, -0.82, 0.85, color="#ffd06a")
        _draw_sweat(ax, 0.80, 0.95, color="#ffd06a")


_CAPTION = {
    MOOD_FREEZING: ("not tönks", "#6aa7d6"),
    MOOD_COLD: ("meh", "#888"),
    MOOD_MILD: ("tönks?", "#e0a030"),
    MOOD_WARM: ("tönks", "#ff8a3d"),
    MOOD_TONKKA: ("TÖNKKÄ!", "#ff2d1f"),
}


def _draw_mascot_caption(ax, mood: str) -> None:
    """Meme-style caption under the suit."""
    text, color = _CAPTION[mood]
    ax.text(
        0.0, -1.45, text,
        fontsize=12, fontweight="heavy",
        color=color, ha="center", va="center",
        rotation=0, zorder=6,
        path_effects=[pe.withStroke(linewidth=3, foreground="white")],
    )


def _draw_wine_glass(ax, center: tuple, size: float, *,
                     colors: tuple = ("#722f37", "#2b1e14"),
                     zorder: int = 6) -> None:
    """Tiny wine glass icon centered at `center`, height ≈ 1.5 × `size`.

    `colors` is a (wine, glass) pair: the bowl fill and the stem/base color.
    """
    cx, cy = center
    wine, glass = colors
    s = size
    # Bowl — triangle
    ax.add_patch(Polygon(
        [(cx - 0.55 * s, cy + 0.70 * s),
         (cx + 0.55 * s, cy + 0.70 * s),
         (cx, cy - 0.10 * s)],
        closed=True, facecolor=wine, edgecolor=glass,
        linewidth=0.9, zorder=zorder,
    ))
    # Stem
    ax.add_patch(Polygon(
        [(cx - 0.05 * s, cy - 0.10 * s), (cx + 0.05 * s, cy - 0.10 * s),
         (cx + 0.05 * s, cy - 0.65 * s), (cx - 0.05 * s, cy - 0.65 * s)],
        closed=True, facecolor=glass, edgecolor=glass,
        linewidth=0.8, zorder=zorder,
    ))
    # Base
    ax.add_patch(Polygon(
        [(cx - 0.38 * s, cy - 0.65 * s), (cx + 0.38 * s, cy - 0.65 * s),
         (cx + 0.38 * s, cy - 0.73 * s), (cx - 0.38 * s, cy - 0.73 * s)],
        closed=True, facecolor=glass, edgecolor=glass,
        linewidth=0.8, zorder=zorder,
    ))


_BROW_PLOTS = {
    # Each entry: list of (xs, ys, linewidth) line segments.
    MOOD_FREEZING: [
        ([-0.55, -0.18], [0.38, 0.52], 4.2),   # deeply angled ∧ left
        ([0.18, 0.55], [0.52, 0.38], 4.2),     # ∧ right
        ([-0.05, 0.05], [0.55, 0.55], 1.8),    # worry line
    ],
    MOOD_COLD: [
        ([-0.52, -0.18], [0.44, 0.44], 3.2),
        ([0.18, 0.52], [0.44, 0.44], 3.2),
    ],
    MOOD_MILD: [
        ([-0.50, -0.18], [0.42, 0.48], 3.2),   # left normal
        ([0.18, 0.52], [0.66, 0.40], 4.0),     # right: DRAMATIC raise
    ],
    MOOD_WARM: [
        ([-0.55, -0.35, -0.15], [0.50, 0.62, 0.55], 3.4),
        ([0.15, 0.35, 0.55], [0.55, 0.62, 0.50], 3.4),
    ],
    MOOD_TONKKA: [
        ([-0.60, -0.32, -0.08], [0.42, 0.78, 0.60], 4.4),
        ([0.08, 0.32, 0.60], [0.60, 0.78, 0.42], 4.4),
    ],
}


def _draw_brows(ax, mood: str) -> None:
    """Eyebrows — asymmetric for mild, cranked for tönkkä, droopy for freezing."""
    for xs, ys, lw in _BROW_PLOTS[mood]:
        ax.plot(xs, ys, color="#2b1e14", linewidth=lw,
                solid_capstyle="round", solid_joinstyle="round", zorder=6)


def _draw_eyes(ax, mood: str) -> None:
    """Eyes + brows, cranked per mood."""
    _draw_brows(ax, mood)

    if mood == MOOD_FREEZING:
        # Squeezed-shut crying eyes — curved arcs
        for cx in (-0.32, 0.32):
            ax.plot([cx - 0.17, cx, cx + 0.17], [0.20, 0.30, 0.20],
                    color="#2b1e14", linewidth=3.0,
                    solid_capstyle="round", solid_joinstyle="round", zorder=6)
        return

    if mood == MOOD_COLD:
        # Dead-inside pinprick eyes
        for cx in (-0.32, 0.32):
            ax.add_patch(Circle((cx, 0.28), 0.05, color="#111", zorder=6))
        return

    if mood == MOOD_WARM:
        # Happy crescents ︶ ︶
        for cx in (-0.32, 0.32):
            ax.plot([cx - 0.17, cx, cx + 0.17], [0.34, 0.22, 0.34],
                    color="#2b1e14", linewidth=3.2,
                    solid_capstyle="round", solid_joinstyle="round", zorder=6)
        return

    # MILD: asymmetric squint + open eye
    if mood == MOOD_MILD:
        # Left eye open with pupil
        ax.add_patch(Ellipse(
            (-0.32, 0.28), 0.26, 0.22,
            facecolor="white", edgecolor="#2b1e14", linewidth=1.3, zorder=5,
        ))
        ax.add_patch(Circle((-0.30, 0.30), 0.055, color="#111", zorder=6))
        # Right eye narrowed — a flat half-oval
        ax.plot([0.18, 0.32, 0.46], [0.26, 0.30, 0.26],
                color="#2b1e14", linewidth=3.0,
                solid_capstyle="round", solid_joinstyle="round", zorder=6)
        return

    # TONKKA: BULGING eyes with wine-glass pupils
    for cx in (-0.32, 0.32):
        ax.add_patch(Ellipse(
            (cx, 0.30), 0.40, 0.36,
            facecolor="white", edgecolor="#2b1e14", linewidth=1.8, zorder=5,
        ))
        _draw_wine_glass(ax, (cx, 0.28), 0.22,
                         colors=("#8e1b2a", "#222"), zorder=7)


def _draw_mouth(ax, mood: str) -> None:
    """Mouth — pushed further at each extreme."""
    if mood == MOOD_FREEZING:
        # Open wailing mouth — an upside-down U
        ax.add_patch(Ellipse(
            (0, -0.40), width=0.42, height=0.26,
            facecolor="#2a0d0d", edgecolor="#2b1e14", linewidth=2, zorder=6,
        ))
        # Downturned lip overlay
        ax.plot([-0.25, -0.10, 0.0, 0.10, 0.25], [-0.32, -0.40, -0.44, -0.40, -0.32],
                color="#2b1e14", linewidth=2.6,
                solid_capstyle="round", solid_joinstyle="round", zorder=7)
        return
    if mood == MOOD_COLD:
        ax.plot([-0.28, 0.28], [-0.30, -0.30],
                color="#2b1e14", linewidth=3,
                solid_capstyle="round", zorder=6)
        return
    if mood == MOOD_MILD:
        # Pronounced smirk with a dimple dot
        ax.plot([-0.30, -0.05, 0.15, 0.32], [-0.36, -0.32, -0.20, -0.05],
                color="#2b1e14", linewidth=3.0,
                solid_capstyle="round", solid_joinstyle="round", zorder=6)
        ax.add_patch(Circle((0.36, -0.12), 0.018, color="#2b1e14", zorder=6))
        return
    if mood == MOOD_WARM:
        # Open grin with teeth
        ax.add_patch(Ellipse(
            (0, -0.28), width=0.60, height=0.32,
            facecolor="#2a0d0d", edgecolor="#2b1e14", linewidth=2, zorder=6,
        ))
        ax.add_patch(FancyBboxPatch(
            (-0.22, -0.20), 0.44, 0.08,
            boxstyle="round,pad=0.0,rounding_size=0.02",
            facecolor="white", edgecolor="#2b1e14", linewidth=0.8, zorder=7,
        ))
        return
    # TONKKA — jaw dropped, tongue out, teeth flashing
    ax.add_patch(Ellipse(
        (0, -0.32), width=0.78, height=0.48,
        facecolor="#2a0d0d", edgecolor="#2b1e14", linewidth=2.2, zorder=6,
    ))
    # Top row of teeth
    ax.add_patch(FancyBboxPatch(
        (-0.30, -0.20), 0.60, 0.09,
        boxstyle="round,pad=0.0,rounding_size=0.02",
        facecolor="white", edgecolor="#2b1e14", linewidth=0.8, zorder=7,
    ))
    # Tongue lolling out
    ax.add_patch(Ellipse(
        (0, -0.50), width=0.34, height=0.22,
        facecolor="#ff4d64", edgecolor="#2b1e14", linewidth=1.4, zorder=7,
    ))
    # Tongue midline
    ax.plot([0, 0], [-0.58, -0.45],
            color="#8a1a2a", linewidth=1, solid_capstyle="round", zorder=8)


def temperature_plot(df, title: str) -> BinaryIO:
    """Render the temperature line + threshold + mood mascot into a PNG BytesIO."""
    max_temp = float(df["temp"].max())
    mood = _mood_for(max_temp)

    fig, ax = plt.subplots(figsize=(10, 6), dpi=200)
    try:
        ax.set_facecolor(_bg_tint(max_temp))

        _draw_decor(ax, mood)

        # Shade the "tönkkä achieved" zone above threshold
        ax.axhspan(TONKKA_THRESHOLD, 50, color="#ff3b30", alpha=0.08, zorder=0)

        # Main temperature line with marker dots + white halo
        ax.plot(
            df["time"], df["temp"],
            color="#c8102e", linewidth=2.6,
            marker="o", markersize=3.2, markeredgecolor="white", markeredgewidth=0.4,
            label="Helsinki-Vantaa, EFHK", zorder=3,
            path_effects=[pe.Stroke(linewidth=4.5, foreground="white", alpha=0.7), pe.Normal()],
        )

        # Tönkkä fill
        ax.fill_between(
            df["time"], df["temp"], TONKKA_THRESHOLD,
            where=(df["temp"] >= TONKKA_THRESHOLD),
            interpolate=True, color="#ff3b30", alpha=0.35, zorder=2,
            label="Tönkkä!",
        )

        # Threshold reference
        ax.axhline(TONKKA_THRESHOLD, ls="--", color="black", linewidth=1.5,
                   label=f"Pääpäivä ({TONKKA_THRESHOLD:.0f}°C)", zorder=2)

        # Annotate the peak
        max_idx = df["temp"].idxmax()
        max_time = df.loc[max_idx, "time"]
        ax.annotate(
            f"{max_temp:.1f}°C",
            xy=(max_time, max_temp),
            xytext=(0, 14), textcoords="offset points",
            fontsize=10, fontweight="bold", ha="center", zorder=5,
            bbox={"boxstyle": "round,pad=0.35", "fc": "#ffeb3b",
                  "ec": "#2b1e14", "lw": 1.2, "alpha": 0.95},
        )

        _style_axes(ax, title)

        _draw_mascot(fig, mood)

        return _render(fig, title)
    finally:
        plt.close(fig)


def _style_axes(ax, title: str) -> None:
    """Apply labels, title, legend, date formatter, and the visible grid."""
    ax.set_xlabel("Aika", fontsize=11)
    ax.set_ylabel("Lämpötila " + "\N{DEGREE SIGN}" + "C", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)
    ax.grid(True, which="major", color="#4a4a4a", alpha=0.55,
            linestyle="--", linewidth=0.9, zorder=1.5)
    ax.minorticks_on()
    ax.grid(True, which="minor", color="#4a4a4a", alpha=0.25,
            linestyle=":", linewidth=0.6, zorder=1.5)
    ax.xaxis.set_major_formatter(DateFormatter("%H:%M\n%d.%m.", tz=HELSINKI))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")


def _render(fig, title: str) -> BinaryIO:
    """Save the figure to a BytesIO. Caller is responsible for closing `fig`."""
    bio = io.BytesIO()
    bio.name = f"{title}.png"
    fig.savefig(bio, format="png", bbox_inches="tight", dpi=200)
    return bio


def _placeholder(title: str) -> BinaryIO:
    """Fallback image when no data is available."""
    fig, ax = plt.subplots(figsize=(8, 5), dpi=200)
    try:
        ax.text(0.5, 0.5, "Ei tietoja saatavilla",
                ha="center", va="center", transform=ax.transAxes, fontsize=16)
        ax.set_title(title)
        return _render(fig, title)
    finally:
        plt.close(fig)


@cached(cache_history)
def history(hours: int = 24) -> BinaryIO:
    """Render the last `hours` of observations (cached for 60s)."""
    df = data.fetch_data(hourdelta=hours + 2)
    if df.empty:
        return _placeholder(f"Edellinen {hours}h")
    return temperature_plot(df, f"Edellinen {hours}h")


@cached(cache_forecast)
def forecast(hours: int = 48) -> BinaryIO:
    """Render the next `hours` of forecast (cached for 60s)."""
    df = data.fetch_data()
    if df.empty:
        return _placeholder(f"{hours}h Ennuste")
    df = df.iloc[0 : hours + 1, :]
    return temperature_plot(df, f"{hours}h Ennuste")
