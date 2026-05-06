# Farmer Mode

<p align="center">
  <img src="images/hero.png" alt="Farmer Mode — A coaching skill for Claude Code" width="700">
</p>

A Claude Code skill that teaches engineering thinking and AI literacy through constraint-driven practice — inspired by [The Farmer Was Replaced](https://store.steampowered.com/app/2060160/The_Farmer_Was_Replaced/).

Instead of answering your questions, it gates knowledge behind productive struggle, demands invariants, injects adversarial challenges, and tracks your skill mastery over time. Domain-agnostic — works on whatever you're building.

---

## Why This Exists

Most people use AI to skip the hard parts of engineering. This skill makes the hard parts unavoidable.

The Farmer Was Replaced teaches programming by giving you a crippled language and a tiny API, then unlocking new primitives only after you prove mastery with what you have. Farmer Mode applies the same pedagogy to your real work with Claude Code:

- **Withholds answers** — diagnostic questions before solutions
- **Constrains solutions** — forces approaches the easy/LLM path can't satisfy
- **Demands invariants** — no confirmation until you articulate *why* it works
- **Injects bugs** — gives your working code back with a subtle flaw to find
- **Gates progression** — tracks demonstrated skills, won't advance until foundations are solid
- **Reviews your real work** — weekly analysis of your actual prompts to Claude, not practice exercises

<p align="center">
  <img src="images/skill-graph.png" alt="Skill Graph" width="500">
</p>

## The Skill Graph

Five tiers of domain-agnostic engineering skills, gated by prerequisites:

| Tier | Skills | Requires |
|------|--------|----------|
| **1 — Foundations** | Decomposition, State reasoning, Conditional logic, Iteration | — |
| **2 — Structure** | Abstraction, Data modeling, Interface design, Error handling | Tier 1 |
| **3 — Rigor** | Invariant reasoning, Testing strategy, Optimization under constraint, Debugging by observation | Tier 2 |
| **4 — Systems** | Composition, Concurrency reasoning, Failure mode analysis, Feedback loops | Tier 3 |
| **5 — AI Collaboration** | Specification before generation, Output verification, Constraint-directed prompting, Adversarial review | Tier 3 |

Skills are **demonstrated** when you solve a problem targeting that skill, articulate the invariant, and survive a counter-question. Skills are **mastered** after passing spaced reviews at increasing intervals.

## Installation

Copy the skill into your Claude Code skills directory:

```bash
# Clone the repo
git clone https://github.com/vincenthopf/farmer-mode.git

# Copy to Claude Code skills
cp -r farmer-mode/SKILL.md ~/.claude/skills/farmer-mode/SKILL.md
cp -r farmer-mode/scripts ~/.claude/skills/farmer-mode/scripts

# Create state directory
mkdir -p ~/.claude/farmer-state
cp farmer-mode/state-template/state.md ~/.claude/farmer-state/state.md
```

Or as a one-liner:

```bash
git clone https://github.com/vincenthopf/farmer-mode.git /tmp/farmer-mode && \
  mkdir -p ~/.claude/skills/farmer-mode/scripts ~/.claude/farmer-state && \
  cp /tmp/farmer-mode/SKILL.md ~/.claude/skills/farmer-mode/ && \
  cp /tmp/farmer-mode/scripts/*.py ~/.claude/skills/farmer-mode/scripts/ && \
  cp /tmp/farmer-mode/state-template/state.md ~/.claude/farmer-state/
```

## Usage

### First Session — Calibration

```
/farmer-mode
```

On first run, the skill:
1. Runs `calibrate.py` — reads your entire Claude Code prompt history, denoises it, formats it
2. Claude reads your actual prompts and assesses your engineering thinking patterns
3. Asks which skills in `~/.claude/skills/` you built yourself (vs received)
4. Asks targeted gap-filling questions about uncertain skills
5. Seeds your skill state and proposes your first challenge

<p align="center">
  <img src="images/calibration.png" alt="Calibration" width="500">
</p>

### Daily Coaching

Every interaction while farmer-mode is active follows these protocols:

| Protocol | What It Does |
|----------|-------------|
| **Never Answer First** | Asks diagnostic questions before giving any answer |
| **Constrain Solutions** | Imposes at least one constraint that blocks the naive approach |
| **Demand Invariants** | Requires you to state the invariant, break condition, and test |
| **Socratic Ladder** | 4-rung progressive hints: reframe → narrow → nudge → teach |
| **Bug Injection** | Every ~3rd success, returns your code with a subtle bug to find |
| **AI-Literacy** | Pushes back on "write this for me" with "define correct first" |
| **Exam Mode** | No-help problems graded on a 100-point rubric |

<p align="center">
  <img src="images/coaching.png" alt="Coaching Loop" width="500">
</p>

### Weekly Review

```
/farmer-mode review
```

Reviews your actual work from the past week:
1. Runs `review.py` — loads recent prompts, compares against skill state
2. Claude reads all your real prompts and assesses progress and regression
3. Checks spaced reviews — tests due skills, promotes or demotes
4. Asks self-assessment questions
5. Updates state, generates a progress report with an honest assessment
6. Assigns a behavior challenge for the coming week

<p align="center">
  <img src="images/review.png" alt="Weekly Review" width="500">
</p>

Schedule it automatically:
```
/schedule — create weekly farmer-mode review
  cron: "0 9 * * 1"
  prompt: "Run /farmer-mode review. Analyze the last 7 days."
```

### Escape Hatch

Say **"just answer"** or **"no farmer"** in any message to bypass coaching for that turn.

## The Seven Protocols

<p align="center">
  <img src="images/protocols.png" alt="The Seven Protocols" width="500">
</p>

### 1. Never Answer First
When you ask "how do I X", Claude asks what you've tried and what your mental model is. The struggle is the learning.

### 2. Constrain Solutions
Every problem comes with at least one constraint that makes the obvious approach fail — banned primitives, resource budgets, forced decomposition, or solution inversion.

### 3. Demand Invariants
No solution is confirmed until you state: the invariant (what must always be true), the break condition (what input would break it), and the test (what catches regression).

### 4. Progressive Hints (Socratic Ladder)
When stuck, hints climb a ladder: reframe the problem → narrow to the specific area → smallest possible nudge → teach (but only after three genuine attempts, and immediately followed by a variant problem).

### 5. Adversarial Bug Injection
Every ~3rd success, your working solution comes back with a subtle bug. Find it, then write the test that would have caught it.

### 6. AI-Literacy Challenges
When you ask Claude to generate code, it pushes back: "What are the constraints? What invariants must hold? How will you verify my output?" Periodically, Claude generates deliberately flawed output for you to grade.

### 7. Exam Mode
No hints, no questions answered. State the problem, impose constraints, require deliverables. Grade on a 100-point rubric: correctness (30), constraints (20), invariants (20), edge cases (15), code quality (15).

## Methodology Sources

- **The Farmer Was Replaced** — gate primitives, force optimization under scarcity
- **Bjork** — desirable difficulties: slow initial acquisition → durable retention
- **Ericsson** — deliberate practice at the edge of ability
- **Kapur** — productive failure: struggle before instruction
- **Polya** — understand → plan → execute → look back
- **Bloom** — mastery learning: don't advance until the current skill is solid

## File Structure

```
farmer-mode/
├── SKILL.md                    # Main skill definition (Claude reads this)
├── scripts/
│   ├── calibrate.py            # Prompt history preprocessor (first session)
│   └── review.py               # Weekly review preprocessor
├── state-template/
│   └── state.md                # Initial state template
├── images/                     # Visual assets
└── README.md
```

## State Files (not in repo)

These are generated per-user and live in `~/.claude/farmer-state/`:

| File | Purpose |
|------|---------|
| `state.md` | Your skill graph, demonstrated/frontier skills, session log |
| `calibration.md` | Full preprocessed prompt history (first session) |
| `review.md` | Weekly review data (regenerated each review) |

## License

MIT

## Credits

Built by [Vince Hopf](https://github.com/vincenthopf). Inspired by [The Farmer Was Replaced](https://thefarmerwasreplaced.com/) by Daniel Springwald.

Research artifact: see the full [learning blueprint](https://github.com/vincenthopf/farmer-mode/wiki) for the pedagogy behind this skill.
