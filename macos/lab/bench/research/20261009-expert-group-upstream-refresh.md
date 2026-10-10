# Expert grouping upstream refresh

Read October9,2026: [llama.cpp PR30047](https://github.com/ggml-org/llama.cpp/pull/30047) remains open. Its current description selects matvec below2tokens perexpert (0.5 at K<=512); our R4/R5,10of512expert verify batches yield0.078125/0.09765625. Thus its automatic MMA path does not select our target shapes. This is an inference from the documented gate, not a measured speed result. The local pair experiment is separate and preserves Q2_0 math.
