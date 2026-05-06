"""
Farmer Mode Calibration — Preprocessor

Reads ~/.claude/history.jsonl and ~/.claude/skills/, denoises prompts,
samples representative sessions, inventories skills, and outputs a clean
markdown file that Claude reads directly to perform the actual analysis.

The script does NOT interpret skill level — it prepares material for Claude.

Usage:
    python3 calibrate.py [--history PATH] [--output PATH]

What it does (printed to stderr so the user sees it):
  1. Loads all prompts from history.jsonl
  2. Removes noise (system commands, very short, duplicates, pasted blobs)
  3. Groups by session and project
  4. Samples ~60 representative prompts across early/mid/recent periods
  5. Inventories ~/.claude/skills/ (name, description, file count, size)
  6. Outputs clean markdown to the output path for Claude to read

Output: markdown file with sections:
  - Stats (counts, timeline, projects)
  - Denoising report (what was removed and why)
  - Sampled prompts (grouped by period, with project context)
  - Skills inventory (each skill with metadata)
"""

import json
import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime


def log(msg: str):
    """Print to stderr so user sees progress."""
    print(f"  [calibrate] {msg}", file=sys.stderr)


def load_history(path: str) -> list[dict]:
    prompts = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                prompts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return prompts


# --- Noise filters ---

NOISE_PATTERNS = [
    (r"^/\w+\s*$", "slash command"),                    # /compact, /model, /new etc
    (r"^!\w+\s*$", "bang command"),                      # !ls, !o etc
    (r"^\[Pasted text #\d+.*\]$", "paste-only"),         # just a paste reference
    (r"^(?:ok|yes|no|yep|nah|sure|yea|yeah|nope|k|y|n)\s*$", "single-word ack"),
    (r"^(?:continue|go|proceed|next|done|thanks|ty|thx)\s*$", "continuation"),
    (r"^.{0,8}$", "too short"),                          # under 8 chars
]

NOISE_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in NOISE_PATTERNS]


def classify_noise(text: str) -> str | None:
    """Return noise label if the prompt is noise, else None."""
    stripped = text.strip()
    for pattern, label in NOISE_COMPILED:
        if pattern.match(stripped):
            return label
    # Duplicate pasted content with no user text
    if stripped.startswith("[Pasted text") and len(stripped) < 50:
        return "paste-only"
    # Image-only
    if stripped.startswith("[Image #") and len(stripped) < 30:
        return "image-only"
    return None


def deduplicate(prompts: list[dict]) -> tuple[list[dict], int]:
    """Remove exact duplicate display text within same session."""
    seen = set()
    deduped = []
    dup_count = 0
    for p in prompts:
        key = (p.get("sessionId", ""), p.get("display", ""))
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        deduped.append(p)
    return deduped, dup_count


def denoise(prompts: list[dict]) -> tuple[list[dict], dict]:
    """Remove noise prompts. Returns (clean_prompts, removal_stats)."""
    stats = Counter()
    clean = []

    prompts, dup_count = deduplicate(prompts)
    stats["duplicates"] = dup_count

    for p in prompts:
        text = p.get("display", "")
        noise_label = classify_noise(text)
        if noise_label:
            stats[noise_label] += 1
        else:
            clean.append(p)

    return clean, dict(stats)


# --- Skills inventory ---

def inventory_skills(skills_dir: str) -> list[dict]:
    """Read each skill in ~/.claude/skills/ and extract metadata."""
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        return []

    skills = []
    for skill_dir in sorted(skills_path.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("."):
            continue

        skill_md = skill_dir / "SKILL.md"
        guide_md = skill_dir / "GUIDE.md"
        source = None
        description = ""
        name = skill_dir.name

        for candidate in [skill_md, guide_md]:
            if candidate.exists():
                source = candidate
                break

        if source:
            content = source.read_text(errors="replace")
            fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                fm = fm_match.group(1)
                nm = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
                if nm:
                    name = nm.group(1).strip().strip("'\"")
                desc = re.search(r"^description:\s*[>|]?\s*\n?((?:\s+.+\n?)+)", fm, re.MULTILINE)
                if desc:
                    description = " ".join(desc.group(1).split())
                else:
                    desc_single = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
                    if desc_single:
                        description = desc_single.group(1).strip().strip("'\"")

        file_count = sum(1 for _ in skill_dir.rglob("*") if _.is_file())
        total_size = sum(f.stat().st_size for f in skill_dir.rglob("*") if f.is_file())

        has_scripts = (skill_dir / "scripts").exists()
        has_references = (skill_dir / "references").exists()

        skills.append({
            "name": name,
            "dir": skill_dir.name,
            "description": description[:300] if description else "(no description)",
            "file_count": file_count,
            "total_size_kb": round(total_size / 1024, 1),
            "has_scripts": has_scripts,
            "has_references": has_references,
            "source_file": source.name if source else None,
        })

    return skills


# --- Output formatting ---

def format_prompt(p: dict, period: str, include_project: bool = True) -> str:
    """Format a single prompt for Claude to read."""
    text = p.get("display", "").strip()
    # Truncate very long prompts (plans, pasted content)
    if len(text) > 500:
        text = text[:500] + " [... truncated]"
    # Collapse internal newlines for readability
    text = text.replace("\n", " ↵ ")
    proj = p.get("project", "unknown").split("/")[-1]
    ts = p.get("timestamp", 0)
    date = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "?"
    return f"[{date} | {period} | {proj}] {text}"


def assign_periods(prompts: list[dict]) -> list[tuple[dict, str]]:
    """Tag each prompt with EARLY/MID/RECENT."""
    n = len(prompts)
    third = n // 3
    result = []
    for i, p in enumerate(prompts):
        if i < third:
            period = "EARLY"
        elif i < 2 * third:
            period = "MID"
        else:
            period = "RECENT"
        result.append((p, period))
    return result


def build_output(
    raw_count: int,
    clean_count: int,
    noise_stats: dict,
    projects: list[tuple[str, int]],
    timeline: dict,
    prompts_with_periods: list[tuple[dict, str]],
    skills: list[dict],
) -> str:
    """Build the markdown output for Claude to analyze."""
    lines = []

    lines.append("# Farmer Mode Calibration Data")
    lines.append("")
    lines.append("This file was generated by `calibrate.py`. Claude reads this to assess")
    lines.append("the learner's engineering skill level before starting farmer-mode coaching.")
    lines.append("")
    lines.append("**Reading instructions for Claude**: This file is large. Use the Read tool")
    lines.append("with offset/limit to read in chunks. Recommended approach:")
    lines.append("1. Read Stats + Denoising + Projects (first ~40 lines)")
    lines.append("2. Read prompts in chunks of 200 lines, taking notes on patterns")
    lines.append("3. Read Skills Inventory at the end")
    lines.append("")

    # --- Stats ---
    lines.append("## Stats")
    lines.append("")
    lines.append(f"- **Total prompts**: {raw_count}")
    lines.append(f"- **After denoising**: {clean_count} ({raw_count - clean_count} removed)")
    lines.append(f"- **Projects**: {len(projects)}")
    lines.append(f"- **First prompt**: {timeline.get('first', '?')}")
    lines.append(f"- **Last prompt**: {timeline.get('last', '?')}")
    lines.append(f"- **Days active**: {timeline.get('days', '?')}")
    lines.append("")

    # --- Denoising report ---
    lines.append("## Denoising Report")
    lines.append("")
    lines.append("What was removed and why:")
    lines.append("")
    for label, count in sorted(noise_stats.items(), key=lambda x: -x[1]):
        lines.append(f"- **{label}**: {count} prompts removed")
    lines.append("")

    # --- Projects ---
    lines.append("## Projects (by prompt count)")
    lines.append("")
    for name, count in projects[:25]:
        lines.append(f"- **{name}**: {count} prompts")
    if len(projects) > 25:
        lines.append(f"- ... and {len(projects) - 25} more projects")
    lines.append("")

    # --- All denoised prompts ---
    lines.append("## All Denoised Prompts (chronological)")
    lines.append("")
    lines.append(f"Total: {len(prompts_with_periods)} prompts. Each tagged with")
    lines.append("[date | EARLY/MID/RECENT | project].")
    lines.append("")
    lines.append("Claude: read these and assess the learner's engineering thinking.")
    lines.append("Look for decomposition, specification, verification, debugging method,")
    lines.append("state reasoning, abstraction, optimization, invariant reasoning,")
    lines.append("AI-direction skill, and delegation-without-spec patterns.")
    lines.append("")

    for p, period in prompts_with_periods:
        lines.append(f"- {format_prompt(p, period)}")

    lines.append("")

    # --- Skills inventory ---
    lines.append("## Skills Inventory (~/.claude/skills/)")
    lines.append("")
    lines.append("Each skill found in the learner's Claude Code setup.")
    lines.append("Claude must ask the learner which of these they built themselves")
    lines.append("vs. received from someone else — authorship signals engineering capability.")
    lines.append("")
    for s in skills:
        lines.append(f"### {s['name']} (`{s['dir']}/`)")
        lines.append(f"- **Description**: {s['description']}")
        lines.append(f"- **Files**: {s['file_count']} ({s['total_size_kb']} KB)")
        lines.append(f"- **Has scripts**: {'yes' if s['has_scripts'] else 'no'}")
        lines.append(f"- **Has references**: {'yes' if s['has_references'] else 'no'}")
        lines.append(f"- **Source**: {s['source_file'] or 'none found'}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Preprocess prompt history for farmer-mode calibration")
    parser.add_argument(
        "--history",
        default=str(Path.home() / ".claude" / "history.jsonl"),
        help="Path to history.jsonl",
    )
    parser.add_argument(
        "--skills-dir",
        default=str(Path.home() / ".claude" / "skills"),
        help="Path to skills directory",
    )
    parser.add_argument(
        "--output",
        default=str(Path.home() / ".claude" / "farmer-state" / "calibration.md"),
        help="Output path for calibration data (markdown)",
    )
    args = parser.parse_args()

    # Load
    log(f"Loading history from {args.history}")
    raw_prompts = load_history(args.history)
    raw_count = len(raw_prompts)
    log(f"Loaded {raw_count} prompts")

    # Denoise
    log("Denoising...")
    clean_prompts, noise_stats = denoise(raw_prompts)
    clean_count = len(clean_prompts)
    removed = raw_count - clean_count
    log(f"Removed {removed} noise prompts ({removed*100//max(raw_count,1)}% of total)")
    for label, count in sorted(noise_stats.items(), key=lambda x: -x[1])[:5]:
        log(f"  - {label}: {count}")

    # Projects
    project_counts = Counter()
    for p in clean_prompts:
        proj = p.get("project", "unknown")
        name = proj.split("/")[-1]
        project_counts[name] += 1
    projects = project_counts.most_common()
    log(f"Found {len(projects)} projects")

    # Timeline
    first_ts = raw_prompts[0].get("timestamp", 0) if raw_prompts else 0
    last_ts = raw_prompts[-1].get("timestamp", 0) if raw_prompts else 0
    timeline = {
        "first": datetime.fromtimestamp(first_ts / 1000).strftime("%Y-%m-%d") if first_ts else "?",
        "last": datetime.fromtimestamp(last_ts / 1000).strftime("%Y-%m-%d") if last_ts else "?",
        "days": round((last_ts - first_ts) / (1000 * 86400)) if first_ts and last_ts else 0,
    }

    # Assign periods
    log("Tagging prompts with period markers (EARLY/MID/RECENT)...")
    prompts_with_periods = assign_periods(clean_prompts)

    # Skills inventory
    log(f"Scanning skills in {args.skills_dir}...")
    skills = inventory_skills(args.skills_dir)
    log(f"Found {len(skills)} skills")
    for s in skills:
        log(f"  - {s['name']} ({s['file_count']} files, {s['total_size_kb']} KB)")

    # Build output
    output = build_output(
        raw_count=raw_count,
        clean_count=clean_count,
        noise_stats=noise_stats,
        projects=projects,
        timeline=timeline,
        prompts_with_periods=prompts_with_periods,
        skills=skills,
    )

    # Write
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)

    line_count = output.count("\n") + 1
    log(f"Calibration data written to {output_path}")
    log(f"Total: {raw_count} raw → {clean_count} clean prompts + {len(skills)} skills")
    log(f"Output: {line_count} lines, {len(output) // 1024} KB")

    # Print status to stdout for Claude
    print(json.dumps({
        "status": "ok",
        "output": str(output_path),
        "raw_prompts": raw_count,
        "clean_prompts": clean_count,
        "noise_removed": removed,
        "projects": len(projects),
        "skills_found": len(skills),
        "output_lines": line_count,
        "output_kb": len(output) // 1024,
    }))


if __name__ == "__main__":
    main()
