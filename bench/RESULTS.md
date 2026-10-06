# Strata Mac experiment results

Measured on this 48 GiB M5 Pro. Raw JSON, CSV, native logs, exact prompt IDs and 250 ms memory samples are saved beside each run. Earlier results stay unchanged.

| Run | Workload / prompt tokens | Output tok/s (median) | First token (median, s) | Input tok/s (median) | Peak RSS (GiB) | Peak swap (GiB) | Swap growth (GiB) | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [small-baseline](results/20261006T105737Z-small-baseline/result.json) | synthetic / 512 | 77.56 | 0.325 | 1576.7 | 3.01 | 0.00 | 0.00 | passed |
| [small-baseline](results/20261006T105737Z-small-baseline/result.json) | synthetic / 2048 | 76.13 | 1.256 | 1631.4 | 3.01 | 0.00 | 0.00 | passed |
| [small-ubatch512](results/20261006T105818Z-small-ubatch512/result.json) | synthetic / 512 | 77.41 | 0.248 | 2069.9 | 3.05 | 0.00 | 0.00 | passed |
| [small-ubatch512](results/20261006T105818Z-small-ubatch512/result.json) | synthetic / 2048 | 75.76 | 0.943 | 2173.9 | 3.05 | 0.00 | 0.00 | passed |
| [small-baseline-confirm](results/20261006T105843Z-small-baseline-confirm/result.json) | synthetic / 512 | 77.51 | 0.325 | 1579.3 | 3.01 | 0.00 | 0.00 | passed |
| [small-baseline-confirm](results/20261006T105843Z-small-baseline-confirm/result.json) | synthetic / 2048 | 75.95 | 1.256 | 1631.6 | 3.01 | 0.00 | 0.00 | passed |
| [flash-baseline](results/20261006T111445Z-flash-baseline/result.json) | synthetic / 512 | 38.74 | 1.230 | 416.3 | 34.39 | 0.02 | 0.01 | passed |
| [flash-baseline](results/20261006T111445Z-flash-baseline/result.json) | synthetic / 2048 | 37.55 | 4.943 | 414.4 | 34.39 | 0.02 | 0.01 | passed |
| [flash-ubatch512](results/20261006T111541Z-flash-ubatch512/result.json) | synthetic / 512 | 38.72 | 0.750 | 683.5 | 35.68 | 0.02 | 0.00 | passed |
| [flash-ubatch512](results/20261006T111541Z-flash-ubatch512/result.json) | synthetic / 2048 | 37.44 | 3.111 | 658.4 | 35.68 | 0.02 | 0.00 | passed |
| [flash-mtp3-ubatch512](results/20261006T111640Z-flash-mtp3-ubatch512/result.json) | - | - | - | - | 37.35 | 0.14 | 0.12 | failed: RuntimeError: Streaming response has no first token or final timing record |
| [flash-mtp3-cpu-ubatch512](results/20261006T111806Z-flash-mtp3-cpu-ubatch512/result.json) | synthetic / 512 | 45.05 | 1.016 | 504.3 | 38.31 | 1.99 | 1.85 | passed |
| [flash-mtp3-cpu-ubatch512](results/20261006T111806Z-flash-mtp3-cpu-ubatch512/result.json) | synthetic / 2048 | 42.66 | 4.148 | 493.8 | 38.31 | 1.99 | 1.85 | passed |
| [flash-8k-ubatch512](results/20261006T111954Z-flash-8k-ubatch512/result.json) | synthetic / 1024 | 38.27 | 1.504 | 680.9 | 35.94 | 1.93 | 0.00 | passed |
| [flash-8k-ubatch512](results/20261006T111954Z-flash-8k-ubatch512/result.json) | synthetic / 4096 | 37.19 | 6.616 | 619.2 | 35.94 | 1.93 | 0.00 | passed |
| [prediction-baseline-a](results/20261006T144910Z-prediction-baseline-a/result.json) | synthetic / 512 | 38.97 | 0.749 | 684.4 | 33.37 | 1.03 | 0.00 | passed |
| [prediction-baseline-a](results/20261006T144910Z-prediction-baseline-a/result.json) | synthetic / 2048 | 37.59 | 3.106 | 659.4 | 33.37 | 1.03 | 0.00 | passed |
| [prediction-q2-gpu2](results/20261006T144952Z-prediction-q2-gpu2/result.json) | - | - | - | - | 37.10 | 1.03 | 0.00 | failed: RuntimeError: Streaming response has no first token or final timing record |
| [prediction-q2-output2](results/20261006T145142Z-prediction-q2-output2/result.json) | synthetic / 512 | 39.52 | 1.083 | 473.2 | 37.95 | 1.03 | 0.00 | passed |
| [prediction-q2-output2](results/20261006T145142Z-prediction-q2-output2/result.json) | synthetic / 2048 | 40.00 | 4.162 | 492.1 | 37.95 | 1.03 | 0.00 | passed |
| [prediction-q2_0-gpu2](results/20261006T145347Z-prediction-q2_0-gpu2/result.json) | synthetic / 512 | 13.86 | 0.918 | 558.3 | 37.33 | 1.02 | 0.00 | failed |
| [prediction-q2_0-gpu2](results/20261006T145347Z-prediction-q2_0-gpu2/result.json) | synthetic / 2048 | 14.42 | 4.460 | 459.3 | 37.33 | 1.02 | 0.00 | failed |
| [prediction-q3-output2](results/20261006T145640Z-prediction-q3-output2/result.json) | synthetic / 512 | 43.15 | 1.070 | 478.6 | 37.36 | 1.02 | 0.00 | passed |
| [prediction-q3-output2](results/20261006T145640Z-prediction-q3-output2/result.json) | synthetic / 2048 | 42.53 | 4.297 | 476.8 | 37.36 | 1.02 | 0.00 | passed |
| [prediction-q3-cpu2](results/20261006T145805Z-prediction-q3-cpu2/result.json) | synthetic / 512 | 41.07 | 1.058 | 484.3 | 37.94 | 1.02 | 0.00 | passed |
| [prediction-q3-cpu2](results/20261006T145805Z-prediction-q3-cpu2/result.json) | synthetic / 2048 | 41.42 | 4.392 | 466.4 | 37.94 | 1.02 | 0.00 | passed |
| [prediction-baseline-b-t06](results/20261006T145946Z-prediction-baseline-b-t06/result.json) | synthetic / 512 | 38.99 | 0.749 | 684.3 | 35.87 | 1.02 | 0.00 | passed |
| [prediction-baseline-b-t06](results/20261006T145946Z-prediction-baseline-b-t06/result.json) | synthetic / 2048 | 37.48 | 3.107 | 659.4 | 35.87 | 1.02 | 0.00 | passed |
| [prediction-q3-output2-t06](results/20261006T150044Z-prediction-q3-output2-t06/result.json) | synthetic / 512 | 38.38 | 1.104 | 463.9 | 37.98 | 1.02 | 0.00 | passed |
| [prediction-q3-output2-t06](results/20261006T150044Z-prediction-q3-output2-t06/result.json) | synthetic / 2048 | 37.30 | 4.389 | 466.7 | 37.98 | 1.02 | 0.00 | passed |
| [q2-1-baseline](results/20261006T171840Z-q2-1-baseline/result.json) | - | - | - | - | 26.34 | 2.38 | 2.14 | failed: RuntimeError: Server exited during load with code -15; see server.log |
| [q2-1-baseline](results/20261006T172232Z-q2-1-baseline/result.json) | synthetic / 512 | 36.19 | 0.774 | 662.8 | 29.39 | 2.34 | 0.00 | passed |
| [q2-1-baseline](results/20261006T172232Z-q2-1-baseline/result.json) | synthetic / 2048 | 35.18 | 3.559 | 575.5 | 29.39 | 2.34 | 0.00 | passed |
| [q2-2-q2-masked](results/20261006T172507Z-q2-2-q2-masked/result.json) | synthetic / 512 | 29.20 | 0.957 | 539.0 | 35.15 | 1.94 | 0.25 | passed |
| [q2-2-q2-masked](results/20261006T172507Z-q2-2-q2-masked/result.json) | synthetic / 2048 | 30.92 | 3.863 | 531.5 | 35.15 | 1.94 | 0.25 | passed |
| [q2-3-q2-masked](results/20261006T172754Z-q2-3-q2-masked/result.json) | synthetic / 512 | 34.60 | 0.857 | 598.6 | 35.40 | 1.97 | 0.14 | passed |
| [q2-3-q2-masked](results/20261006T172754Z-q2-3-q2-masked/result.json) | synthetic / 2048 | 35.37 | 3.582 | 571.9 | 35.40 | 1.97 | 0.14 | passed |
| [q2-4-baseline](results/20261006T173022Z-q2-4-baseline/result.json) | synthetic / 512 | 34.03 | 0.845 | 606.3 | 35.34 | 1.90 | 0.00 | passed |
| [q2-4-baseline](results/20261006T173022Z-q2-4-baseline/result.json) | synthetic / 2048 | 35.45 | 3.525 | 581.3 | 35.34 | 1.90 | 0.00 | passed |
| [q2-quiet-confirmation](results/20261006T173319Z-q2-quiet-confirmation/result.json) | synthetic / 512 | 38.01 | 0.803 | 637.9 | 33.65 | 1.72 | 0.00 | passed |
| [q2-quiet-confirmation](results/20261006T173319Z-q2-quiet-confirmation/result.json) | synthetic / 2048 | 36.86 | 3.415 | 599.8 | 33.65 | 1.72 | 0.00 | passed |
| [q2-quiet-baseline](results/20261006T173609Z-q2-quiet-baseline/result.json) | synthetic / 512 | 37.91 | 0.754 | 679.2 | 35.73 | 1.70 | 0.00 | passed |
| [q2-quiet-baseline](results/20261006T173609Z-q2-quiet-baseline/result.json) | synthetic / 2048 | 35.55 | 3.166 | 647.0 | 35.73 | 1.70 | 0.00 | passed |
| [vocab-feature](results/20261006T181113Z-vocab-feature/result.json) | synthetic / 48 | 37.77 | 0.608 | 79.1 | 28.78 | 1.50 | 0.48 | completed-check-failure |
| [vocab-feature](results/20261006T181113Z-vocab-feature/result.json) | synthetic / 53 | 32.79 | 0.381 | 139.4 | 28.78 | 1.50 | 0.48 | completed-check-failure |
| [vocab-feature](results/20261006T181113Z-vocab-feature/result.json) | synthetic / 56 | 31.29 | 0.390 | 143.8 | 28.78 | 1.50 | 0.48 | completed-check-failure |
| [vocab-feature](results/20261006T181113Z-vocab-feature/result.json) | synthetic / 512 | 32.88 | 1.249 | 410.7 | 28.78 | 1.50 | 0.48 | completed-check-failure |
| [vocab-feature](results/20261006T181113Z-vocab-feature/result.json) | synthetic / 2048 | 33.16 | 4.547 | 450.9 | 28.78 | 1.50 | 0.48 | completed-check-failure |
| [vocab-1-plain](results/20261006T181358Z-vocab-1-plain/result.json) | chinese / 56 | 36.45 | 0.294 | 190.7 | 36.21 | 1.46 | 0.00 | passed |
| [vocab-1-plain](results/20261006T181358Z-vocab-1-plain/result.json) | code / 48 | 37.75 | 0.269 | 178.9 | 36.21 | 1.46 | 0.00 | passed |
| [vocab-1-plain](results/20261006T181358Z-vocab-1-plain/result.json) | prose / 53 | 37.26 | 0.277 | 191.9 | 36.21 | 1.46 | 0.00 | passed |
| [vocab-1-plain](results/20261006T181358Z-vocab-1-plain/result.json) | synthetic / 512 | 36.50 | 0.768 | 667.5 | 36.21 | 1.46 | 0.00 | passed |
| [vocab-1-plain](results/20261006T181358Z-vocab-1-plain/result.json) | synthetic / 2048 | 35.97 | 3.157 | 649.0 | 36.21 | 1.46 | 0.00 | passed |
| [vocab-2-full](results/20261006T181631Z-vocab-2-full/result.json) | chinese / 56 | 33.38 | 0.398 | 141.1 | 37.71 | 1.43 | 0.00 | passed |
| [vocab-2-full](results/20261006T181631Z-vocab-2-full/result.json) | code / 48 | 41.22 | 0.481 | 100.0 | 37.71 | 1.43 | 0.00 | passed |
| [vocab-2-full](results/20261006T181631Z-vocab-2-full/result.json) | prose / 53 | 31.94 | 0.426 | 125.8 | 37.71 | 1.43 | 0.00 | passed |
| [vocab-2-full](results/20261006T181631Z-vocab-2-full/result.json) | synthetic / 512 | 34.87 | 1.279 | 402.1 | 37.71 | 1.43 | 0.00 | passed |
| [vocab-2-full](results/20261006T181631Z-vocab-2-full/result.json) | synthetic / 2048 | 34.88 | 5.214 | 393.3 | 37.71 | 1.43 | 0.00 | passed |
| [vocab-3-subset](results/20261006T181924Z-vocab-3-subset/result.json) | chinese / 56 | 31.91 | 0.390 | 143.9 | 37.67 | 1.41 | 0.00 | passed |
| [vocab-3-subset](results/20261006T181924Z-vocab-3-subset/result.json) | code / 48 | 39.75 | 0.415 | 116.8 | 37.67 | 1.41 | 0.00 | passed |
| [vocab-3-subset](results/20261006T181924Z-vocab-3-subset/result.json) | prose / 53 | 31.42 | 0.406 | 130.9 | 37.67 | 1.41 | 0.00 | passed |
| [vocab-3-subset](results/20261006T181924Z-vocab-3-subset/result.json) | synthetic / 512 | 34.17 | 1.489 | 358.5 | 37.67 | 1.41 | 0.00 | passed |
| [vocab-3-subset](results/20261006T181924Z-vocab-3-subset/result.json) | synthetic / 2048 | 34.59 | 5.294 | 387.1 | 37.67 | 1.41 | 0.00 | passed |
| [vocab-4-subset](results/20261006T182225Z-vocab-4-subset/result.json) | synthetic / 512 | 33.54 | 1.206 | 426.2 | 37.81 | 1.35 | 0.00 | failed |
| [feature-shared-cpu](results/20261006T182755Z-feature-shared-cpu/result.json) | chinese / 56 | 32.52 | 0.538 | 104.1 | 31.21 | 1.37 | 0.05 | passed |
| [feature-shared-cpu](results/20261006T182755Z-feature-shared-cpu/result.json) | code / 48 | 39.69 | 0.551 | 87.4 | 31.21 | 1.37 | 0.05 | passed |
| [feature-shared-cpu](results/20261006T182755Z-feature-shared-cpu/result.json) | prose / 53 | 36.46 | 0.768 | 69.1 | 31.21 | 1.37 | 0.05 | passed |
| [feature-shared-cpu](results/20261006T182755Z-feature-shared-cpu/result.json) | synthetic / 512 | 36.35 | 1.344 | 381.3 | 31.21 | 1.37 | 0.05 | passed |
| [feature-shared-cpu](results/20261006T182755Z-feature-shared-cpu/result.json) | synthetic / 2048 | 35.81 | 4.572 | 448.0 | 31.21 | 1.37 | 0.05 | passed |
| [feature-shared-gpu](results/20261006T182852Z-feature-shared-gpu/result.json) | synthetic / 512 | 2.96 | 1.458 | 351.4 | 37.27 | 1.36 | 0.00 | failed |
| [feature-shared-gpu](results/20261006T182852Z-feature-shared-gpu/result.json) | synthetic / 2048 | 4.98 | 7.180 | 285.3 | 37.27 | 1.36 | 0.00 | failed |
| [feature-shared-gpu](results/20261006T183135Z-feature-shared-gpu/result.json) | chinese / 56 | 4.31 | 1.980 | 28.3 | 36.94 | 1.36 | 0.00 | passed |
| [feature-shared-gpu](results/20261006T183135Z-feature-shared-gpu/result.json) | code / 48 | 6.64 | 1.290 | 37.2 | 36.94 | 1.36 | 0.00 | passed |
| [feature-shared-gpu](results/20261006T183135Z-feature-shared-gpu/result.json) | prose / 53 | 4.50 | 1.419 | 37.4 | 36.94 | 1.36 | 0.00 | passed |
| [feature-shared-gpu](results/20261006T183135Z-feature-shared-gpu/result.json) | synthetic / 512 | 10.09 | 3.815 | 134.2 | 36.94 | 1.36 | 0.00 | passed |
| [feature-shared-gpu](results/20261006T183135Z-feature-shared-gpu/result.json) | synthetic / 2048 | 5.30 | 13.219 | 154.9 | 36.94 | 1.36 | 0.00 | passed |
| [feature-shared-mixed](results/20261006T183622Z-feature-shared-mixed/result.json) | - | - | - | - | 37.39 | 1.35 | 0.00 | failed: RuntimeError: Streaming response has no first token or final timing record |
| [feature-shared-mixed](results/20261006T183903Z-feature-shared-mixed/result.json) | chinese / 56 | 33.86 | 0.345 | 162.5 | 34.58 | 1.33 | 0.00 | passed |
| [feature-shared-mixed](results/20261006T183903Z-feature-shared-mixed/result.json) | code / 48 | 44.84 | 0.318 | 151.3 | 34.58 | 1.33 | 0.00 | passed |
| [feature-shared-mixed](results/20261006T183903Z-feature-shared-mixed/result.json) | prose / 53 | 38.80 | 0.321 | 165.1 | 34.58 | 1.33 | 0.00 | passed |
| [feature-shared-mixed](results/20261006T183903Z-feature-shared-mixed/result.json) | synthetic / 512 | 35.11 | 1.109 | 462.4 | 34.58 | 1.33 | 0.00 | passed |
| [feature-shared-mixed](results/20261006T183903Z-feature-shared-mixed/result.json) | synthetic / 2048 | 41.69 | 3.925 | 522.0 | 34.58 | 1.33 | 0.00 | passed |
| [vocab-1-plain](results/20261006T183950Z-vocab-1-plain/result.json) | chinese / 56 | 37.57 | 0.283 | 198.3 | 36.18 | 1.30 | 0.00 | passed |
| [vocab-1-plain](results/20261006T183950Z-vocab-1-plain/result.json) | code / 48 | 37.23 | 0.271 | 177.7 | 36.18 | 1.30 | 0.00 | passed |
| [vocab-1-plain](results/20261006T183950Z-vocab-1-plain/result.json) | prose / 53 | 38.32 | 0.276 | 192.8 | 36.18 | 1.30 | 0.00 | passed |
| [vocab-1-plain](results/20261006T183950Z-vocab-1-plain/result.json) | synthetic / 512 | 37.12 | 0.759 | 675.4 | 36.18 | 1.30 | 0.00 | passed |
| [vocab-1-plain](results/20261006T183950Z-vocab-1-plain/result.json) | synthetic / 2048 | 35.79 | 3.156 | 649.2 | 36.18 | 1.30 | 0.00 | passed |
| [vocab-2-full](results/20261006T184129Z-vocab-2-full/result.json) | chinese / 56 | 34.70 | 0.346 | 162.1 | 37.45 | 1.30 | 0.00 | passed |
| [vocab-2-full](results/20261006T184129Z-vocab-2-full/result.json) | code / 48 | 44.83 | 0.336 | 143.2 | 37.45 | 1.30 | 0.00 | passed |
| [vocab-2-full](results/20261006T184129Z-vocab-2-full/result.json) | prose / 53 | 37.09 | 0.347 | 153.0 | 37.45 | 1.30 | 0.00 | passed |
| [vocab-2-full](results/20261006T184129Z-vocab-2-full/result.json) | synthetic / 512 | 37.48 | 1.146 | 449.5 | 37.45 | 1.30 | 0.00 | passed |
| [vocab-2-full](results/20261006T184129Z-vocab-2-full/result.json) | synthetic / 2048 | 36.74 | 4.556 | 449.7 | 37.45 | 1.30 | 0.00 | passed |
| [vocab-3-subset](results/20261006T184322Z-vocab-3-subset/result.json) | chinese / 56 | 35.15 | 0.369 | 152.4 | 38.34 | 1.35 | 0.05 | passed |
| [vocab-3-subset](results/20261006T184322Z-vocab-3-subset/result.json) | code / 48 | 43.53 | 0.625 | 97.9 | 38.34 | 1.35 | 0.05 | passed |
| [vocab-3-subset](results/20261006T184322Z-vocab-3-subset/result.json) | prose / 53 | 38.47 | 0.370 | 143.5 | 38.34 | 1.35 | 0.05 | passed |
| [vocab-3-subset](results/20261006T184322Z-vocab-3-subset/result.json) | synthetic / 512 | 39.15 | 1.083 | 473.3 | 38.34 | 1.35 | 0.05 | passed |
| [vocab-3-subset](results/20261006T184322Z-vocab-3-subset/result.json) | synthetic / 2048 | 38.75 | 4.644 | 442.6 | 38.34 | 1.35 | 0.05 | passed |
| [vocab-4-subset](results/20261006T184513Z-vocab-4-subset/result.json) | chinese / 56 | 35.58 | 0.344 | 162.9 | 38.48 | 1.35 | 0.00 | passed |
| [vocab-4-subset](results/20261006T184513Z-vocab-4-subset/result.json) | code / 48 | 43.68 | 0.344 | 139.6 | 38.48 | 1.35 | 0.00 | passed |
| [vocab-4-subset](results/20261006T184513Z-vocab-4-subset/result.json) | prose / 53 | 31.18 | 0.354 | 149.9 | 38.48 | 1.35 | 0.00 | passed |
| [vocab-4-subset](results/20261006T184513Z-vocab-4-subset/result.json) | synthetic / 512 | 39.11 | 1.090 | 470.0 | 38.48 | 1.35 | 0.00 | passed |
| [vocab-4-subset](results/20261006T184513Z-vocab-4-subset/result.json) | synthetic / 2048 | 38.63 | 4.738 | 435.1 | 38.48 | 1.35 | 0.00 | passed |
| [vocab-5-full](results/20261006T184707Z-vocab-5-full/result.json) | chinese / 56 | 34.79 | 0.344 | 162.9 | 38.21 | 1.34 | 0.00 | passed |
| [vocab-5-full](results/20261006T184707Z-vocab-5-full/result.json) | code / 48 | 43.25 | 0.348 | 138.1 | 38.21 | 1.34 | 0.00 | passed |
| [vocab-5-full](results/20261006T184707Z-vocab-5-full/result.json) | prose / 53 | 37.10 | 0.353 | 150.4 | 38.21 | 1.34 | 0.00 | passed |
| [vocab-5-full](results/20261006T184707Z-vocab-5-full/result.json) | synthetic / 512 | 37.75 | 1.076 | 476.4 | 38.21 | 1.34 | 0.00 | passed |
| [vocab-5-full](results/20261006T184707Z-vocab-5-full/result.json) | synthetic / 2048 | 37.04 | 4.389 | 466.7 | 38.21 | 1.34 | 0.00 | passed |
| [vocab-6-plain](results/20261006T184856Z-vocab-6-plain/result.json) | chinese / 56 | 38.42 | 0.278 | 201.8 | 36.33 | 1.34 | 0.00 | passed |
| [vocab-6-plain](results/20261006T184856Z-vocab-6-plain/result.json) | code / 48 | 37.81 | 0.269 | 178.9 | 36.33 | 1.34 | 0.00 | passed |
| [vocab-6-plain](results/20261006T184856Z-vocab-6-plain/result.json) | prose / 53 | 38.08 | 0.275 | 193.0 | 36.33 | 1.34 | 0.00 | passed |
| [vocab-6-plain](results/20261006T184856Z-vocab-6-plain/result.json) | synthetic / 512 | 38.12 | 0.754 | 679.2 | 36.33 | 1.34 | 0.00 | passed |
| [vocab-6-plain](results/20261006T184856Z-vocab-6-plain/result.json) | synthetic / 2048 | 36.51 | 3.126 | 655.4 | 36.33 | 1.34 | 0.00 | passed |
| [shared-1-plain](results/20261006T185032Z-shared-1-plain/result.json) | chinese / 56 | 38.09 | 0.279 | 201.2 | 36.34 | 1.33 | 0.00 | passed |
| [shared-1-plain](results/20261006T185032Z-shared-1-plain/result.json) | code / 48 | 38.28 | 0.270 | 178.3 | 36.34 | 1.33 | 0.00 | passed |
| [shared-1-plain](results/20261006T185032Z-shared-1-plain/result.json) | prose / 53 | 38.23 | 0.275 | 193.1 | 36.34 | 1.33 | 0.00 | passed |
| [shared-1-plain](results/20261006T185032Z-shared-1-plain/result.json) | synthetic / 512 | 37.93 | 0.759 | 675.5 | 36.34 | 1.33 | 0.00 | passed |
| [shared-1-plain](results/20261006T185032Z-shared-1-plain/result.json) | synthetic / 2048 | 35.77 | 3.166 | 647.0 | 36.34 | 1.33 | 0.00 | passed |
| [shared-2-full](results/20261006T185208Z-shared-2-full/result.json) | chinese / 56 | 23.97 | 1.150 | 53.8 | 37.92 | 2.90 | 1.58 | failed |
| [shared-2-full](results/20261006T185208Z-shared-2-full/result.json) | code / 48 | 39.48 | 0.732 | 66.3 | 37.92 | 2.90 | 1.58 | failed |
| [shared-2-full](results/20261006T185208Z-shared-2-full/result.json) | prose / 53 | 32.44 | 0.506 | 107.7 | 37.92 | 2.90 | 1.58 | failed |
| [shared-2-full](results/20261006T185208Z-shared-2-full/result.json) | synthetic / 512 | 34.41 | 1.133 | 453.0 | 37.92 | 2.90 | 1.58 | failed |
| [shared-2-full](results/20261006T185208Z-shared-2-full/result.json) | synthetic / 2048 | 36.53 | 4.449 | 460.4 | 37.92 | 2.90 | 1.58 | failed |
| [shared-1-plain](results/20261006T185833Z-shared-1-plain/result.json) | chinese / 56 | 37.61 | 0.281 | 199.6 | 36.24 | 1.68 | 0.00 | passed |
| [shared-1-plain](results/20261006T185833Z-shared-1-plain/result.json) | code / 48 | 37.98 | 0.269 | 179.0 | 36.24 | 1.68 | 0.00 | passed |
| [shared-1-plain](results/20261006T185833Z-shared-1-plain/result.json) | prose / 53 | 37.38 | 0.279 | 190.2 | 36.24 | 1.68 | 0.00 | passed |
| [shared-1-plain](results/20261006T185833Z-shared-1-plain/result.json) | synthetic / 512 | 38.12 | 0.753 | 680.3 | 36.24 | 1.68 | 0.00 | passed |
| [shared-1-plain](results/20261006T185833Z-shared-1-plain/result.json) | synthetic / 2048 | 36.41 | 3.128 | 654.8 | 36.24 | 1.68 | 0.00 | passed |
| [shared-2-full](results/20261006T190011Z-shared-2-full/result.json) | chinese / 56 | 31.84 | 0.391 | 143.9 | 38.05 | 1.63 | 0.00 | passed |
| [shared-2-full](results/20261006T190011Z-shared-2-full/result.json) | code / 48 | 43.51 | 0.355 | 135.5 | 38.05 | 1.63 | 0.00 | passed |
| [shared-2-full](results/20261006T190011Z-shared-2-full/result.json) | prose / 53 | 35.63 | 0.356 | 149.0 | 38.05 | 1.63 | 0.00 | passed |
| [shared-2-full](results/20261006T190011Z-shared-2-full/result.json) | synthetic / 512 | 37.03 | 1.132 | 452.8 | 38.05 | 1.63 | 0.00 | passed |
| [shared-2-full](results/20261006T190011Z-shared-2-full/result.json) | synthetic / 2048 | 36.37 | 4.544 | 450.8 | 38.05 | 1.63 | 0.00 | passed |
| [shared-3-shared-cpu](results/20261006T190204Z-shared-3-shared-cpu/result.json) | chinese / 56 | 33.04 | 0.385 | 146.0 | 37.90 | 1.59 | 0.00 | passed |
| [shared-3-shared-cpu](results/20261006T190204Z-shared-3-shared-cpu/result.json) | code / 48 | 41.82 | 0.350 | 137.3 | 37.90 | 1.59 | 0.00 | passed |
| [shared-3-shared-cpu](results/20261006T190204Z-shared-3-shared-cpu/result.json) | prose / 53 | 33.56 | 0.446 | 119.0 | 37.90 | 1.59 | 0.00 | passed |
| [shared-3-shared-cpu](results/20261006T190204Z-shared-3-shared-cpu/result.json) | synthetic / 512 | 36.04 | 1.180 | 434.8 | 37.90 | 1.59 | 0.00 | passed |
| [shared-3-shared-cpu](results/20261006T190204Z-shared-3-shared-cpu/result.json) | synthetic / 2048 | 36.65 | 4.616 | 443.7 | 37.90 | 1.59 | 0.00 | passed |
| [shared-4-shared-mixed](results/20261006T190357Z-shared-4-shared-mixed/result.json) | chinese / 56 | 34.77 | 0.313 | 179.2 | 37.87 | 1.54 | 0.00 | passed |
| [shared-4-shared-mixed](results/20261006T190357Z-shared-4-shared-mixed/result.json) | code / 48 | 42.36 | 0.310 | 155.3 | 37.87 | 1.54 | 0.00 | passed |
| [shared-4-shared-mixed](results/20261006T190357Z-shared-4-shared-mixed/result.json) | prose / 53 | 37.80 | 0.311 | 170.9 | 37.87 | 1.54 | 0.00 | passed |
| [shared-4-shared-mixed](results/20261006T190357Z-shared-4-shared-mixed/result.json) | synthetic / 512 | 40.65 | 1.018 | 503.7 | 37.87 | 1.54 | 0.00 | passed |
| [shared-4-shared-mixed](results/20261006T190357Z-shared-4-shared-mixed/result.json) | synthetic / 2048 | 38.90 | 4.106 | 499.0 | 37.87 | 1.54 | 0.00 | passed |
| [shared-5-shared-mixed](results/20261006T190540Z-shared-5-shared-mixed/result.json) | chinese / 56 | 33.65 | 0.331 | 169.6 | 37.74 | 1.54 | 0.00 | passed |
| [shared-5-shared-mixed](results/20261006T190540Z-shared-5-shared-mixed/result.json) | code / 48 | 43.50 | 0.310 | 154.9 | 37.74 | 1.54 | 0.00 | passed |
| [shared-5-shared-mixed](results/20261006T190540Z-shared-5-shared-mixed/result.json) | prose / 53 | 34.46 | 0.360 | 149.1 | 37.74 | 1.54 | 0.00 | passed |
| [shared-5-shared-mixed](results/20261006T190540Z-shared-5-shared-mixed/result.json) | synthetic / 512 | 41.47 | 0.953 | 537.7 | 37.74 | 1.54 | 0.00 | passed |
| [shared-5-shared-mixed](results/20261006T190540Z-shared-5-shared-mixed/result.json) | synthetic / 2048 | 39.32 | 4.185 | 489.6 | 37.74 | 1.54 | 0.00 | passed |
| [shared-6-shared-cpu](results/20261006T190724Z-shared-6-shared-cpu/result.json) | chinese / 56 | 34.77 | 0.350 | 160.1 | 37.69 | 1.48 | 0.00 | passed |
| [shared-6-shared-cpu](results/20261006T190724Z-shared-6-shared-cpu/result.json) | code / 48 | 42.85 | 0.351 | 137.2 | 37.69 | 1.48 | 0.00 | passed |
| [shared-6-shared-cpu](results/20261006T190724Z-shared-6-shared-cpu/result.json) | prose / 53 | 35.78 | 0.417 | 129.8 | 37.69 | 1.48 | 0.00 | passed |
| [shared-6-shared-cpu](results/20261006T190724Z-shared-6-shared-cpu/result.json) | synthetic / 512 | 38.30 | 1.085 | 472.3 | 37.69 | 1.48 | 0.00 | passed |
| [shared-6-shared-cpu](results/20261006T190724Z-shared-6-shared-cpu/result.json) | synthetic / 2048 | 38.42 | 4.385 | 467.1 | 37.69 | 1.48 | 0.00 | passed |
| [shared-7-full](results/20261006T190914Z-shared-7-full/result.json) | chinese / 56 | 32.68 | 0.370 | 151.6 | 37.97 | 1.47 | 0.00 | passed |
| [shared-7-full](results/20261006T190914Z-shared-7-full/result.json) | code / 48 | 40.66 | 0.373 | 129.0 | 37.97 | 1.47 | 0.00 | passed |
| [shared-7-full](results/20261006T190914Z-shared-7-full/result.json) | prose / 53 | 34.57 | 0.414 | 128.4 | 37.97 | 1.47 | 0.00 | passed |
| [shared-7-full](results/20261006T190914Z-shared-7-full/result.json) | synthetic / 512 | 36.87 | 1.529 | 361.9 | 37.97 | 1.47 | 0.00 | passed |
| [shared-7-full](results/20261006T190914Z-shared-7-full/result.json) | synthetic / 2048 | 35.68 | 4.832 | 426.3 | 37.97 | 1.47 | 0.00 | passed |
| [shared-8-plain](results/20261006T191108Z-shared-8-plain/result.json) | chinese / 56 | 36.77 | 0.285 | 196.7 | 36.32 | 1.46 | 0.00 | passed |
| [shared-8-plain](results/20261006T191108Z-shared-8-plain/result.json) | code / 48 | 37.12 | 0.269 | 178.8 | 36.32 | 1.46 | 0.00 | passed |
| [shared-8-plain](results/20261006T191108Z-shared-8-plain/result.json) | prose / 53 | 36.84 | 0.280 | 189.4 | 36.32 | 1.46 | 0.00 | passed |
| [shared-8-plain](results/20261006T191108Z-shared-8-plain/result.json) | synthetic / 512 | 36.93 | 0.775 | 660.9 | 36.32 | 1.46 | 0.00 | passed |
| [shared-8-plain](results/20261006T191108Z-shared-8-plain/result.json) | synthetic / 2048 | 35.66 | 3.268 | 626.9 | 36.32 | 1.46 | 0.00 | passed |
| [tuning-depth-1-2](results/20261006T211035Z-tuning-depth-1-2/result.json) | chinese / 56 | 36.18 | 0.305 | 184.2 | 31.70 | 1.12 | 0.00 | passed |
| [tuning-depth-1-2](results/20261006T211035Z-tuning-depth-1-2/result.json) | code / 48 | 45.92 | 0.293 | 164.4 | 31.70 | 1.12 | 0.00 | passed |
| [tuning-depth-1-2](results/20261006T211035Z-tuning-depth-1-2/result.json) | prose / 53 | 39.95 | 0.301 | 176.3 | 31.70 | 1.12 | 0.00 | passed |
| [tuning-depth-1-2](results/20261006T211035Z-tuning-depth-1-2/result.json) | synthetic / 512 | 42.81 | 0.932 | 549.6 | 31.70 | 1.12 | 0.00 | passed |
| [tuning-depth-1-2](results/20261006T211035Z-tuning-depth-1-2/result.json) | synthetic / 2048 | 41.45 | 3.811 | 537.5 | 31.70 | 1.12 | 0.00 | passed |
| [tuning-depth-2-1](results/20261006T211229Z-tuning-depth-2-1/result.json) | chinese / 56 | 42.04 | 0.309 | 181.6 | 37.68 | 1.12 | 0.00 | passed |
| [tuning-depth-2-1](results/20261006T211229Z-tuning-depth-2-1/result.json) | code / 48 | 46.43 | 0.293 | 164.1 | 37.68 | 1.12 | 0.00 | passed |
| [tuning-depth-2-1](results/20261006T211229Z-tuning-depth-2-1/result.json) | prose / 53 | 41.11 | 0.305 | 174.2 | 37.68 | 1.12 | 0.00 | passed |
| [tuning-depth-2-1](results/20261006T211229Z-tuning-depth-2-1/result.json) | synthetic / 512 | 44.54 | 0.943 | 543.3 | 37.68 | 1.12 | 0.00 | passed |
| [tuning-depth-2-1](results/20261006T211229Z-tuning-depth-2-1/result.json) | synthetic / 2048 | 41.36 | 3.887 | 527.0 | 37.68 | 1.12 | 0.00 | passed |
| [tuning-depth-3-3](results/20261006T211405Z-tuning-depth-3-3/result.json) | chinese / 56 | 34.35 | 0.311 | 180.4 | 38.03 | 1.12 | 0.00 | passed |
| [tuning-depth-3-3](results/20261006T211405Z-tuning-depth-3-3/result.json) | code / 48 | 48.36 | 0.296 | 162.3 | 38.03 | 1.12 | 0.00 | passed |
| [tuning-depth-3-3](results/20261006T211405Z-tuning-depth-3-3/result.json) | prose / 53 | 36.65 | 0.306 | 173.3 | 38.03 | 1.12 | 0.00 | passed |
| [tuning-depth-3-3](results/20261006T211405Z-tuning-depth-3-3/result.json) | synthetic / 512 | 41.82 | 0.954 | 536.8 | 38.03 | 1.12 | 0.00 | passed |
| [tuning-depth-3-3](results/20261006T211405Z-tuning-depth-3-3/result.json) | synthetic / 2048 | 43.05 | 3.918 | 522.8 | 38.03 | 1.12 | 0.00 | passed |
| [tuning-depth-4-4](results/20261006T211545Z-tuning-depth-4-4/result.json) | chinese / 56 | 29.37 | 0.306 | 183.1 | 38.07 | 1.12 | 0.00 | passed |
| [tuning-depth-4-4](results/20261006T211545Z-tuning-depth-4-4/result.json) | code / 48 | 46.37 | 0.298 | 161.7 | 38.07 | 1.12 | 0.00 | passed |
| [tuning-depth-4-4](results/20261006T211545Z-tuning-depth-4-4/result.json) | prose / 53 | 34.29 | 0.305 | 174.2 | 38.07 | 1.12 | 0.00 | passed |
| [tuning-depth-4-4](results/20261006T211545Z-tuning-depth-4-4/result.json) | synthetic / 512 | 38.05 | 0.945 | 542.1 | 38.07 | 1.12 | 0.00 | passed |
| [tuning-depth-4-4](results/20261006T211545Z-tuning-depth-4-4/result.json) | synthetic / 2048 | 41.22 | 3.883 | 527.6 | 38.07 | 1.12 | 0.00 | passed |
| [tuning-depth-5-4](results/20261006T211729Z-tuning-depth-5-4/result.json) | chinese / 56 | 29.34 | 0.312 | 179.9 | 38.15 | 1.10 | 0.00 | passed |
| [tuning-depth-5-4](results/20261006T211729Z-tuning-depth-5-4/result.json) | code / 48 | 46.56 | 0.293 | 164.2 | 38.15 | 1.10 | 0.00 | passed |
| [tuning-depth-5-4](results/20261006T211729Z-tuning-depth-5-4/result.json) | prose / 53 | 34.36 | 0.304 | 174.9 | 38.15 | 1.10 | 0.00 | passed |
| [tuning-depth-5-4](results/20261006T211729Z-tuning-depth-5-4/result.json) | synthetic / 512 | 38.08 | 0.941 | 544.3 | 38.15 | 1.10 | 0.00 | passed |
| [tuning-depth-5-4](results/20261006T211729Z-tuning-depth-5-4/result.json) | synthetic / 2048 | 40.90 | 3.859 | 530.8 | 38.15 | 1.10 | 0.00 | passed |
| [tuning-depth-6-3](results/20261006T211913Z-tuning-depth-6-3/result.json) | chinese / 56 | 34.27 | 0.306 | 183.1 | 37.89 | 1.10 | 0.00 | passed |
| [tuning-depth-6-3](results/20261006T211913Z-tuning-depth-6-3/result.json) | code / 48 | 47.88 | 0.295 | 162.9 | 37.89 | 1.10 | 0.00 | passed |
| [tuning-depth-6-3](results/20261006T211913Z-tuning-depth-6-3/result.json) | prose / 53 | 36.45 | 0.307 | 173.2 | 37.89 | 1.10 | 0.00 | passed |
| [tuning-depth-6-3](results/20261006T211913Z-tuning-depth-6-3/result.json) | synthetic / 512 | 41.87 | 0.946 | 541.8 | 37.89 | 1.10 | 0.00 | passed |
| [tuning-depth-6-3](results/20261006T211913Z-tuning-depth-6-3/result.json) | synthetic / 2048 | 42.61 | 3.856 | 531.2 | 37.89 | 1.10 | 0.00 | passed |
| [tuning-depth-7-1](results/20261006T212052Z-tuning-depth-7-1/result.json) | chinese / 56 | 42.03 | 0.306 | 183.2 | 37.66 | 1.09 | 0.00 | passed |
| [tuning-depth-7-1](results/20261006T212052Z-tuning-depth-7-1/result.json) | code / 48 | 46.22 | 0.292 | 164.8 | 37.66 | 1.09 | 0.00 | passed |
| [tuning-depth-7-1](results/20261006T212052Z-tuning-depth-7-1/result.json) | prose / 53 | 40.73 | 0.303 | 175.3 | 37.66 | 1.09 | 0.00 | passed |
| [tuning-depth-7-1](results/20261006T212052Z-tuning-depth-7-1/result.json) | synthetic / 512 | 44.44 | 0.945 | 542.1 | 37.66 | 1.09 | 0.00 | passed |
| [tuning-depth-7-1](results/20261006T212052Z-tuning-depth-7-1/result.json) | synthetic / 2048 | 41.33 | 3.855 | 531.3 | 37.66 | 1.09 | 0.00 | passed |
| [tuning-depth-8-2](results/20261006T212228Z-tuning-depth-8-2/result.json) | chinese / 56 | 36.12 | 0.307 | 182.5 | 37.88 | 1.09 | 0.00 | passed |
| [tuning-depth-8-2](results/20261006T212228Z-tuning-depth-8-2/result.json) | code / 48 | 45.91 | 0.293 | 164.1 | 37.88 | 1.09 | 0.00 | passed |
| [tuning-depth-8-2](results/20261006T212228Z-tuning-depth-8-2/result.json) | prose / 53 | 39.85 | 0.302 | 175.9 | 37.88 | 1.09 | 0.00 | passed |
| [tuning-depth-8-2](results/20261006T212228Z-tuning-depth-8-2/result.json) | synthetic / 512 | 42.64 | 0.957 | 537.1 | 37.88 | 1.09 | 0.00 | passed |
| [tuning-depth-8-2](results/20261006T212228Z-tuning-depth-8-2/result.json) | synthetic / 2048 | 41.27 | 3.867 | 529.7 | 37.88 | 1.09 | 0.00 | passed |
| [tuning-threads-1-8](results/20261006T212441Z-tuning-threads-1-8/result.json) | chinese / 56 | 36.18 | 0.308 | 182.3 | 37.79 | 1.09 | 0.00 | passed |
| [tuning-threads-1-8](results/20261006T212441Z-tuning-threads-1-8/result.json) | code / 48 | 45.65 | 0.297 | 162.1 | 37.79 | 1.09 | 0.00 | passed |
| [tuning-threads-1-8](results/20261006T212441Z-tuning-threads-1-8/result.json) | prose / 53 | 39.79 | 0.306 | 173.5 | 37.79 | 1.09 | 0.00 | passed |
| [tuning-threads-1-8](results/20261006T212441Z-tuning-threads-1-8/result.json) | synthetic / 512 | 42.97 | 0.927 | 553.0 | 37.79 | 1.09 | 0.00 | passed |
| [tuning-threads-1-8](results/20261006T212441Z-tuning-threads-1-8/result.json) | synthetic / 2048 | 41.45 | 3.831 | 534.6 | 37.79 | 1.09 | 0.00 | passed |
| [tuning-threads-2-6](results/20261006T212620Z-tuning-threads-2-6/result.json) | chinese / 56 | 36.24 | 0.310 | 181.2 | 37.84 | 1.09 | 0.00 | passed |
| [tuning-threads-2-6](results/20261006T212620Z-tuning-threads-2-6/result.json) | code / 48 | 45.74 | 0.300 | 160.2 | 37.84 | 1.09 | 0.00 | passed |
| [tuning-threads-2-6](results/20261006T212620Z-tuning-threads-2-6/result.json) | prose / 53 | 40.23 | 0.304 | 174.4 | 37.84 | 1.09 | 0.00 | passed |
| [tuning-threads-2-6](results/20261006T212620Z-tuning-threads-2-6/result.json) | synthetic / 512 | 42.90 | 0.974 | 526.1 | 37.84 | 1.09 | 0.00 | passed |
| [tuning-threads-2-6](results/20261006T212620Z-tuning-threads-2-6/result.json) | synthetic / 2048 | 41.53 | 3.995 | 512.8 | 37.84 | 1.09 | 0.00 | passed |
| [tuning-threads-3-12](results/20261006T212759Z-tuning-threads-3-12/result.json) | chinese / 56 | 36.17 | 0.306 | 183.5 | 37.70 | 1.08 | 0.00 | passed |
| [tuning-threads-3-12](results/20261006T212759Z-tuning-threads-3-12/result.json) | code / 48 | 45.65 | 0.295 | 163.2 | 37.70 | 1.08 | 0.00 | passed |
| [tuning-threads-3-12](results/20261006T212759Z-tuning-threads-3-12/result.json) | prose / 53 | 39.91 | 0.301 | 176.4 | 37.70 | 1.08 | 0.00 | passed |
| [tuning-threads-3-12](results/20261006T212759Z-tuning-threads-3-12/result.json) | synthetic / 512 | 42.99 | 0.909 | 563.5 | 37.70 | 1.08 | 0.00 | passed |
| [tuning-threads-3-12](results/20261006T212759Z-tuning-threads-3-12/result.json) | synthetic / 2048 | 41.42 | 3.737 | 548.1 | 37.70 | 1.08 | 0.00 | passed |
| [tuning-threads-4-12](results/20261006T212936Z-tuning-threads-4-12/result.json) | chinese / 56 | 36.09 | 0.306 | 183.2 | 37.77 | 1.08 | 0.00 | passed |
| [tuning-threads-4-12](results/20261006T212936Z-tuning-threads-4-12/result.json) | code / 48 | 45.82 | 0.291 | 165.1 | 37.77 | 1.08 | 0.00 | passed |
| [tuning-threads-4-12](results/20261006T212936Z-tuning-threads-4-12/result.json) | prose / 53 | 39.87 | 0.301 | 176.6 | 37.77 | 1.08 | 0.00 | passed |
| [tuning-threads-4-12](results/20261006T212936Z-tuning-threads-4-12/result.json) | synthetic / 512 | 42.75 | 0.914 | 560.7 | 37.77 | 1.08 | 0.00 | passed |
| [tuning-threads-4-12](results/20261006T212936Z-tuning-threads-4-12/result.json) | synthetic / 2048 | 41.39 | 3.731 | 549.0 | 37.77 | 1.08 | 0.00 | passed |
| [tuning-threads-5-6](results/20261006T213114Z-tuning-threads-5-6/result.json) | chinese / 56 | 36.27 | 0.307 | 182.4 | 37.87 | 1.06 | 0.00 | passed |
| [tuning-threads-5-6](results/20261006T213114Z-tuning-threads-5-6/result.json) | code / 48 | 46.16 | 0.298 | 161.6 | 37.87 | 1.06 | 0.00 | passed |
| [tuning-threads-5-6](results/20261006T213114Z-tuning-threads-5-6/result.json) | prose / 53 | 40.00 | 0.305 | 173.9 | 37.87 | 1.06 | 0.00 | passed |
| [tuning-threads-5-6](results/20261006T213114Z-tuning-threads-5-6/result.json) | synthetic / 512 | 43.13 | 0.956 | 535.8 | 37.87 | 1.06 | 0.00 | passed |
| [tuning-threads-5-6](results/20261006T213114Z-tuning-threads-5-6/result.json) | synthetic / 2048 | 41.74 | 3.945 | 519.3 | 37.87 | 1.06 | 0.00 | passed |
| [tuning-threads-6-8](results/20261006T213253Z-tuning-threads-6-8/result.json) | chinese / 56 | 36.03 | 0.310 | 181.1 | 37.86 | 1.06 | 0.00 | passed |
| [tuning-threads-6-8](results/20261006T213253Z-tuning-threads-6-8/result.json) | code / 48 | 45.64 | 0.293 | 164.0 | 37.86 | 1.06 | 0.00 | passed |
| [tuning-threads-6-8](results/20261006T213253Z-tuning-threads-6-8/result.json) | prose / 53 | 39.71 | 0.302 | 175.8 | 37.86 | 1.06 | 0.00 | passed |
| [tuning-threads-6-8](results/20261006T213253Z-tuning-threads-6-8/result.json) | synthetic / 512 | 42.41 | 0.973 | 527.1 | 37.86 | 1.06 | 0.00 | passed |
| [tuning-threads-6-8](results/20261006T213253Z-tuning-threads-6-8/result.json) | synthetic / 2048 | 41.23 | 3.856 | 531.3 | 37.86 | 1.06 | 0.00 | passed |

## Optimization 1: conversation caching

Matched follow-up prompts through the Strata adapter, caching off versus on. Same model/settings, alternating pair order, excluded warm-up pairs. This measures follow-up waiting, not fresh-prompt throughput.

| Model / run | History budget | First token off (s) | First token on (s) | Less waiting | Less total response time | Output speed change | Checks | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| [small / 20261006T140905Z-small-conversation-cache](results/20261006T140905Z-small-conversation-cache/comparison.json) | 512 | 0.306 | 0.080 | 73.7% | 36.5% | -0.0% | 9/9 | passed |
| [small / 20261006T140905Z-small-conversation-cache](results/20261006T140905Z-small-conversation-cache/comparison.json) | 2048 | 1.005 | 0.083 | 91.8% | 70.4% | -0.0% | 9/9 | passed |
| [flash / 20261006T141016Z-flash-conversation-cache](results/20261006T141016Z-flash-conversation-cache/comparison.json) | 512 | 0.951 | 0.259 | 72.8% | 44.1% | +1.0% | 15/15 | passed |
| [flash / 20261006T141016Z-flash-conversation-cache](results/20261006T141016Z-flash-conversation-cache/comparison.json) | 2048 | 3.351 | 0.272 | 91.9% | 77.4% | -0.7% | 15/15 | passed |
| [flash / 20261006T150238Z-flash-prediction-cache-baseline-t06](results/20261006T150238Z-flash-prediction-cache-baseline-t06/comparison.json) | 512 | 0.947 | 0.258 | 72.8% | 44.0% | +0.3% | 11/11 | passed |
| [flash / 20261006T150238Z-flash-prediction-cache-baseline-t06](results/20261006T150238Z-flash-prediction-cache-baseline-t06/comparison.json) | 2048 | 3.340 | 0.271 | 91.9% | 77.5% | -0.5% | 11/11 | passed |

Reduction = 100 x (1 - cached duration / uncached duration). Output speed change = 100 x (cached rate / uncached rate - 1). Prompt cache is one engine slot; an unrelated chat may replace it. Memory samples cover both modes in the same process; paired RSS values are not isolated allocation measurements.

[Optimization 2: prediction-helper percentages, tradeoffs and decision](PREDICTION.md)

[Optimization 3: isolated Q2 Metal measurements and decision](Q2-METAL.md)

[Optimization 4: smaller draft vocabulary](DRAFT-VOCAB.md)

[Optimization 5: sharing helper weights and GPU placement](SHARED-HELPER.md)

[Optimization 6: helper prediction depth and CPU workers](HELPER-TUNING.md)

## Interpretation

- Compare changes within the same model, prompt hash, sampling settings and context. Model names ending Q2_0 or Q4_K_M describe compressed weights, not fewer model layers or experts.
- Speed runs ignore EOS to generate a fixed output length. Separate normal chat checks test answer correctness and stop handling. Two sanity questions do not establish overall model quality.
- No concurrent model downloads during speed runs. OS file caches are uncontrolled; these are not guaranteed cold SSD tests. The first request may include additional shader compilation.
- RSS is a process measurement, not total GPU usage. Read the full-model native allocation log too. System disk reads include unrelated activity.
- Swap growth is relative to the start of each run. Peak swap includes pages left swapped by earlier experiments; the 8K run inherited swap from the CPU draft test.
- The default guard stops a run if swap grows by more than 2 GiB or available RAM stays below 384 MiB for four seconds. A stopped configuration is recorded as a failure, not a speed result.

## Integration checks

- [20261006T110621Z-small-integration](results/20261006T110621Z-small-integration.json): 8/9 checks passed.
- [20261006T110714Z-small-integration](results/20261006T110714Z-small-integration.json): 9/9 checks passed.
- [20261006T112221Z-flash-integration](results/20261006T112221Z-flash-integration.json): 9/9 checks passed.
- [20261006T141248Z-flash-integration](results/20261006T141248Z-flash-integration.json): 9/9 checks passed.
- [20261006T155222Z-flash-integration](results/20261006T155222Z-flash-integration.json): 9/9 checks passed.
- [20261006T185730Z-flash-integration](results/20261006T185730Z-flash-integration.json): 9/9 checks passed.
- [20261006T213453Z-flash-integration](results/20261006T213453Z-flash-integration.json): 9/9 checks passed.
- [20261006T213646Z-flash-integration](results/20261006T213646Z-flash-integration.json): 9/9 checks passed.
- [20261006T213653Z-flash-integration](results/20261006T213653Z-flash-integration.json): 9/9 checks passed.
- [20261006T213659Z-flash-integration](results/20261006T213659Z-flash-integration.json): 9/9 checks passed.
- [20261006T112501Z-flash-context-probe](results/20261006T112501Z-flash-context-probe.json): passed, varied records across 2831 input tokens.
- [20261006T141353Z-flash-cache-api](results/20261006T141353Z-flash-cache-api.json): 2/2 real Strata HTTP follow-ups correct with confirmed native cache reuse.

Initial SSD measurement: [raw data](results/ssd-initial.json). GGUF layouts: [full model](results/flash-gguf-inventory.json), [draft head](results/mtp-gguf-inventory.json).
