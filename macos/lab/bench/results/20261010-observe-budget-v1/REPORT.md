# Load-free native allocation audit

This audit reads model-header inventory and an existing full P07 startup log. It loads no model and runs no GPU test. It preserves every logged reservation instead of deduplicating rows with the same role/backend/purpose.

- Unique target tensor payload: **37,612,715,520 bytes / 35.030 GiB**. This is stored tensor payload, not measured resident RAM.
- Lazy lookup file: **28,800,138,240 bytes**. File length does not establish residency or hardware SSD throughput.
- Packed helper file: **1,251,560,832 bytes**; borrowed target weights are not an additional unique full target copy.
- Historical P07 log: **19 reservations**, including separate attention/indexer KV and repeated scratch reservations. Mapped/shared/repacked overlap is unknown; their sum is not unique physical memory or a peak.
- Helper-off 512-context F32 attention/indexer KV: **30 MiB estimated**, 15 MiB more than F16 at the same context. Actual recurrent snapshot allocation, transient scratch, first-touch startup peak and unique mapped residency remain unmeasured.

The historical startup uses 4K F16 context, batch 512, packed mixed Q3 helper and draft maximum three. That log is evidence of the historical allocation profile, not a new allocation measurement on the observer engine. No admission threshold, ordinary launcher or performance claim changes.

[Raw audit, allocation identities and source hashes](REPORT.json). [Monitoring status and next steps](../../M5-MONITORING.md).
