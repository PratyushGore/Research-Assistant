# Person B — Documented Assumptions

Per the role brief's General Rules ("Document any assumption you make
about ambiguous requirements... don't silently decide and move on"), here
are the decisions made while implementing the Summarization and
Verification agents, for your final report section.

## 1. "Retrieve relevant chunks per paper" — no direct topic-query API exposed yet

The locked schema gives the Summarization Agent an `IngestionResult` per
paper (already containing all of that paper's chunks), but there's no
exposed function to query ChromaDB by topic relevance directly from this
module. Until Person A exposes one, `_select_relevant_chunks()` ranks the
paper's own chunks by keyword overlap with the research topic and takes
the top 6. This is a placeholder for a real embedding-similarity query —
swap it out if/when a `query_chunks(topic, paper_id)` function becomes
available.

## 2. Cross-paper synthesis has no home in the locked schema

The role brief asks for "synthesize a cross-paper findings summary
(map-reduce style)," but `FindingsPacket` only has `topic`, `summaries`,
`claims` — no field for a synthesized narrative. The synthesis step still
runs (see `_cross_paper_synthesis()`) and is logged, but it is **not**
persisted anywhere the Composer Agent can read it. If the team wants this
in the final documents, `FindingsPacket` needs a new optional field (e.g.
`cross_paper_synthesis: Optional[str]`) — that requires updating the
shared schema file and notifying everyone, per the General Rules, so it
hasn't been added unilaterally here.

## 3. Contradiction flags reuse `verification_status` + `explanation`

`VerificationResult` has no field for "which other claim does this
contradict." Detected contradictions are recorded by setting
`verification_status="contradicted"` on **both** conflicting claims'
results and naming the other claim's `claim_id` inside `explanation`. This
keeps the contract unchanged but means anything reading
`verification_status` should treat `"contradicted"` as a fourth possible
value alongside `"verified"` / `"unsupported"` / `"unverified"`.

## 4. Citation Agent ownership conflict

The role brief assigns the Citation Agent to Person B; the finalized
blueprint's team-split table assigns it to Person C. It's already
implemented (deterministic, working) in `graph.py`. Left untouched here —
flagging for the team to confirm ownership rather than having two people
edit it.

## 5. `verification_status` open question from the README

The README asks whether `verification_status` should become an `Enum`.
Left as an open string here (matching the locked schema as given) so nothing
breaks if the team resolves this differently — the values currently in use
across this implementation are: `"pending"`, `"verified"`, `"unsupported"`,
`"unverified"`, `"contradicted"`.
