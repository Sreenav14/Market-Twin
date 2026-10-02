# Source Asset boundary — Step 4

The ORM boundary lives in `packages/database-python/src/markettwin_database/models/knowledge.py`.
All five knowledge models are exported by the shared model registry so Alembic can discover them.

## Identities and revision pinning

- `ProductBlueprint` owns logical `SourceAsset` records and `BlueprintVersion` records.
- `SourceAsset` identifies a piece of source material. `AssetVersion` records each uploaded revision.
- Composite unique keys and foreign keys bind workspace, blueprint, source and revision IDs together.
  An existing ID from another workspace or blueprint cannot satisfy these foreign keys.
- `BlueprintVersionAsset` selects exactly one revision of a given source per Blueprint Version.
  Different Blueprint Versions can retain different revisions of the same source.
- Deleting a Blueprint Version cascades its pins. Deleting a pinned AssetVersion is restricted,
  preserving the revision used by that Blueprint Version.

## Upload and ingestion metadata

AssetVersion stores the original filename, independently declared and detected content types,
storage provider (`s3` or `minio`), bucket, object key, byte size, SHA-256, ingestion status,
status message, creator and timestamps. Storage locations and per-source version numbers are unique;
SHA-256 is deliberately not unique, permitting reuse of identical bytes.
Versions must be positive, sizes nonnegative, and statuses must belong to the V1 ingestion lifecycle.

Pins contain at least one supported role, a required/optional flag (required by default),
and paired role-confirmation user/time fields. These fields support later synthesis and approval;
the model step does not implement MIME detection, ingestion, or approval enforcement.

## Verification and deployment scope

Regression checks cover PostgreSQL DDL compilation, workspace/blueprint/source mismatches,
duplicate pins, role validation (including null elements), partial confirmations, revision and
storage uniqueness, repeated SHA-256 values, differing declared/detected MIME values, large byte
sizes, defaults, historical pins and cascade/restrict behavior.

```powershell
$env:MARKETTWIN_TEST_DATABASE = '1'
.venv\Scripts\python.exe -m pytest packages/database-python/tests/test_knowledge_models.py -q -p no:cacheprovider
```

The database check uses unique translated schemas and rolls back all DDL and data.
Step 4 updates and verifies ORM definitions; no Alembic migration is generated or applied here.
The existing database still needs a migration before these tables can be used by the application.
