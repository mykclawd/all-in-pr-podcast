---
name: all-in-pr-podcast
description: Generate a 2-3 minute All-In-podcast-style audio episode that walks the listener through a GitHub pull request. Jason moderates, Friedberg explains exactly how the code works, Chamath flags what matters most, and Sacks plays devil's advocate on the trade-offs. Use when the user asks for a PR podcast, an All-In episode about a PR, "podcast my PR", or an audio walkthrough of a pull request. Input is a PR URL or number. Do not use for written PR summaries or code review.
---

# All-In PR Podcast

Turn one pull request into a 2-3 minute, four-host audio episode. After one
listen, the user must be able to answer:

1. What does the PR do?
2. Why was it made?
3. Exactly how does it work? (files, functions, data flow, edge cases)
4. What trade-offs did it make, and what were the alternatives?

Skill directory (referred to as `$SKILL` below): the folder containing this file,
normally `~/.claude/skills/all-in-pr-podcast`.

## Voice policy

Use stock or library voices cast to each host's *role and energy*. Never clone,
design, or pick voices intended to reproduce the real hosts' voices, even if the
user asks; say so in one line and continue with stock voices. Names and
on-air personas are fine; this is a fan parody-style explainer, not affiliated with the show.

## Workflow

### 1. Fetch the PR

Input must be a PR URL or number. If the user gave neither, ask for one.

```bash
OUT=$("$SKILL/scripts/fetch_pr.sh" <pr-url-or-number>)   # prints the episode dir
```

This writes `pr.json` (metadata, files, commits, reviews), `diff.patch`, and
`diffstat.txt` to `~/pr-podcasts/<repo>-<number>/`. A bare number only works
inside the PR's repo checkout.

### 2. Understand the change (do not skip)

- Read `pr.json` (title, body, linked tickets, review comments) and
  `diffstat.txt`, then read `diff.patch`.
- Large diffs (>2,000 lines): skip lockfiles, generated code, snapshots, and
  mechanical renames; focus on the 3-6 files that carry the logic. Read
  surrounding code with `gh api` or the local checkout when a hunk alone is
  ambiguous.
- Write `notes.md` in `$OUT` with:
  - **What**: one sentence.
  - **Why**: the motivating problem, from the PR body, ticket, or code. If the
    reason is not stated anywhere, write "inferred:" and say so on air.
  - **How**: the mechanism as an ordered data/control flow, naming real
    files, functions, types, flags, and numbers. 4-8 steps.
  - **Trade-offs**: 2-3 real ones, each with the alternative that was not
    chosen and what it would have cost. Include at least one the PR author
    might argue with.
  - **Claims ledger**: every technical claim the script will make, each mapped
    to `path:line` or a hunk. A claim without a source does not go in the
    script.

### 3. Write the script

Read `references/personas.md` for each host's role and speech patterns, and
`references/example-episode.md` for the target shape and density.

Hard constraints:

- **Aim for 300-470 spoken words** (about 2:00-3:10 at the current cast's ~150 wpm; pace depends on the voices). Going a little over is fine when the PR needs it; the renderer only refuses scripts above 600 words.
- Speaker lines only, one turn per line: `JASON: ...`, `FRIEDBERG: ...`,
  `CHAMATH: ...`, `SACKS: ...`. Anything else in the file is ignored by the
  renderer, so a title line or notes are fine.
- Beat sheet (approximate word budget):
  1. Cold open (Jason, ~30): what the PR does + a hook. Quick banter.
  2. Why (~45): Jason asks; Chamath or Friedberg answers with the real motive.
  3. ELI5 (~40): before the deep dive, Jason asks Friedberg to explain it
     "like I'm five". Friedberg gives one everyday analogy (a restaurant, a
     mailroom, a bouncer with a guest list, a toll booth) that maps onto the
     real mechanism, not just the vibe. Another host may riff on it in one line.
  4. How (~150): Friedberg walks the mechanism step by step, in order, using
     real identifiers spoken naturally ("the `retryWithBackoff` helper in
     `http-client`"). He ties at least one step back to the analogy ("that's
     the guest list"). Jason asks one clarifying question a listener would
     ask. Chamath interrupts once: "This is the part that matters..."
  5. Trade-offs (~110): Sacks pushes back on the most debatable choice and
     names the alternative. He may bend the analogy to make his point ("your
     bouncer goes home at midnight"). Friedberg or Chamath defends with
     specifics. Sacks lands one more risk. Disagreement stays unresolved if it
     is genuinely unresolved.
  6. Close (~35): sounds like the end of a real segment, not a checklist.
     Never recite "What: ... Why: ... How: ...". Pick one or two: Jason gives
     his one-line take, the hosts make a quick bet or prediction ("I give it
     two weeks before someone flips that flag"), call back to the analogy, or
     Sacks gets a last jab. Then the sign-off. The ELI5 and the trade-off
     beats already covered the takeaways; the close only needs to leave the
     one thing the listener should remember.
- Make it sound spoken: contractions, short sentences, interruptions (end a
  line with "—" and start the next with `[interrupting]`), crosstalk
  reactions ("Right.", "Hold on."), one or two laughs. No bullet-point prose.
- Code read aloud: say identifiers as words ("use user profile hook"), never
  read raw syntax, paths longer than two segments, hashes, or line numbers.
  Numbers that matter (timeouts, limits, percentages) must be said exactly.
- Audio tags (ElevenLabs v3) go at the start of a line or clause, at most one
  per line: `[excited]`, `[laughs]`, `[sarcastic]`, `[skeptical]`,
  `[interrupting]`, `[sighs]`, `[thoughtful]`, `[serious]`.
- Accuracy beats bits. Friedberg never says anything that is not in the
  claims ledger. Jokes and analogies cannot misstate behavior: if the
  analogy breaks down somewhere important, have a host say where.

Save as `$OUT/script.md`.

### 4. Validate before spending credits

```bash
uv run "$SKILL/scripts/render.py" "$OUT/script.md" --dry-run
```

Fix and re-run until it passes: all four hosts speak,
Friedberg has the most words, Sacks has 2+ turns. A length WARN is advisory. Then self-check the script
against the four outcomes at the top of this file and the claims ledger.

### 5. Render audio

```bash
uv run "$SKILL/scripts/render.py" "$OUT/script.md" -o "$OUT/episode.mp3"
```

- Engine `auto` uses ElevenLabs (`eleven_v3` text-to-dialogue, chunked at
  ~1,800 characters, stitched with ffmpeg) when a key is available, otherwise
  macOS `say` as a robotic fallback. Force one with `--engine elevenlabs|say`.
- Key lookup order: `ELEVENLABS_API_KEY` env var, then macOS Keychain item
  `elevenlabs-api-key`. Never ask the user to paste the key into chat. If it is
  missing, tell them to run:
  `security add-generic-password -a "$USER" -s elevenlabs-api-key -w`
  (prompts for the key without echoing it).
- Voices and model live in `$SKILL/voices.json`. `--list-voices` prints the
  voices on the account so the user can recast.
- Cost: about 1 credit per character, so a typical episode costs
  2,000-3,000 credits.

### 6. Deliver

- `open "$OUT/episode.mp3"`.
- Reply with: the episode path, duration, credits used, and the four
  takeaways in one line each. Do not paste the whole script unless asked; give
  the `script.md` path.
- Offer one round of tweaks (for example "more Sacks", "slower Friedberg",
  "go deeper on the cache layer"). For tweaks, edit `script.md` and re-render;
  do not refetch.

## Failure handling

- `gh` auth or 404: report the exact error; for GitHub Enterprise PRs suggest
  `gh auth login --hostname <your-enterprise-host>`.
- ElevenLabs 401: key invalid; 402/quota: out of credits. Offer `--engine say`.
- ElevenLabs 422 on a chunk: lower `--chunk-chars` to 1200 and retry.
- `ffmpeg` missing: `brew install ffmpeg` (macOS) or your package manager.
