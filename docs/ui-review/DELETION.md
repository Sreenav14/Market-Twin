# Test, target, and application deletion

The UI uses **Tests**, **New test**, and **testing goals**. The sign-in screen now leads with "Build an app people want to use." Existing `/runs` URLs and database/API names remain compatible.

Owners and administrators can delete from the Tests, application tests, Targets, and Applications lists, and from individual test, target, and application pages. The confirmation dialog describes the item and consequences; Cancel receives initial focus. Server errors keep the dialog open and the row visible. Successful requests refresh the lists.

The Control API implements:

- `DELETE /api/v1/test-runs/{id}`
- `DELETE /api/v1/targets/{id}`
- `DELETE /api/v1/applications/{id}`

These perform SQLAlchemy database deletes inside a transaction. They do not merely hide rows in the frontend. Membership and owner/admin permissions are checked server-side. Row locking and foreign keys protect concurrent dependencies.

Delete tests first, then their targets, then the application. Planning, queued, and running tests are blocked. Active journeys and pending/generating evaluation also block deletion. Deleting a test cascades to its related database results, events, and evidence metadata through the existing foreign keys. Object-storage files have separate retention and are not deleted by these endpoints; the confirmation explicitly states this.

No schema migration is required. Restart the Control API if it is not running with reload enabled.

Backend validation: 44 tests passed, including authorization, dependency conflicts, active jobs, and successful deletion. An additional opt-in PostgreSQL test passed against the local database, verifying test/report/event cascades and target/application removal. It uses isolated fixture records inside an outer transaction that is rolled back.

To repeat the database check from the repository root in PowerShell:

```powershell
$env:MARKETTWIN_TEST_DATABASE = '1'
uv run pytest services/control-api/tests/test_lifecycle_database.py -q
Remove-Item Env:MARKETTWIN_TEST_DATABASE
```
