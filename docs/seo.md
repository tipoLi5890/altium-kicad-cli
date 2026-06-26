# SEO assets — single source of truth

This file is the **single source of truth** for all non-file (repo-settings) SEO assets:
the GitHub *About* string, the GitHub *Topics*, and the social-preview note. `tools/seo-apply.sh`
reads this file and applies the About/homepage/topics via `gh repo edit`. Keep them in sync here
first, then run the script — never edit them by hand in the GitHub UI.

The on-page SEO (README H1/H2 keyword headings, file extensions, comparison table, FAQ) lives in
`README.md`. The PyPI `keywords`/`classifiers` live in `pyproject.toml`. This file owns only the
three repo-settings assets below.

---

## 7.1 GitHub About (≤350 chars, exact)

```
Dual-format EDA toolkit + Claude Code plugin: read Altium binary .SchDoc/.SchLib/.PcbDoc AND KiCad .kicad_sch with no Altium or KiCad install, then run ERC/power/pinmap/BOM checks and draw KiCad schematics. Zero-dependency Python CLI built for AI coding agents. Not an Altium-to-KiCad converter.
```

Homepage (set alongside About): `https://github.com/tipoLi5890/altium-kicad-cli`

## 7.2 GitHub Topics (exactly 20, ≤50 chars, lowercase, hyphenated — no dots/underscores)

```
altium
kicad
eda
schematic
pcb
netlist
schdoc
kicad-sch
erc
electronics
hardware
pcb-design
electronic-design-automation
altium-designer
claude-code
ai-agents
cli
python
netlist-parser
circuit-design
```

## Social-preview note

GitHub renders a social-preview (Open Graph) card when the repo link is shared on X/LinkedIn/Slack.
Upload a 1280×640 px PNG/JPG under **Settings → General → Social preview**. Recommended content:

- Headline: `altium-kicad-cli` with the subline *read Altium .SchDoc & KiCad .kicad_sch — no EDA install*.
- Show the two file extensions (`.SchDoc`, `.kicad_sch`) and the `akcli` command prompt prominently —
  these are the primary search terms and reinforce the README H1.
- Include the disclaimer *Not an Altium-to-KiCad converter* so the card sets correct expectations.
- High contrast, ≤6 words per line, no fine print (the card is downscaled in feeds).

This image is a repo setting, not a committed file; there is no `gh` API for it, so set it manually.
