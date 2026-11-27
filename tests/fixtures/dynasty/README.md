# Dynasty frozen test inputs

Dynasty DM9000 1.0.4 (5), `com.richmat.dynasty`, accepted row189 independent
FULL static recovery. Original queue accounting remains DELTA; no baseline
comparison. Hardware is unverified.

These fixtures are read by `tests/test_dynasty.py` and `tests/richmat_vectors.py`:

- `controls.json.gz`: all 8,144 frozen declarations, keyed by layout and node.
- `wire.json.gz`: all 19,440 literal catalog/mode results, including byte proof
  for excluded diagnostic/speech paths. It does not enable those paths.
- `vectors.json`: the report's unchanged 39 vectors. Production matches 35;
  network administration and motor-mapping programming (four vectors) remain
  excluded. The original report reproducer verifies all 39 externally.
- `alarm-functions.json`: the accepted alarm branch map, checked independently
  against the runtime combination table.

No generator is checked in. The app catalog was mechanically converted from
all 558 retained resource XML files after verifying their accepted hashes and
reconciling every frozen declaration; resource IDs and ancestor visibility are
retained, without inferring physical actuator or side meanings.

Original report input SHA-256:

- `resource-buttons.json`: `8a5831b94af3c454aab149b4a43cf3f4566dd576850ef7ad6bdb972b605b9040`
- `variant-inventory.json`: `318d267525680e65722155907fa74d1c86fbbdebf30039a285d4579baef66f91`
- `catalog-commands.json`: `f70aad0296666392328382bae55d4789c8f822225df575c45c1300142b9899b7`
- `vectors.json`: `eb846c8c0613f9d46ac1da73d8e95b8a4012b4af5d85aca195e18e94a28feb45`
- `analysis.json`: `6629529afa2616c664f1781f24850d5f211eb7a4d2541703423e636e9a64c845`
