# Safe RAM recovery and native preparation

Available RAM at the final snapshot: **34.145 GiB of 48 GiB**, normal pressure, existing 0.493 GiB swap unchanged. No native/MLX model was loaded in this pass. T3/Codex remain running. No service was disabled and no model/build file was modified or deleted.

| Action | Observed outcome |
|---|---|
| Inspect then release owned idle Flash/Q3 model cache | 0.242 GiB visible residency initially; tiny host gain. Model identities unchanged. |
| Gracefully stop idle same-user Apple media analysis after exact PID/creation-time/executable checks | Full cache/media step available delta +0.241 GiB; 60-second settle 34.048–34.156 GiB. |
| Gracefully stop idle same-user signed Apple text analysis after exact identity checks | Available delta +0.083 GiB; 60-second settle 34.109–34.320 GiB. Original process stayed absent in the settle. |
| Inspect native artifact cache after fresh verification | Only 23.11 MiB unique files; symlink aliases overlap. No further release justified. |
| Inspect owned supervisor memory after full provenance checks | RSS 37.66 MiB. GC collects zero; allocator reports zero bytes released. No hook added. |

The maximum settled host reading was 34.320 GiB. These deltas include background variation; do not add process RSS or cleanup deltas as uniquely recovered physical RAM. Both quiet global intervals met 34 GiB, but the actual supervisor's two load preflights subsequently refused. Post-refusal readings were 33.976/33.824 GiB. Both rejected attempts are preserved before any child, GPU/model response or speed sample. No further automatic attempt is queued. Future admission must pass in the real supervisor, with more margin for background fluctuations; keep the 34 GiB hard rule, normal pressure, 1 GiB native floor and zero-new-swap guard unchanged.

[Cache/media receipt](cleanup-20261010T175322440830Z/receipt.json), [text-analysis receipt](text-analysis-20261010T175937378775Z/receipt.json), [initial residency](inspection-20261010T175207853096Z/receipt.json), [native artifact inspection](native-artifact-cache-inspection.json), [owned setup diagnostic](setup-memory-diagnostic.json), [final snapshot](final-resources.json), [first native refusal](../../20261010-native-mlx-greedy-v1/REPORT.md), [fresh refusal](../../20261010-native-mlx-greedy-v2/REPORT.md).
