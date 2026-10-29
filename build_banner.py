#!/usr/bin/env python3
"""Build assets/banner.svg from profile.json and public github.com stats.

Usage: ./build_banner.py            # refresh stats from the github.com API, then build
       ./build_banner.py --offline  # reuse assets/stats.json
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "profile.json"
STATS = ROOT / "assets" / "stats.json"
ICONS = json.loads((ROOT / "assets" / "icons.json").read_text())["icons"]
OUTPUT = ROOT / "assets" / "banner.svg"
API = "https://api.github.com"

WIDTH = 960
PAD = 36
LINE = 22
CHAR = 8.4  # approximate advance of the 14px monospace font
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
TYPE_SPEED = 0.045  # seconds per typed character
PAUSE = 0.35

COLORS = {
    "bg": "#0d1117",
    "bar": "#161b22",
    "border": "#30363d",
    "text": "#e6edf3",
    "dim": "#8b949e",
    "prompt": "#7ee787",
    "path": "#79c0ff",
    "accent": "#d2a8ff",
    "number": "#ffa657",
}


def api_get(path):
    """GET a github.com API path; GITHUB_TOKEN raises the rate limit, and a
    token github.com rejects (such as an Enterprise token) is ignored."""
    request = urllib.request.Request(
        f"{API}{path}", headers={"Accept": "application/vnd.github+json"}
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code != 401 or not token:
            raise
    request.remove_header("Authorization")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def search_count(kind, query):
    """Total results of a github.com search."""
    return api_get(
        f"/search/{kind}?q={urllib.parse.quote(query, safe=':+')}&per_page=1"
    )["total_count"]


def refresh_stats(user):
    """All-time public activity of `user` on github.com."""
    account = api_get(f"/users/{user}")
    stats = {
        "issues": search_count("issues", f"author:{user}+type:issue"),
        "commented": search_count("issues", f"commenter:{user}"),
        "pull_requests": search_count("issues", f"author:{user}+type:pr"),
        "repositories": account["public_repos"],
    }
    STATS.parent.mkdir(exist_ok=True)
    STATS.write_text(json.dumps(stats, indent=2) + "\n")
    return stats


class Banner:
    def __init__(self):
        self.parts = []
        self.y = 0
        self.t = 0.4
        self.clip = 0

    def add(self, svg):
        self.parts.append(svg)

    def text(self, x, y, content, fill, size=14, weight="normal", extra=""):
        return (
            f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" {extra}>{content}</text>'
        )

    def command(self, command):
        """Type a shell command after the prompt, then advance the clock."""
        self.y += LINE + 16
        prompt = f"{escape(self.user)}@{escape(self.host)}:~$ "
        x = PAD + len(prompt) * CHAR
        width = len(command) * CHAR + 4
        duration = max(len(command) * TYPE_SPEED, 0.3)
        self.clip += 1
        cid = f"c{self.clip}"
        self.add(
            f"<g>{self.fade(self.t)}"
            + self.text(
                PAD,
                self.y,
                f'<tspan fill="{COLORS["prompt"]}">{escape(self.user)}@{escape(self.host)}</tspan>'
                f'<tspan fill="{COLORS["dim"]}">:</tspan><tspan fill="{COLORS["path"]}">~</tspan>'
                f'<tspan fill="{COLORS["dim"]}">$</tspan>',
                COLORS["text"],
            )
            + f'<clipPath id="{cid}"><rect x="{x - 2}" y="{self.y - 16}" height="22" width="{width:.0f}">'
            + self.typing(width, len(command), self.t, duration)
            + "</rect></clipPath>"
            + self.text(
                x,
                self.y,
                escape(command),
                COLORS["text"],
                extra=f'clip-path="url(#{cid})"',
            )
            + "</g>"
        )
        self.t += duration + PAUSE

    def output(self, svg_lines, height):
        """Reveal a block of output at the current time."""
        self.add(f"<g>{self.fade(self.t)}{svg_lines}</g>")
        self.y += height
        self.t += PAUSE

    # Every element is visible by default. The animations start at 0s and keep
    # the element hidden until its turn, so viewers that skip SVG animation
    # still show the complete banner.
    @staticmethod
    def fade(begin):
        end = begin + 0.25
        return (
            f'<animate attributeName="opacity" values="0;0;1" '
            f'keyTimes="0;{begin / end:.4f};1" dur="{end:.2f}s" fill="freeze"/>'
        )

    @staticmethod
    def typing(width, chars, begin, duration):
        end = begin + duration
        values = ["0"] + [f"{width * i / chars:.0f}" for i in range(chars + 1)]
        times = ["0"] + [
            f"{(begin + duration * i / (chars + 1)) / end:.4f}"
            for i in range(chars + 1)
        ]
        return (
            f'<animate attributeName="width" calcMode="discrete" dur="{end:.2f}s" fill="freeze" '
            f'values="{";".join(values)}" keyTimes="{";".join(times)}"/>'
        )


def build(profile, stats):
    b = Banner()
    b.user, b.host = profile["handle"], profile["host"]
    b.y = 36  # window bar

    b.command("whoami")
    b.output(
        b.text(PAD, b.y + 34, escape(profile["name"]), COLORS["text"], 28, "bold")
        + b.text(PAD, b.y + 60, escape(profile["tagline"]), COLORS["accent"], 15)
        + b.text(PAD, b.y + 82, escape(profile["location"]), COLORS["dim"], 13),
        86,
    )

    b.command("cat languages.txt")
    spoken = "   ".join(
        f'<tspan fill="{COLORS["text"]}">{escape(lang)}</tspan>'
        f'<tspan fill="{COLORS["dim"]}"> ({escape(level)})</tspan>'
        for lang, level in profile["spoken"]
    )
    b.output(b.text(PAD, b.y + LINE, spoken, COLORS["text"]), LINE)

    b.command("ls ~/projects")
    if "projects_note" in profile:
        notes = profile["projects_note"]
        b.output(
            "".join(
                b.text(PAD, b.y + LINE * (i + 1), escape(line), COLORS["dim"], 13)
                for i, line in enumerate(notes)
            ),
            LINE * len(notes),
        )
    else:
        column = (WIDTH - 2 * PAD) / 2
        rows = (len(profile["projects"]) + 1) // 2
        lines = []
        for i, (name, description, _url) in enumerate(profile["projects"]):
            x = PAD + (i // rows) * column
            y = b.y + LINE * (i % rows + 1)
            lines.append(
                b.text(
                    x,
                    y,
                    f'<tspan fill="{COLORS["path"]}" font-weight="bold">{escape(name)}</tspan>'
                    f'<tspan fill="{COLORS["dim"]}" font-size="12.5"> {escape(description)}</tspan>',
                    COLORS["text"],
                )
            )
        b.output("".join(lines), LINE * rows)

    b.command("cat stack.yml")
    pills, x, y = [], PAD, b.y + 10
    for label, color in (
        (label, ICONS[icons[0]]["color"])
        for _group, items in profile["groups"]
        for label, icons in items
    ):
        width = len(label) * 7.9 + 30
        if x + width > WIDTH - PAD:
            x, y = PAD, y + 30
        pills.append(
            f'<rect x="{x:.0f}" y="{y}" width="{width:.0f}" height="22" rx="11" '
            f'fill="{color}" fill-opacity="0.16" stroke="{color}" stroke-opacity="0.7"/>'
            f'<circle cx="{x + 11:.0f}" cy="{y + 11}" r="3.5" fill="{color}"/>'
            + b.text(x + 19, y + 15.5, escape(label), COLORS["text"], 12.5)
        )
        x += width + 8
    b.output("".join(pills), y - b.y + 26)

    b.command("cat interests.txt")
    b.output(
        b.text(
            PAD,
            b.y + LINE,
            f'<tspan fill="{COLORS["dim"]}">» </tspan>'
            + f'<tspan fill="{COLORS["dim"]}"> · </tspan>'.join(
                escape(i) for i in profile["interests"]
            ),
            COLORS["text"],
            13.5,
        ),
        LINE,
    )

    if stats:
        b.command(f"gh api users/{profile['stats_user']} | stats")
        items = stat_items(stats)
        b.output(
            b.text(
                PAD,
                b.y + LINE,
                f'<tspan fill="{COLORS["dim"]}">   ·   </tspan>'.join(
                    f'<tspan fill="{COLORS["number"]}" font-weight="bold">{n}</tspan>'
                    f'<tspan fill="{COLORS["text"]}"> {label}</tspan>'
                    for n, label in items
                ),
                COLORS["text"],
            ),
            LINE,
        )

    # Final prompt with a blinking cursor.
    b.y += LINE + 16
    prompt_width = len(f"{b.user}@{b.host}:~$ ") * CHAR
    b.add(
        f"<g>{b.fade(b.t)}"
        + b.text(
            PAD,
            b.y,
            f'<tspan fill="{COLORS["prompt"]}">{escape(b.user)}@{escape(b.host)}</tspan>'
            f'<tspan fill="{COLORS["dim"]}">:</tspan><tspan fill="{COLORS["path"]}">~</tspan>'
            f'<tspan fill="{COLORS["dim"]}">$</tspan>',
            COLORS["text"],
        )
        + f'<rect x="{PAD + prompt_width:.0f}" y="{b.y - 14}" width="9" height="18" fill="{COLORS["text"]}">'
        f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" dur="1.1s" '
        f'repeatCount="indefinite"/></rect></g>'
    )

    height = b.y + 28
    title = f"{b.user}@{b.host}: ~"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{escape(profile["name"])}: {escape(profile["tagline"])}">
<title>{escape(profile["name"])}</title>
<style>text{{font-family:{FONT};white-space:pre}}</style>
<defs><linearGradient id="glow" x1="0" x2="1"><stop offset="0" stop-color="#7ee787"/><stop offset="0.5" stop-color="#79c0ff"/><stop offset="1" stop-color="#d2a8ff"/></linearGradient></defs>
<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="12" fill="{COLORS["bg"]}" stroke="{COLORS["border"]}"/>
<path d="M12.5 0.5H{WIDTH - 12.5}A12 12 0 0 1 {WIDTH - 0.5} 12.5V32H0.5V12.5A12 12 0 0 1 12.5 0.5Z" fill="{COLORS["bar"]}"/>
<rect x="0.5" y="31.5" width="{WIDTH - 1}" height="2" fill="url(#glow)" opacity="0.8"/>
<circle cx="20" cy="16" r="6" fill="#ff5f56"/><circle cx="40" cy="16" r="6" fill="#ffbd2e"/><circle cx="60" cy="16" r="6" fill="#27c93f"/>
<text x="{WIDTH / 2}" y="21" text-anchor="middle" fill="{COLORS["dim"]}" font-size="12.5">{escape(title)}</text>
{chr(10).join(b.parts)}
</svg>
"""


def stat_items(stats):
    return [
        (f"{stats['issues']:,}", "issues opened"),
        (f"{stats['commented']:,}", "threads commented"),
        (f"{stats['pull_requests']:,}", "pull requests"),
        (f"{stats['repositories']:,}", "public repositories"),
    ]


SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
WAVE = {
    "bg": "#0d1117",
    "card": "#161b22",
    "border": "#30363d",
    "text": "#e6edf3",
    "dim": "#8b949e",
    "label": "#a5b4fc",
    "link": "#79c0ff",
}
HEADER = 236


def fade_in(begin):
    """Visible by default; hidden until `begin` when the viewer plays SVG animation."""
    end = begin + 0.6
    return (
        f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{begin / end:.4f};1" '
        f'dur="{end:.2f}s" fill="freeze"/>'
        f'<animateTransform attributeName="transform" type="translate" values="0 8;0 8;0 0" '
        f'keyTimes="0;{begin / end:.4f};1" dur="{end:.2f}s" fill="freeze"/>'
    )


def wave_path(base, amplitude, period, width, bottom):
    """A periodic wave twice as wide as the banner, so it can scroll seamlessly."""
    half = period / 2
    segments = "".join(
        f"q {half / 2:.1f},{-amplitude} {half:.1f},0 q {half / 2:.1f},{amplitude} {half:.1f},0"
        for _ in range(int(2 * width / period) + 1)
    )
    return f"M0,{base} {segments} V{bottom} H0 Z"


def icon(name, x, y, size=16):
    data = ICONS[name]
    scale = size / 24
    fill_rule = f' fill-rule="{data["fillRule"]}"' if "fillRule" in data else ""
    return (
        f'<path transform="translate({x:.1f} {y:.1f}) scale({scale:.4f})" '
        f'fill="{data["color"]}"{fill_rule} d="{data["path"]}"><title>{escape(data["title"])}</title></path>'
    )


def flag(code, x, y):
    """Small FR, UK, ES or DE flag, 21x14."""
    clip = f'<clipPath id="flag-{code}"><rect x="{x}" y="{y}" width="21" height="14" rx="2.5"/></clipPath>'
    if code == "es":
        body = (
            f'<rect x="{x}" y="{y}" width="21" height="14" fill="#AA151B"/>'
            f'<rect x="{x}" y="{y + 3.5}" width="21" height="7" fill="#F1BF00"/>'
        )
    elif code == "de":
        body = (
            f'<rect x="{x}" y="{y}" width="21" height="4.7" fill="#000000"/>'
            f'<rect x="{x}" y="{y + 4.66}" width="21" height="4.7" fill="#DD0000"/>'
            f'<rect x="{x}" y="{y + 9.33}" width="21" height="4.67" fill="#FFCE00"/>'
        )
    elif code == "fr":
        body = (
            f'<rect x="{x}" y="{y}" width="7" height="14" fill="#0055A4"/>'
            f'<rect x="{x + 7}" y="{y}" width="7" height="14" fill="#FFFFFF"/>'
            f'<rect x="{x + 14}" y="{y}" width="7" height="14" fill="#EF4135"/>'
        )
    else:
        cx, cy = x + 10.5, y + 7
        body = (
            f'<rect x="{x}" y="{y}" width="21" height="14" fill="#012169"/>'
            f'<path d="M{x},{y}L{x + 21},{y + 14}M{x + 21},{y}L{x},{y + 14}" stroke="#FFFFFF" stroke-width="2.8"/>'
            f'<path d="M{x},{y}L{x + 21},{y + 14}M{x + 21},{y}L{x},{y + 14}" stroke="#C8102E" stroke-width="1.1"/>'
            f'<path d="M{cx},{y}V{y + 14}M{x},{cy}H{x + 21}" stroke="#FFFFFF" stroke-width="4.4"/>'
            f'<path d="M{cx},{y}V{y + 14}M{x},{cy}H{x + 21}" stroke="#C8102E" stroke-width="2.4"/>'
        )
    return f'{clip}<g clip-path="url(#flag-{code})">{body}</g>'


def chips(items, x0, y0, max_x):
    """Lay out (label, icon_names, extra) chips; extra is (width, draw(x, y)) or None."""
    parts, x, y = [], x0, y0
    for label, icon_names, extra in items:
        prefix = 21 * len(icon_names) + (extra[0] + 5 if extra else 0)
        width = 14 + prefix + (3 if prefix else 0) + len(label) * 6.9 + 16
        if x + width > max_x:
            x, y = x0, y + 40
        parts.append(
            f'<rect x="{x:.1f}" y="{y}" width="{width:.1f}" height="30" rx="15" '
            f'fill="{WAVE["card"]}" stroke="{WAVE["border"]}"/>'
        )
        cursor = x + 14
        for name in icon_names:
            parts.append(icon(name, cursor, y + 7))
            cursor += 21
        if extra:
            parts.append(extra[1](cursor, y + 8))
            cursor += extra[0] + 5
        text_x = cursor + 3 if prefix else cursor
        parts.append(
            f'<text x="{text_x:.1f}" y="{y + 19.5}" fill="{WAVE["text"]}" font-size="13.5">'
            f"{escape(label)}</text>"
        )
        x += width + 8
    return "".join(parts), y + 30


def build_wave(profile, stats):
    width = 960
    pad = 40
    parts = []
    y = HEADER + 18
    begin = 0.3

    def section(title, body, bottom):
        nonlocal begin
        parts.append(
            f"<g>{fade_in(begin)}"
            f'<text x="{pad}" y="{section.top}" fill="{WAVE["label"]}" font-size="11.5" '
            f'font-weight="600" letter-spacing="1.6">{escape(title.upper())}</text>{body}</g>'
        )
        begin += 0.25
        return bottom

    for title, items in profile["groups"]:
        section.top = y + 14
        body, bottom = chips(
            [(label, icons, None) for label, icons in items], pad, y + 26, width - pad
        )
        y = section(title, body, bottom) + 18

    section.top = y + 14
    spoken = [
        (
            f"{lang} · {level}",
            [],
            (
                21,
                lambda x, fy, c={"French": "fr", "Spanish": "es", "German": "de"}.get(lang, "uk"): (
                    flag(c, x, fy)
                ),
            ),
        )
        for lang, level in profile["spoken"]
    ]
    body, bottom = chips(spoken, pad, y + 26, width - pad)
    y = section("Languages spoken", body, bottom) + 26

    parts.append(
        f'<rect x="{pad}" y="{y}" width="{width - 2 * pad}" height="1" fill="{WAVE["border"]}"/>'
    )
    y += 22

    section.top = y + 14
    if "projects_note" in profile:
        lines = profile["projects_note"]
        body = "".join(
            f'<text x="{pad}" y="{y + 44 + i * 24}" fill="{WAVE["text"] if i == 0 else WAVE["dim"]}" '
            f'font-size="{14.5 if i == 0 else 13}">{escape(line)}</text>'
            for i, line in enumerate(lines)
        )
        y = section("Featured projects", body, y + 44 + (len(lines) - 1) * 24 + 22) + 6
    else:
        column = (width - 2 * pad) / 2
        rows = (len(profile["projects"]) + 1) // 2
        body = []
        for i, (name, description, _url) in enumerate(profile["projects"]):
            px = pad + (i // rows) * column
            py = y + 44 + (i % rows) * 42
            body.append(
                f'<text x="{px}" y="{py}" fill="{WAVE["link"]}" font-size="14.5" font-weight="600">'
                f"{escape(name.rstrip('/'))}</text>"
                f'<text x="{px}" y="{py + 18}" fill="{WAVE["dim"]}" font-size="12.5">{escape(description)}</text>'
            )
        y = section("Featured projects", "".join(body), y + 44 + rows * 42) + 6

    section.top = y + 14
    body, bottom = chips(
        [(i, [], None) for i in profile["interests"]], pad, y + 26, width - pad
    )
    y = section("Interests", body, bottom) + 26

    if stats:
        parts.append(
            f'<rect x="{pad}" y="{y}" width="{width - 2 * pad}" height="1" fill="{WAVE["border"]}"/>'
        )
        y += 22
        section.top = y + 14
        items = stat_items(stats)
        cell = (width - 2 * pad) / len(items)
        body = "".join(
            f'<text x="{pad + cell * i + cell / 2:.1f}" y="{y + 66}" text-anchor="middle" font-size="32" '
            f'font-weight="700" fill="url(#stat)">{escape(n)}</text>'
            f'<text x="{pad + cell * i + cell / 2:.1f}" y="{y + 88}" text-anchor="middle" font-size="12.5" '
            f'fill="{WAVE["dim"]}">{escape(label)}</text>'
            for i, (n, label) in enumerate(items)
        )
        y = section("On GitHub", body, y + 92) + 10

    height = y + 24
    back = wave_path(HEADER - 34, 14, 480, width, HEADER + 2)
    front = wave_path(HEADER - 22, 11, 320, width, HEADER + 2)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(profile["name"])}: {escape(profile["tagline"])}">
<title>{escape(profile["name"])}</title>
<style>text{{font-family:{SANS};white-space:pre}}</style>
<defs>
<clipPath id="card"><rect width="{width}" height="{height}" rx="14"/></clipPath>
<linearGradient id="sky" x1="0" y1="0" x2="1" y2="0.35" spreadMethod="reflect">
<stop offset="0" stop-color="#0f766e"/><stop offset="0.35" stop-color="#2563eb"/><stop offset="0.7" stop-color="#7c3aed"/><stop offset="1" stop-color="#db2777"/>
<animateTransform attributeName="gradientTransform" type="translate" values="0 0;1 0;0 0" dur="16s" repeatCount="indefinite"/>
</linearGradient>
<linearGradient id="stat" x1="0" x2="1"><stop offset="0" stop-color="#5eead4"/><stop offset="0.5" stop-color="#93c5fd"/><stop offset="1" stop-color="#c4b5fd"/></linearGradient>
</defs>
<g clip-path="url(#card)">
<rect width="{width}" height="{height}" fill="{WAVE["bg"]}"/>
<rect width="{width}" height="{HEADER}" fill="url(#sky)"/>
<path d="{back}" fill="#ffffff" fill-opacity="0.14"><animateTransform attributeName="transform" type="translate" values="0 0;-480 0" dur="14s" repeatCount="indefinite"/></path>
<path d="{front}" fill="{WAVE["bg"]}"><animateTransform attributeName="transform" type="translate" values="-320 0;0 0" dur="9s" repeatCount="indefinite"/></path>
<text x="{width / 2}" y="92" text-anchor="middle" fill="#ffffff" font-size="42" font-weight="800" letter-spacing="0.5">{escape(profile["name"])}</text>
<text x="{width / 2}" y="128" text-anchor="middle" fill="#e0e7ff" font-size="18">{escape(profile["tagline"])}</text>
<text x="{width / 2}" y="156" text-anchor="middle" fill="#ffffff" fill-opacity="0.75" font-size="13">{escape(profile["location"])}</text>
{chr(10).join(parts)}
</g>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="none" stroke="{WAVE["border"]}"/>
</svg>
"""


def main():
    profile = json.loads(PROFILE.read_text())
    style = profile.get("style", "wave")
    if "--style" in sys.argv:
        style = sys.argv[sys.argv.index("--style") + 1]
    if "--offline" in sys.argv:
        stats = json.loads(STATS.read_text()) if STATS.exists() else None
    else:
        stats = refresh_stats(profile["stats_user"])
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        build_wave(profile, stats) if style == "wave" else build(profile, stats)
    )
    print(
        f"wrote {OUTPUT.relative_to(ROOT)} ({style})"
        + (f" with {stats}" if stats else "")
    )


if __name__ == "__main__":
    main()
