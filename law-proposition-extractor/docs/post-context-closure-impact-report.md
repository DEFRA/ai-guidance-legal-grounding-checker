# Post context-closure impact report

**Date:** 2026-06-12
**Corpus:** Slurry GB principal-5 (727-fragment regenerated export)
**Export:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export`

Before/after comparison on the **same export bundle** with effective law re-derived with (before) legacy export closure vs (after) Prompt 86-BR1 workbench-aligned locator resolution.

## Executive summary

- **Context closure:** unresolved required_context entries **283 → 44** (-239); empty proposition_ids **306 → 63**.
- **Composition opacity:** trace-reviewable opaque statements **248 → 480** (+232); trace-blocked **417 → 252** (-165).
- **Context-dependent trace-blocked:** **301 → 234** (-67).
- **Verdict:** Export context closure materially improves trace reviewability for context-dependent statements; remaining opacity is dominated by monolithic composition (statement text = core proposition only), not missing locator closure.

## 1. Context closure

| Metric | Before 86-BR1 | After 86-BR1 | Delta |
| --- | ---: | ---: | ---: |
| Unresolved required_context entries (focus population) | 283 | 44 | -239 |
| Entries with empty proposition_ids | 306 | 63 | -243 |

### Export resolution_status (focus population)

| Status | Before | After | Delta |
| --- | ---: | ---: | ---: |
| ambiguous | 180 | 0 | -180 |
| external_reference | 23 | 17 | -6 |
| resolved | 108 | 248 | +140 |
| unresolved | 283 | 44 | -239 |

### Workbench resolution mode (focus population, per required_context entry)

| Mode | Before | After | Delta |
| --- | ---: | ---: | ---: |
| exact | 223 | 112 | -111 |
| container | 280 | 121 | -159 |
| partial | 0 | 0 | +0 |
| unresolved | 68 | 59 | -9 |
| external | 23 | 17 | -6 |
| ambiguous | 0 | 0 | +0 |

## 2. Composition opacity

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Total opaque statements | 665 | 732 | +67 |
| Trace-reviewable opaque statements | 248 | 480 | +232 |
| Trace-blocked opaque statements | 417 | 252 | -165 |
| Context-dependent trace-blocked (subset) | 301 | 234 | -67 |
| Trace-reviewable rate (of opaque) | 37.3% | 65.6% | |

### Opacity trigger resolution (context_dependent)

| Trigger | Opaque before | Reviewable before | Opaque after | Reviewable after |
| --- | ---: | ---: | ---: | ---: |
| context_dependent | 413 | 112 | 413 | 179 |

## 3. Reviewability blockers

| Blocker | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Unresolved internal references | 42 | 42 | +0 |
| External references | 36 | 36 | +0 |
| Missing propositions | 58 | 69 | +11 |
| Apparent overreach | 168 | 471 | +303 |
| Evidence corruption | 144 | 145 | +1 |
| Composition opacity | 665 | 732 | +67 |

## 4. Specific improvements

### Statements: trace-blocked → trace-reviewable (12 sampled of 159 total)

| Statement ID | Statement (truncated) |
| --- | --- |
| `lawstmt:01a80b20889c33f1` | SEPA shall withdraw, extend, or modify a notice under regulation 8(5) if directed to do so by the Scottish Ministers under regulation 9(5). |
| `lawstmt:030a536762dc5059` | A silo must either comply with the provisions of Schedule 1, or be designed and constructed in accordance with BS 5502 (parts relating to Cylindrical Forage To… |
| `lawstmt:040001c967a640a6` | Before 30th April each year, the occupier of a holding with livestock must record for the previous storage period the number of animals in a building or hardst… |
| `lawstmt:04c567b56533e739` | The amount of nitrogen produced by livestock must be calculated in accordance with Schedule 1. |
| `lawstmt:069650b20d51ed36` | A person who has custody or control of silage being made or stored must ensure the silage is kept in a silo satisfying the requirements of Schedule 1, or compr… |
| `lawstmt:0867d90aaf67b9f4` | A report under regulation 40(2)(a) must include an assessment of the extent to which the objectives of these Regulations are being achieved. |
| `lawstmt:08b5215d220b4a8b` | For permanent grassland, the occupier must comply with the regulation 6(1) obligations each year beginning 1 January before the first spreading of nitrogen fer… |
| `lawstmt:09149c28263e2529` | The occupier must ensure that the total amount of phosphate from manufactured phosphate fertiliser and phosphate from organic manure spread in the growing seas… |
| `lawstmt:0d2057b4d8e66d5e` | Any reference in regulation 7(1) to the period stated in a notice means that period as extended if extended under regulation 8(5) or by virtue of regulation 9(… |
| `lawstmt:0d42cdfdf01e29b2` | No person shall have custody or control of fuel oil on a farm unless it is stored in a fuel storage tank or container within a storage area in relation to whic… |
| `lawstmt:0de52d5c9affd1cf` | The occupier must determine the soil phosphorus index for each area of the holding with the same cropping regime, nutrient management regime and soil type by u… |
| `lawstmt:0e17c18d182ab8b5` | A person must not spread organic manure within 10 metres of surface water, except as permitted by regulation 17(2) or 17(4). |

### Top required_context proposition_ids fills

| Statement ID | Locator | Before IDs | After IDs |
| --- | --- | --- | --- |
| `lawstmt:0b1280c161a44bfe` | `schedule 1a` | 0 | prop:4549f7c797b20783, prop:19b70002ac78b4ca, prop:300780b32dd015d2, prop:74bbff993257e70f, prop:abd6e75a5429a226, prop:a0ae7ea9089cc17f, prop:f787cd5e606bcbeb, prop:343d17238308da7f, prop:9b478ae58a5926ff, prop:1b4c048e3fd291b8, prop:9c213e3c57d91950, prop:fd2c2dcce0827c25, prop:ff0a2d341b98c6d5, prop:2f208db821098f79, prop:6c9d19cbdcfde972, prop:08541c3a4c86f928, prop:c2fe39f2aa8c6291, prop:10499edd269d050c, prop:0b2a5a4d0bd3ef0a, prop:a2c95e74116b7e62, prop:24ede6d8c4f3bffd, prop:89faba74bd026ca2, prop:cd11a73db6cbe404, prop:392a993a68ac43c4, prop:c25d6db533fa158c, prop:e243860c17e9cc7d, prop:655a89adef9e62d7, prop:bdda3d60e6396e7f, prop:8ed9afe5edb57785, prop:592d4dda58fe4527, prop:01874340bd69f309, prop:93afa8015897f599, prop:db63e4fa3a715d3e, prop:e8fdc18aec65be9c, prop:fbb45b04fea83e0a, prop:fdbedbae435e33cb, prop:ef7b0552097c4d4a, prop:5f868ad0850107f1, prop:403c9353e002c550, prop:26709c281c6ffc84, prop:d7408ce314a854d4, prop:c4cf7b2e6942845c, prop:a442ec2d7d659632, prop:17f2a0428dafbca1, prop:4843a6543721015f, prop:ebb0bbe67c51c6ed, prop:6c2e71c0745e54c9, prop:b337f9ec7d6a8a73, prop:615e31ac1b2fbd84, prop:26a5e80a050c8d4f, prop:ff12482f8b2aeb50, prop:0a9fb968f044cf16, prop:a0652c6ba66db1ab, prop:0a52652e919c0e81, prop:fbde19d9d5f5c98e, prop:74a66e958fba4483, prop:442d6fd0a8da1c61, prop:8eb44a972e45c926, prop:9e14e002ace37736, prop:4133ebe27fc764a1, prop:1f5e9f121c8f021e, prop:6e85e95c4731367a, prop:f09880a29f84b8f1 |
| `lawstmt:1397881b2bd0821d` | `schedule 1a` | 0 | prop:4549f7c797b20783, prop:19b70002ac78b4ca, prop:300780b32dd015d2, prop:74bbff993257e70f, prop:abd6e75a5429a226, prop:a0ae7ea9089cc17f, prop:f787cd5e606bcbeb, prop:343d17238308da7f, prop:9b478ae58a5926ff, prop:1b4c048e3fd291b8, prop:9c213e3c57d91950, prop:fd2c2dcce0827c25, prop:ff0a2d341b98c6d5, prop:2f208db821098f79, prop:6c9d19cbdcfde972, prop:08541c3a4c86f928, prop:c2fe39f2aa8c6291, prop:10499edd269d050c, prop:0b2a5a4d0bd3ef0a, prop:a2c95e74116b7e62, prop:24ede6d8c4f3bffd, prop:89faba74bd026ca2, prop:cd11a73db6cbe404, prop:392a993a68ac43c4, prop:c25d6db533fa158c, prop:e243860c17e9cc7d, prop:655a89adef9e62d7, prop:bdda3d60e6396e7f, prop:8ed9afe5edb57785, prop:592d4dda58fe4527, prop:01874340bd69f309, prop:93afa8015897f599, prop:db63e4fa3a715d3e, prop:e8fdc18aec65be9c, prop:fbb45b04fea83e0a, prop:fdbedbae435e33cb, prop:ef7b0552097c4d4a, prop:5f868ad0850107f1, prop:403c9353e002c550, prop:26709c281c6ffc84, prop:d7408ce314a854d4, prop:c4cf7b2e6942845c, prop:a442ec2d7d659632, prop:17f2a0428dafbca1, prop:4843a6543721015f, prop:ebb0bbe67c51c6ed, prop:6c2e71c0745e54c9, prop:b337f9ec7d6a8a73, prop:615e31ac1b2fbd84, prop:26a5e80a050c8d4f, prop:ff12482f8b2aeb50, prop:0a9fb968f044cf16, prop:a0652c6ba66db1ab, prop:0a52652e919c0e81, prop:fbde19d9d5f5c98e, prop:74a66e958fba4483, prop:442d6fd0a8da1c61, prop:8eb44a972e45c926, prop:9e14e002ace37736, prop:4133ebe27fc764a1, prop:1f5e9f121c8f021e, prop:6e85e95c4731367a, prop:f09880a29f84b8f1 |
| `lawstmt:4e0708bb8a53a098` | `schedule 1a` | 0 | prop:4549f7c797b20783, prop:19b70002ac78b4ca, prop:300780b32dd015d2, prop:74bbff993257e70f, prop:abd6e75a5429a226, prop:a0ae7ea9089cc17f, prop:f787cd5e606bcbeb, prop:343d17238308da7f, prop:9b478ae58a5926ff, prop:1b4c048e3fd291b8, prop:9c213e3c57d91950, prop:fd2c2dcce0827c25, prop:ff0a2d341b98c6d5, prop:2f208db821098f79, prop:6c9d19cbdcfde972, prop:08541c3a4c86f928, prop:c2fe39f2aa8c6291, prop:10499edd269d050c, prop:0b2a5a4d0bd3ef0a, prop:a2c95e74116b7e62, prop:24ede6d8c4f3bffd, prop:89faba74bd026ca2, prop:cd11a73db6cbe404, prop:392a993a68ac43c4, prop:c25d6db533fa158c, prop:e243860c17e9cc7d, prop:655a89adef9e62d7, prop:bdda3d60e6396e7f, prop:8ed9afe5edb57785, prop:592d4dda58fe4527, prop:01874340bd69f309, prop:93afa8015897f599, prop:db63e4fa3a715d3e, prop:e8fdc18aec65be9c, prop:fbb45b04fea83e0a, prop:fdbedbae435e33cb, prop:ef7b0552097c4d4a, prop:5f868ad0850107f1, prop:403c9353e002c550, prop:26709c281c6ffc84, prop:d7408ce314a854d4, prop:c4cf7b2e6942845c, prop:a442ec2d7d659632, prop:17f2a0428dafbca1, prop:4843a6543721015f, prop:ebb0bbe67c51c6ed, prop:6c2e71c0745e54c9, prop:b337f9ec7d6a8a73, prop:615e31ac1b2fbd84, prop:26a5e80a050c8d4f, prop:ff12482f8b2aeb50, prop:0a9fb968f044cf16, prop:a0652c6ba66db1ab, prop:0a52652e919c0e81, prop:fbde19d9d5f5c98e, prop:74a66e958fba4483, prop:442d6fd0a8da1c61, prop:8eb44a972e45c926, prop:9e14e002ace37736, prop:4133ebe27fc764a1, prop:1f5e9f121c8f021e, prop:6e85e95c4731367a, prop:f09880a29f84b8f1 |
| `lawstmt:505812c5e3e5eda1` | `schedule 1a` | 0 | prop:4549f7c797b20783, prop:19b70002ac78b4ca, prop:300780b32dd015d2, prop:74bbff993257e70f, prop:abd6e75a5429a226, prop:a0ae7ea9089cc17f, prop:f787cd5e606bcbeb, prop:343d17238308da7f, prop:9b478ae58a5926ff, prop:1b4c048e3fd291b8, prop:9c213e3c57d91950, prop:fd2c2dcce0827c25, prop:ff0a2d341b98c6d5, prop:2f208db821098f79, prop:6c9d19cbdcfde972, prop:08541c3a4c86f928, prop:c2fe39f2aa8c6291, prop:10499edd269d050c, prop:0b2a5a4d0bd3ef0a, prop:a2c95e74116b7e62, prop:24ede6d8c4f3bffd, prop:89faba74bd026ca2, prop:cd11a73db6cbe404, prop:392a993a68ac43c4, prop:c25d6db533fa158c, prop:e243860c17e9cc7d, prop:655a89adef9e62d7, prop:bdda3d60e6396e7f, prop:8ed9afe5edb57785, prop:592d4dda58fe4527, prop:01874340bd69f309, prop:93afa8015897f599, prop:db63e4fa3a715d3e, prop:e8fdc18aec65be9c, prop:fbb45b04fea83e0a, prop:fdbedbae435e33cb, prop:ef7b0552097c4d4a, prop:5f868ad0850107f1, prop:403c9353e002c550, prop:26709c281c6ffc84, prop:d7408ce314a854d4, prop:c4cf7b2e6942845c, prop:a442ec2d7d659632, prop:17f2a0428dafbca1, prop:4843a6543721015f, prop:ebb0bbe67c51c6ed, prop:6c2e71c0745e54c9, prop:b337f9ec7d6a8a73, prop:615e31ac1b2fbd84, prop:26a5e80a050c8d4f, prop:ff12482f8b2aeb50, prop:0a9fb968f044cf16, prop:a0652c6ba66db1ab, prop:0a52652e919c0e81, prop:fbde19d9d5f5c98e, prop:74a66e958fba4483, prop:442d6fd0a8da1c61, prop:8eb44a972e45c926, prop:9e14e002ace37736, prop:4133ebe27fc764a1, prop:1f5e9f121c8f021e, prop:6e85e95c4731367a, prop:f09880a29f84b8f1 |
| `lawstmt:6a6197469046b8f2` | `schedule 1a` | 0 | prop:4549f7c797b20783, prop:19b70002ac78b4ca, prop:300780b32dd015d2, prop:74bbff993257e70f, prop:abd6e75a5429a226, prop:a0ae7ea9089cc17f, prop:f787cd5e606bcbeb, prop:343d17238308da7f, prop:9b478ae58a5926ff, prop:1b4c048e3fd291b8, prop:9c213e3c57d91950, prop:fd2c2dcce0827c25, prop:ff0a2d341b98c6d5, prop:2f208db821098f79, prop:6c9d19cbdcfde972, prop:08541c3a4c86f928, prop:c2fe39f2aa8c6291, prop:10499edd269d050c, prop:0b2a5a4d0bd3ef0a, prop:a2c95e74116b7e62, prop:24ede6d8c4f3bffd, prop:89faba74bd026ca2, prop:cd11a73db6cbe404, prop:392a993a68ac43c4, prop:c25d6db533fa158c, prop:e243860c17e9cc7d, prop:655a89adef9e62d7, prop:bdda3d60e6396e7f, prop:8ed9afe5edb57785, prop:592d4dda58fe4527, prop:01874340bd69f309, prop:93afa8015897f599, prop:db63e4fa3a715d3e, prop:e8fdc18aec65be9c, prop:fbb45b04fea83e0a, prop:fdbedbae435e33cb, prop:ef7b0552097c4d4a, prop:5f868ad0850107f1, prop:403c9353e002c550, prop:26709c281c6ffc84, prop:d7408ce314a854d4, prop:c4cf7b2e6942845c, prop:a442ec2d7d659632, prop:17f2a0428dafbca1, prop:4843a6543721015f, prop:ebb0bbe67c51c6ed, prop:6c2e71c0745e54c9, prop:b337f9ec7d6a8a73, prop:615e31ac1b2fbd84, prop:26a5e80a050c8d4f, prop:ff12482f8b2aeb50, prop:0a9fb968f044cf16, prop:a0652c6ba66db1ab, prop:0a52652e919c0e81, prop:fbde19d9d5f5c98e, prop:74a66e958fba4483, prop:442d6fd0a8da1c61, prop:8eb44a972e45c926, prop:9e14e002ace37736, prop:4133ebe27fc764a1, prop:1f5e9f121c8f021e, prop:6e85e95c4731367a, prop:f09880a29f84b8f1 |
| `lawstmt:8a723a065163abbe` | `schedule 1a` | 0 | prop:4549f7c797b20783, prop:19b70002ac78b4ca, prop:300780b32dd015d2, prop:74bbff993257e70f, prop:abd6e75a5429a226, prop:a0ae7ea9089cc17f, prop:f787cd5e606bcbeb, prop:343d17238308da7f, prop:9b478ae58a5926ff, prop:1b4c048e3fd291b8, prop:9c213e3c57d91950, prop:fd2c2dcce0827c25, prop:ff0a2d341b98c6d5, prop:2f208db821098f79, prop:6c9d19cbdcfde972, prop:08541c3a4c86f928, prop:c2fe39f2aa8c6291, prop:10499edd269d050c, prop:0b2a5a4d0bd3ef0a, prop:a2c95e74116b7e62, prop:24ede6d8c4f3bffd, prop:89faba74bd026ca2, prop:cd11a73db6cbe404, prop:392a993a68ac43c4, prop:c25d6db533fa158c, prop:e243860c17e9cc7d, prop:655a89adef9e62d7, prop:bdda3d60e6396e7f, prop:8ed9afe5edb57785, prop:592d4dda58fe4527, prop:01874340bd69f309, prop:93afa8015897f599, prop:db63e4fa3a715d3e, prop:e8fdc18aec65be9c, prop:fbb45b04fea83e0a, prop:fdbedbae435e33cb, prop:ef7b0552097c4d4a, prop:5f868ad0850107f1, prop:403c9353e002c550, prop:26709c281c6ffc84, prop:d7408ce314a854d4, prop:c4cf7b2e6942845c, prop:a442ec2d7d659632, prop:17f2a0428dafbca1, prop:4843a6543721015f, prop:ebb0bbe67c51c6ed, prop:6c2e71c0745e54c9, prop:b337f9ec7d6a8a73, prop:615e31ac1b2fbd84, prop:26a5e80a050c8d4f, prop:ff12482f8b2aeb50, prop:0a9fb968f044cf16, prop:a0652c6ba66db1ab, prop:0a52652e919c0e81, prop:fbde19d9d5f5c98e, prop:74a66e958fba4483, prop:442d6fd0a8da1c61, prop:8eb44a972e45c926, prop:9e14e002ace37736, prop:4133ebe27fc764a1, prop:1f5e9f121c8f021e, prop:6e85e95c4731367a, prop:f09880a29f84b8f1 |
| `lawstmt:8ec10ca48a821fc3` | `schedule 1a` | 0 | prop:4549f7c797b20783, prop:19b70002ac78b4ca, prop:300780b32dd015d2, prop:74bbff993257e70f, prop:abd6e75a5429a226, prop:a0ae7ea9089cc17f, prop:f787cd5e606bcbeb, prop:343d17238308da7f, prop:9b478ae58a5926ff, prop:1b4c048e3fd291b8, prop:9c213e3c57d91950, prop:fd2c2dcce0827c25, prop:ff0a2d341b98c6d5, prop:2f208db821098f79, prop:6c9d19cbdcfde972, prop:08541c3a4c86f928, prop:c2fe39f2aa8c6291, prop:10499edd269d050c, prop:0b2a5a4d0bd3ef0a, prop:a2c95e74116b7e62, prop:24ede6d8c4f3bffd, prop:89faba74bd026ca2, prop:cd11a73db6cbe404, prop:392a993a68ac43c4, prop:c25d6db533fa158c, prop:e243860c17e9cc7d, prop:655a89adef9e62d7, prop:bdda3d60e6396e7f, prop:8ed9afe5edb57785, prop:592d4dda58fe4527, prop:01874340bd69f309, prop:93afa8015897f599, prop:db63e4fa3a715d3e, prop:e8fdc18aec65be9c, prop:fbb45b04fea83e0a, prop:fdbedbae435e33cb, prop:ef7b0552097c4d4a, prop:5f868ad0850107f1, prop:403c9353e002c550, prop:26709c281c6ffc84, prop:d7408ce314a854d4, prop:c4cf7b2e6942845c, prop:a442ec2d7d659632, prop:17f2a0428dafbca1, prop:4843a6543721015f, prop:ebb0bbe67c51c6ed, prop:6c2e71c0745e54c9, prop:b337f9ec7d6a8a73, prop:615e31ac1b2fbd84, prop:26a5e80a050c8d4f, prop:ff12482f8b2aeb50, prop:0a9fb968f044cf16, prop:a0652c6ba66db1ab, prop:0a52652e919c0e81, prop:fbde19d9d5f5c98e, prop:74a66e958fba4483, prop:442d6fd0a8da1c61, prop:8eb44a972e45c926, prop:9e14e002ace37736, prop:4133ebe27fc764a1, prop:1f5e9f121c8f021e, prop:6e85e95c4731367a, prop:f09880a29f84b8f1 |
| `lawstmt:c54cfde4cb205245` | `schedule 1a` | 0 | prop:4549f7c797b20783, prop:19b70002ac78b4ca, prop:300780b32dd015d2, prop:74bbff993257e70f, prop:abd6e75a5429a226, prop:a0ae7ea9089cc17f, prop:f787cd5e606bcbeb, prop:343d17238308da7f, prop:9b478ae58a5926ff, prop:1b4c048e3fd291b8, prop:9c213e3c57d91950, prop:fd2c2dcce0827c25, prop:ff0a2d341b98c6d5, prop:2f208db821098f79, prop:6c9d19cbdcfde972, prop:08541c3a4c86f928, prop:c2fe39f2aa8c6291, prop:10499edd269d050c, prop:0b2a5a4d0bd3ef0a, prop:a2c95e74116b7e62, prop:24ede6d8c4f3bffd, prop:89faba74bd026ca2, prop:cd11a73db6cbe404, prop:392a993a68ac43c4, prop:c25d6db533fa158c, prop:e243860c17e9cc7d, prop:655a89adef9e62d7, prop:bdda3d60e6396e7f, prop:8ed9afe5edb57785, prop:592d4dda58fe4527, prop:01874340bd69f309, prop:93afa8015897f599, prop:db63e4fa3a715d3e, prop:e8fdc18aec65be9c, prop:fbb45b04fea83e0a, prop:fdbedbae435e33cb, prop:ef7b0552097c4d4a, prop:5f868ad0850107f1, prop:403c9353e002c550, prop:26709c281c6ffc84, prop:d7408ce314a854d4, prop:c4cf7b2e6942845c, prop:a442ec2d7d659632, prop:17f2a0428dafbca1, prop:4843a6543721015f, prop:ebb0bbe67c51c6ed, prop:6c2e71c0745e54c9, prop:b337f9ec7d6a8a73, prop:615e31ac1b2fbd84, prop:26a5e80a050c8d4f, prop:ff12482f8b2aeb50, prop:0a9fb968f044cf16, prop:a0652c6ba66db1ab, prop:0a52652e919c0e81, prop:fbde19d9d5f5c98e, prop:74a66e958fba4483, prop:442d6fd0a8da1c61, prop:8eb44a972e45c926, prop:9e14e002ace37736, prop:4133ebe27fc764a1, prop:1f5e9f121c8f021e, prop:6e85e95c4731367a, prop:f09880a29f84b8f1 |
| `lawstmt:8004f8b208d38a34` | `schedule 3` | 0 | prop:2025e3b7fc67b3f6, prop:a2fc5c05b895d085, prop:5db2a72552ab9739, prop:2852a90999eab41a, prop:8ccd9d6fac9dd78b, prop:c8b45616f9f6ecfc, prop:f6d67f8d0aaf9305, prop:9f9a73758310fd56, prop:03779f09b2cdbb3a, prop:56ba1ec3fca9dc29, prop:e3c274a1d888e78a, prop:da51ad1ae66b604b, prop:01a4ef3180994b99, prop:4104ca70389b2569, prop:053c1b3704ee9fff, prop:d5a567f8e4951603, prop:d95e1ee61e72f7c9, prop:4657a0724c839e1b, prop:37c9fd9acdf96ae1, prop:f8753f3fdd937775, prop:ca7c6ef3554706c3, prop:808a8fcae058812f, prop:ca197fc7cad8eb8b, prop:524d5b0e5127a815, prop:d974876003e7ba08, prop:b7a8e546951d2140, prop:8cd5c9fcf2b8aca5, prop:e27401870caab0d2, prop:9f9e046b4b8d90e7, prop:80fc3d27f5442283, prop:95f0a85735187cbc, prop:7a5e903bb1dd3971, prop:4a1f56f72bfa11d6, prop:282294581b2cc1cb, prop:ea105ebb0b2a6e9e, prop:976cefd54d332a46, prop:e2e92c34e666a3d8, prop:1300d77fd141d739, prop:4bfa571042be5c56, prop:cae1ec62a09cd8a1, prop:5b1b7587ffb65509, prop:300fe8f07465713e, prop:852039953a4d53d2, prop:fa23c6fbef815d32, prop:0d31056416253e83, prop:5fcd6ee95eeb2c26, prop:1a601253ea186920, prop:357613eb4adac2a8, prop:e877c3c8c94ece57, prop:ab7bbb6ab4e44c2b, prop:9acfce7f5b0766fc, prop:f9f592761c61e936, prop:72ca09fb5f00f206 |
| `lawstmt:938e70e25de7c8f3` | `schedule 3` | 0 | prop:2025e3b7fc67b3f6, prop:a2fc5c05b895d085, prop:5db2a72552ab9739, prop:2852a90999eab41a, prop:8ccd9d6fac9dd78b, prop:c8b45616f9f6ecfc, prop:f6d67f8d0aaf9305, prop:9f9a73758310fd56, prop:03779f09b2cdbb3a, prop:56ba1ec3fca9dc29, prop:e3c274a1d888e78a, prop:da51ad1ae66b604b, prop:01a4ef3180994b99, prop:4104ca70389b2569, prop:053c1b3704ee9fff, prop:d5a567f8e4951603, prop:d95e1ee61e72f7c9, prop:4657a0724c839e1b, prop:37c9fd9acdf96ae1, prop:f8753f3fdd937775, prop:ca7c6ef3554706c3, prop:808a8fcae058812f, prop:ca197fc7cad8eb8b, prop:524d5b0e5127a815, prop:d974876003e7ba08, prop:b7a8e546951d2140, prop:8cd5c9fcf2b8aca5, prop:e27401870caab0d2, prop:9f9e046b4b8d90e7, prop:80fc3d27f5442283, prop:95f0a85735187cbc, prop:7a5e903bb1dd3971, prop:4a1f56f72bfa11d6, prop:282294581b2cc1cb, prop:ea105ebb0b2a6e9e, prop:976cefd54d332a46, prop:e2e92c34e666a3d8, prop:1300d77fd141d739, prop:4bfa571042be5c56, prop:cae1ec62a09cd8a1, prop:5b1b7587ffb65509, prop:300fe8f07465713e, prop:852039953a4d53d2, prop:fa23c6fbef815d32, prop:0d31056416253e83, prop:5fcd6ee95eeb2c26, prop:1a601253ea186920, prop:357613eb4adac2a8, prop:e877c3c8c94ece57, prop:ab7bbb6ab4e44c2b, prop:9acfce7f5b0766fc, prop:f9f592761c61e936, prop:72ca09fb5f00f206 |

### Context-dependent trace-blocked reduction

- Before: **301** trace-blocked of **413** context-dependent (72.9%).
- After: **234** trace-blocked of **413** context-dependent (56.7%).
- Net change: **-67** trace-blocked statements.

## 5. Recommendation — next highest-leverage fix

**Composition transparency / selective context incorporation** remains the top lever after context closure convergence:

1. **234** context-dependent statements are still trace-blocked despite improved locator closure — effective-law statement text remains verbatim core proposition text (413/413 match core).
2. **168** statements have material incorporation gaps (resolved context not surfaced in statement text).
3. Residual **44** unresolved locators are mostly structural containers (`schedule 5`, `article 27`, cross-instrument refs) — lower leverage than inline composition for the blocked population.

**Suggested next prompt:** emit composition traces in export + inline selectively for material `required_context` (Prompt 83 recommendation), targeting trace-blocked context-dependent statements with resolved context propositions.

## Reproduction

```bash
cd law-proposition-extractor
uv run --package law-proposition-extractor-pipeline python scripts/generate_post_context_closure_impact_report.py
```

Refresh subsidiary reports:

```bash
uv run --package law-proposition-extractor-pipeline python scripts/generate_export_context_closure_report.py
uv run --package law-proposition-extractor-pipeline python scripts/generate_composition_trace_report.py
uv run --package law-proposition-extractor-pipeline python scripts/generate_context_dependent_construction_report.py
uv run --package law-proposition-extractor-pipeline python scripts/generate_reviewability_blockers_report.py
```
