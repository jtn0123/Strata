# Coordinator checks on Opus B

Independent Opus B completed with verified claude-opus-5-5 usage. Tools were disabled; the provided source dossier included the correct Metal kernel omitted from A's dossier. The Claude CLI also reported an auxiliary Haiku call. Its raw reply remains advisory.

Accepted refinements:

- QSA initial guard must include by_order=false and contiguous positions, not merely small padded pool count. Preserve original mask/attention dispatch, indexer cache writes and topology keys across limit crossing. `get_n_kpool()` uses actual current padded pool count; reserved1088-pool graphs do not establish runtime eligibility of short contexts.
- Exact useful prompt tile maximum is656 for T512/top10/E512. A static upper-bound launch with GPU prefix metadata could avoid indirect dispatch in a first prototype. It still requires new scheduling/dependency proof and complete cost measurement.
- Winner-only helper selection needs max multiplicity/nonfinite detection, benchmark greedy result_q=null qualification, no full-logit retrieval, tie fallback and complete head+consumer timing. Existing head bandwidth gives a ceiling but no measured winner-path gain.
- Route-map reuse needs graph-owned scratch lifetime; current destination-local extras cannot simply be borrowed until down projection.
- Two graph arenas do not imply two allocated scheduler plans. Measure build/reset/allocation exposure and duplicated scratch cost; target tail widths belong in the census.
- Keep stateless checkpoint serialization and changed prompt split points separate. Keep prompt/app improvements separate from decodeTPS.

Statements not adopted as proven facts:

- QSA source's unordered top-k comment is not proof of the helper sampler's GPU/CPU tie-order contract. Inspect the actual helper chain and fixtures; no tie behavior is assumed.
- An estimated weight byte count divided by memory bandwidth is not a reliable upper bound on removable wall time without actual dispatch, cache residency, execution and overlap attribution. No stopping rule or TPS claim uses that quotient alone.
- The suggested~100microsecond rebuild and~1millisecond detokenize cost are not measurements on this current path.
- Exact prompt split changes are not universally barred or expected to diverge merely because D02 diverged for another shape axis. They remain unqualified and must stop on any exactness failure under the unchanged speed-only contract. No quality-change permission is being requested.
- A failed helper width-invariance screen parks that implementation with a recorded revisit condition, not all materially repaired future mechanisms permanently.
- Identical per-cycle drafts/target row sequences are necessary evidence, not complete state/cache exactness proof by themselves.

The coordinator retains R02/R01 as the first bounded generation screens, R04/R03 as a separate prompt branch, and critical-path R08 profiling as a prerequisite rather than a speculative implementation. No majority-vote adoption and no new measured gain.
