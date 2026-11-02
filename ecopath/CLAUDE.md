# Project context

A research tool over GBIF occurrence data and eBird observation data. Users are
researchers, not casual users. Current surface: a species search page, a
population heat map tab, a migration map tab, a chart tab, and an LLM chat agent
that picks tools (e.g. renders a chart to support an answer).

The project is being refactored toward a single Raycast-style command bar that
resolves intent locally and only falls back to the LLM for open-ended questions.

# Domain constraints — do not violate these

1. **"Not migratory" and "insufficient data" are different answers.** GBIF and
   eBird coverage is extremely uneven. A tropical resident with 40 records and a
   poorly-sampled migrant both look non-migratory to a naive algorithm. Any
   migratory classification must carry record count and spatial/temporal coverage
   alongside it, and the UI must be able to say "we don't know" as a distinct
   third state. Never collapse these into a boolean.

2. **Raw occurrence density is not abundance.** It is largely a map of where
   birdwatchers live. Nothing in this codebase may be labelled "population"
   unless it is effort-corrected. Uncorrected maps are labelled "observation
   density".

3. **Species identity is exact, never fuzzy at the data layer.** Bar-tailed
   Godwit and Black-tailed Godwit are different birds. Fuzzy matching is allowed
   only for resolving user *input* to a taxon ID, and the resolved name must be
   shown back to the user. Data lookups downstream use the ID.

4. **Do not build a semantic/embedding similarity cache for queries.** This has
   been considered and rejected: cosine similarity is near-blind to entity and
   number swaps ("Bar-tailed" vs "Black-tailed", "June" vs "July" score ~0.97),
   which is precisely the axis our queries vary on. Caching must key on
   normalized extracted parameters, never on embedding distance.

# Working agreement

- Work in stages. Do not start a later stage until I confirm the current one.
- Before writing code for a stage, state your plan and what files you'll touch.
- Do not refactor code unrelated to the current stage.
- Small, reviewable commits with clear messages.
- Where a threshold, cutoff, or magic number is needed, **stop and ask me**.
  Do not pick one and move on. Domain thresholds are my call.
- If you find something that contradicts what I've told you about the codebase,
  say so instead of working around it.
```