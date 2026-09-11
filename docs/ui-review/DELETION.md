# Test, target, and application deletion

The product language is **Test**, **New test**, and **testing goal**. Existing `/runs` URLs and the persisted `study_brief` field remain internal V1 compatibility identifiers.

Owners and administrators can delete draft Tests, unused Targets, and empty Applications. The confirmation dialog describes the item and consequences; Cancel receives initial focus. Server errors keep the dialog open and the row visible. Successful requests refresh only the relevant frontend data.

The Control API implements:

- `DELETE /api/v1/test-runs/{id}`
- `DELETE /api/v1/targets/{id}`
- `DELETE /api/v1/applications/{id}`

These perform SQLAlchemy database deletes inside a transaction. They do not merely hide rows in the frontend. Membership and owner/admin permissions are checked server-side. Row locking and foreign keys protect concurrent dependencies.

## V1 deletion policy

A Test can be hard-deleted **only while it is an unused `draft`**. If planning has persisted a Journey, or if the Test has moved beyond `draft`, deletion is rejected. Started, failed, cancelled, and completed Tests are retained so their execution history, results, and evidence remain auditable.

Targets can be deleted only after all of their Tests have been removed. Applications can be deleted only after all Tests and Targets have been removed.

This deliberately avoids the previous unsafe behavior where database evidence metadata could be deleted while screenshot, trace, or log objects remained in S3/MinIO. A future retention/archive feature can introduce coordinated object-store cleanup if product requirements call for deleting executed Tests.

No schema migration is required.

## Validation

Run the Control API lifecycle tests:

```powershell
uv run pytest services/control-api/tests/test_lifecycle_api.py -q
```

To repeat the opt-in database check from the repository root in PowerShell:

```powershell
$env:MARKETTWIN_TEST_DATABASE = '1'
uv run pytest services/control-api/tests/test_lifecycle_database.py -q
Remove-Item Env:MARKETTWIN_TEST_DATABASE
```

The database test verifies that a draft Test blocks deletion of its parent Target, then can be removed before deleting the Target and Application. It uses isolated fixture records inside an outer transaction that is rolled back.
