# Q2 Metal candidate

`q2-masked-metal.patch` is an unchanged copy of Tim / Meld Labs' first patch from [meld-turbo](https://github.com/MeldlabsAI/meld-turbo/blob/ef2101f5f2517204e1d755522d0b84346c4c9f0a/patches/0001-metal-Q2_0-matvec-via-masked-pre-scaled-y-one-FMA-pe.patch), repository revision `ef2101f5f2517204e1d755522d0b84346c4c9f0a`, patch commit `c31f8234172cf1fe27f24370df8ab2cf0ec4ad47`. The original author and commit metadata remain in the patch; its MIT notice is in [MELD-LICENSE.txt](MELD-LICENSE.txt).

The patch replaces bit-by-bit conditional addition with pre-scaled inputs and masked multiplications for Q2_0 matrix-vector operations. It keeps the stored weights unchanged. Floating-point accumulation order changes, so output tokens can differ despite numerical checks passing.

Only this one Metal file is changed. None of the other Meld patches, model conversions, vocabulary filters or GPU memory-limit overrides are included. Source and patch hashes are pinned in [q2_experiment.json](../config/q2_experiment.json). Their reported M2 Max performance gains are external measurements; no M5 Pro performance improvement has been measured here.
