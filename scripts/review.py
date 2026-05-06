"""
Farmer Mode Weekly Review — Preprocessor

Analyzes the last N days of prompt history against the current state.md
to produce a review report. Claude reads this to assess progress,
regression, and what to focus on next.

Usage:
    python3 review.py [--days 7] [--history PATH] [--state PATH] [--output PATH]

What it does:
  1. Loads state.md to get current demonstrated/frontier/review schedule
  2. Loads last N days of prompts from history.jsonl
  3. Denoises and formats them for Claude
  4. Compares recent activity against skill graph
  5. Flags due/overdue spaced reviews
  6. Outputs a markdown review brief for Claude to analyze
"""

import json
import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timedelta


def log(msg: str):
    print(f"  [review] {msg}", file=sys.stderr)


def load_history(path: str, since_ts: int) -> list[dict]:
    """Load only prompts after since_ts (ms epoch)."""
    prompts = []
    with open(path) as f:
        for line in f:
            try:
                obj = json.loads(line)
                if obj.get("timestamp", 0) >= since_ts:
                    prompts.append(obj)
            except json.JSONDecodeError:
                continue
    return prompts


def load_state(path: str) -> str:
    """Load state.md as raw text."""
    p = Path(path)
    if p.exists():
        return p.read_text()
    return ""


# Reuse noise filters from calibrate.py
NOISE_PATTERNS = [
    (r"^/\w+\s*$", "slash command"),
    (r"^!\w+\s*$", "bang command"),
    (r"^\[Pasted text #\d+.*\]$", "paste-only"),
    (r"^(?:ok|yes|no|yep|nah|sure|yea|yeah|nope|k|y|n)\s*$", "single-word ack"),
    (r"^(?:continue|go|proceed|next|done|thanks|ty|thx)\s*$", "continuation"),
    (r"^.{0,8}$", "too short"),
]
NOISE_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in NOISE_PATTERNS]


def is_noise(text: str) -> bool:
    stripped = text.strip()
    for pattern, _ in NOISE_COMPILED:
        if pattern.match(stripped):
            return True
    if stripped.startswith("[Pasted text") and len(stripped) < 50:
        return True
    if stripped.startswith("[Image #") and len(stripped) < 30:
        return True
    return False


def denoise(prompts: list[dict]) -> list[dict]:
    seen = set()
    clean = []
    for p in prompts:
        text = p.get("display", "")
        key = (p.get("sessionId", ""), text)
        if key in seen:
            continue
        seen.add(key)
        if not is_noise(text):
            clean.append(p)
    return clean


def parse_reviews_due(state_text: str, as_of: datetime) -> list[dict]:
    """Extract scheduled reviews and flag which are due/overdue."""
    reviews = []
    in_reviews = False
    for line in state_text.split("\n"):
        if "## Scheduled Reviews" in line:
            in_reviews = True
            continue
        if in_reviews and line.startswith("##"):
            break
        if in_reviews and "|" in line and "pending" in line.lower():
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                skill = parts[0]
                date_str = parts[1]
                try:
                    review_date = datetime.strptime(date_str, "%Y-%m-%d")
                    is_due = review_date.date() <= as_of.date()
                    days_overdue = (as_of.date() - review_date.date()).days if is_due else 0
                    reviews.append({
                        "skill": skill,
                        "review_date": date_str,
                        "is_due": is_due,
                        "days_overdue": days_overdue,
                    })
                except ValueError:
                    pass
    return reviews


def parse_frontier(state_text: str) -> list[str]:
    """Extract frontier skill names."""
    frontier = []
    in_frontier = False
    for line in state_text.split("\n"):
        if "## Frontier Skills" in line:
            in_frontier = True
            continue
        if in_frontier and line.startswith("##"):
            break
        if in_frontier and line.strip().startswith("- ["):
            match = re.match(r"- \[.\]\s+(.+?)(?:\s+—|$)", line.strip())
            if match:
                frontier.append(match.group(1).strip())
    return frontier


def parse_demonstrated(state_text: str) -> list[str]:
    """Extract demonstrated skill names."""
    demonstrated = []
    in_demo = False
    for line in state_text.split("\n"):
        if "## Demonstrated Skills" in line:
            in_demo = True
            continue
        if in_demo and line.startswith("##"):
            break
        if in_demo and "|" in line and "2026" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts:
                demonstrated.append(parts[0])
    return demonstrated


def format_prompt(p: dict) -> str:
    text = p.get("display", "").strip()
    if len(text) > 500:
        text = text[:500] + " [... truncated]"
    text = text.replace("\n", " ↵ ")
    proj = p.get("project", "unknown").split("/")[-1]
    ts = p.get("timestamp", 0)
    date = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "?"
    return f"[{date} | {proj}] {text}"


def build_review(
    days: int,
    raw_count: int,
    clean_count: int,
    clean_prompts: list[dict],
    state_text: str,
    demonstrated: list[str],
    frontier: list[str],
    reviews_due: list[dict],
    projects: list[tuple[str, int]],
) -> str:
    lines = []

    lines.append("# Farmer Mode Weekly Review")
    lines.append("")
    lines.append(f"Review period: last {days} days")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # --- Summary ---
    lines.append("## Period Stats")
    lines.append("")
    lines.append(f"- **Prompts this period**: {raw_count} raw, {clean_count} after denoising")
    lines.append(f"- **Projects active**: {len(projects)}")
    lines.append(f"- **Demonstrated skills**: {len(demonstrated)}")
    lines.append(f"- **Frontier skills**: {len(frontier)}")
    lines.append(f"- **Reviews due/overdue**: {sum(1 for r in reviews_due if r['is_due'])}")
    lines.append("")

    # --- Projects this period ---
    lines.append("## Projects This Period")
    lines.append("")
    for name, count in projects[:15]:
        lines.append(f"- **{name}**: {count} prompts")
    lines.append("")

    # --- Reviews due ---
    if reviews_due:
        lines.append("## Spaced Reviews Due")
        lines.append("")
        lines.append("These skills were previously demonstrated but are scheduled for review.")
        lines.append("Claude should test these during the review session.")
        lines.append("")
        for r in reviews_due:
            status = f"**OVERDUE by {r['days_overdue']}d**" if r['days_overdue'] > 0 else "due today"
            lines.append(f"- **{r['skill']}** — scheduled {r['review_date']} ({status})")
        lines.append("")

    # --- Current frontier ---
    lines.append("## Current Frontier Skills")
    lines.append("")
    for skill in frontier:
        lines.append(f"- {skill}")
    lines.append("")

    # --- Current demonstrated ---
    lines.append("## Current Demonstrated Skills")
    lines.append("")
    for skill in demonstrated:
        lines.append(f"- {skill}")
    lines.append("")

    # --- All prompts from this period ---
    lines.append("## All Prompts This Period (chronological)")
    lines.append("")
    lines.append(f"Total: {clean_count} prompts. Claude: read these and assess:")
    lines.append("")
    lines.append("1. **Progress on frontier skills** — any evidence of growth?")
    lines.append("2. **Regression on demonstrated skills** — did the learner revert")
    lines.append("   to old patterns (delegation without spec, trial-and-error debugging)?")
    lines.append("3. **New skills emerging** — anything not in the graph yet?")
    lines.append("4. **AI interaction quality** — better specification? More verification?")
    lines.append("   Or more delegation?")
    lines.append("5. **Patterns to address** — recurring mistakes, blind spots, avoidances?")
    lines.append("")

    for p in clean_prompts:
        lines.append(f"- {format_prompt(p)}")

    lines.append("")

    # --- Current state for reference ---
    lines.append("## Current State (for reference)")
    lines.append("")
    lines.append("```")
    lines.append(state_text)
    lines.append("```")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Weekly review preprocessor for farmer-mode")
    parser.add_argument("--days", type=int, default=7, help="Number of days to review")
    parser.add_argument(
        "--history",
        default=str(Path.home() / ".claude" / "history.jsonl"),
    )
    parser.add_argument(
        "--state",
        default=str(Path.home() / ".claude" / "farmer-state" / "state.md"),
    )
    parser.add_argument(
        "--output",
        default=str(Path.home() / ".claude" / "farmer-state" / "review.md"),
    )
    args = parser.parse_args()

    now = datetime.now()
    since = now - timedelta(days=args.days)
    since_ts = int(since.timestamp() * 1000)

    # Load state
    log(f"Loading state from {args.state}")
    state_text = load_state(args.state)
    demonstrated = parse_demonstrated(state_text)
    frontier = parse_frontier(state_text)
    reviews_due = parse_reviews_due(state_text, now)
    log(f"State: {len(demonstrated)} demonstrated, {len(frontier)} frontier, {len(reviews_due)} reviews scheduled")

    due_count = sum(1 for r in reviews_due if r["is_due"])
    if due_count:
        log(f"  ⚠ {due_count} reviews are due/overdue")
        for r in reviews_due:
            if r["is_due"]:
                log(f"    - {r['skill']} (due {r['review_date']}, {r['days_overdue']}d overdue)")

    # Load recent prompts
    log(f"Loading prompts from last {args.days} days (since {since.strftime('%Y-%m-%d')})")
    raw_prompts = load_history(args.history, since_ts)
    raw_count = len(raw_prompts)
    log(f"Found {raw_count} raw prompts")

    # Denoise
    clean_prompts = denoise(raw_prompts)
    clean_count = len(clean_prompts)
    log(f"After denoising: {clean_count} prompts")

    # Projects
    project_counts = Counter()
    for p in clean_prompts:
        name = p.get("project", "unknown").split("/")[-1]
        project_counts[name] += 1
    projects = project_counts.most_common()
    log(f"Active projects: {len(projects)}")

    # Build review
    output = build_review(
        days=args.days,
        raw_count=raw_count,
        clean_count=clean_count,
        clean_prompts=clean_prompts,
        state_text=state_text,
        demonstrated=demonstrated,
        frontier=frontier,
        reviews_due=reviews_due,
        projects=projects,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(output)

    line_count = output.count("\n") + 1
    log(f"Review written to {output_path}")
    log(f"Output: {line_count} lines, {len(output) // 1024} KB")

    print(json.dumps({
        "status": "ok",
        "output": str(output_path),
        "days": args.days,
        "raw_prompts": raw_count,
        "clean_prompts": clean_count,
        "projects": len(projects),
        "reviews_due": due_count,
        "demonstrated": len(demonstrated),
        "frontier": len(frontier),
        "output_lines": line_count,
    }))


if __name__ == "__main__":
    main()
