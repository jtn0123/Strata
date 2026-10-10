# Independent reviews

Astra reviewed the design before the native change. It identified that raw-winner-only output can change draft tokens because the CPU chain suppresses model tokens before choosing its winner. The implemented design therefore preserves the complete ordered top10. Astra confirmed the local-distinct-value selection/count proof and required selected-tie, exceptional-value and repeated-invocation fallback tests.

Sol6.1 reviewed the actual native and host source. It found no remaining concrete blocker after the two-row fixture correction. It checked the selection proof, sticky exceptional detection,243 blocks/2430 parts,2,025,456-byte allocation, flag at2,025,440, nonoverlapping scratch, threadgroup/buffer barriers, uniform early exits and unchanged legacy sort/merge arithmetic. The32-lane SIMD assumption remains restricted to this M5 Pro.

Astra separately reviewed the model protocol. Original-engine mapping,256-token responses, excluded warmup plus three measured repeats, English code/prose, per-pass exact fresh/cache outputs, zero-new-swap guards and the stricter final drift predicate were sound. It identified inherited report text that could conflict with the stricter verdict and an incomplete source archive. The final report must be regenerated from preserved results; supplemental dependency hashes are explicitly recorded during the first control rather than claimed as prelaunch captures.

The once-per-process marker proves entry into the eligible variant. It does not establish that every model invocation took the fast branch. The failed cold load is excluded. Accepted retry runs are checked for zero new swap allocation; existing swap remains separate.

These were read-only reviews. Reviewers performed no edits, builds or GPU/model runs. Their conclusions are limited to inspected source and the recorded qualification evidence.
