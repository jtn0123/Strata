# Independent reviews

Sol6.1 reviewed QSA scope, padding/permutation/pairing, exceptional masks, graph placement, manifest/build provenance and the actual engine delta. Runtime caught the Metal-versus-MTL guard mistake after that static review; it was excluded and corrected. Source review did not substitute for actual activation evidence.

Sol6.1 then reviewed route-map allocation bounds, unchanged current amax, post-barrier lifetime tracking, getter ABI and actual backend/device names. Astra implemented the native probe in an isolated file; Sol independently required exact encoding counts, T513 and terminal-only mixed-precision checks. Final native hash70388e942d74772836acc67ac2b27986e6ef2dca4dd6cefb68c86a22f8079b95. Both reviewed the full-block runner; coordinator added strict integer metadata and raw-log/JSONL parity gates before timing.

Astra independently rechecked the completed route-map receipts:198 records per engine,138 eligible records with full counts, exact output digests, all Metal/one split and zero new swap. It confirmed the below-gate result and recommended R03 as a different bounded scheduling experiment.

Astra traced the actual pinned /detokenize endpoint and verified that it bypasses whole-string whitespace cleanup. The optional piece cache remains sound for the tested owned endpoint; actual small model is Qwen3.5-4B. Raw model receipts and source archives are authoritative. No new token-decoder change or timing rerun was needed.

Forced overlap/encoder-partition fixtures and general backend certification remain outside this bounded evidence. No reviews were posted externally.
