"""Preserve request ownership when a shared browser Room changes execution."""

import sqlalchemy as sa
from alembic import op

revision = "d2a718c40e91"
down_revision = "4f1289fb7f9c"
branch_labels = None
depends_on = None

TABLES = ("human_action_requests", "pause_requests", "execution_suspensions")


def replace_constraints(*, historical: bool) -> None:
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        for fk in inspector.get_foreign_keys(table, schema="execution"):
            if fk["constrained_columns"] == ["execution_id", "browser_session_id"]:
                op.drop_constraint(fk["name"], table, schema="execution", type_="foreignkey")
                op.create_foreign_key(fk["name"], table,
                    "browser_execution_bindings" if historical else "browser_sessions",
                    ["execution_id", "browser_session_id"],
                    ["execution_id", "browser_session_id" if historical else "id"],
                    source_schema="execution", referent_schema="execution", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table("browser_execution_bindings",
        sa.Column("execution_id", sa.Uuid(), primary_key=True),
        sa.Column("browser_session_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(["execution_id"], ["execution.agent_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["browser_session_id"], ["execution.browser_sessions.id"], ondelete="CASCADE"),
        schema="execution")
    op.execute("INSERT INTO execution.browser_execution_bindings SELECT execution_id,id FROM execution.browser_sessions")
    op.execute("""CREATE FUNCTION execution.remember_browser_execution_binding() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          INSERT INTO execution.browser_execution_bindings(execution_id,browser_session_id)
          VALUES (NEW.execution_id,NEW.id) ON CONFLICT DO NOTHING;
          RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER remember_browser_execution_binding
        AFTER INSERT OR UPDATE OF execution_id ON execution.browser_sessions
        FOR EACH ROW EXECUTE FUNCTION execution.remember_browser_execution_binding()""")
    replace_constraints(historical=True)
    op.execute("""CREATE FUNCTION execution.enforce_active_browser_binding() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.status IN ('pending','leased','requested','paused','resume_requested','waiting','ready') THEN
            PERFORM 1 FROM execution.browser_sessions
              WHERE id=NEW.browser_session_id AND execution_id=NEW.execution_id FOR KEY SHARE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Active request must match current browser owner' USING ERRCODE='23503'; END IF;
          END IF;
          RETURN NEW;
        END $$""")
    for table in TABLES:
        op.execute(f"""CREATE TRIGGER enforce_active_browser_binding BEFORE INSERT OR UPDATE ON execution.{table}
            FOR EACH ROW EXECUTE FUNCTION execution.enforce_active_browser_binding()""")
    op.execute("""CREATE FUNCTION execution.guard_browser_rebind() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF OLD.execution_id IS DISTINCT FROM NEW.execution_id AND (
          EXISTS(SELECT 1 FROM execution.human_action_requests WHERE browser_session_id=OLD.id AND status IN ('pending','leased')) OR
          EXISTS(SELECT 1 FROM execution.pause_requests WHERE browser_session_id=OLD.id AND status IN ('requested','paused','resume_requested')) OR
          EXISTS(SELECT 1 FROM execution.execution_suspensions WHERE browser_session_id=OLD.id AND status IN ('waiting','ready'))
        ) THEN RAISE EXCEPTION 'Cannot rebind browser with active assistance' USING ERRCODE='23503'; END IF;
        RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER guard_browser_rebind BEFORE UPDATE OF execution_id ON execution.browser_sessions
        FOR EACH ROW EXECUTE FUNCTION execution.guard_browser_rebind()""")


def downgrade() -> None:
    for table in TABLES:
        mismatch = op.get_bind().execute(sa.text(f"""SELECT EXISTS (
            SELECT 1 FROM execution.{table} r JOIN execution.browser_sessions b ON b.id=r.browser_session_id
            WHERE r.execution_id<>b.execution_id)""")).scalar()
        if mismatch:
            raise RuntimeError("Cannot downgrade: retained requests refer to prior Room owners. Preserve their history.")
    replace_constraints(historical=False)
    for table in TABLES:
        op.execute(f"DROP TRIGGER enforce_active_browser_binding ON execution.{table}")
    op.execute("DROP FUNCTION execution.enforce_active_browser_binding()")
    op.execute("DROP TRIGGER guard_browser_rebind ON execution.browser_sessions")
    op.execute("DROP FUNCTION execution.guard_browser_rebind()")
    op.execute("DROP TRIGGER remember_browser_execution_binding ON execution.browser_sessions")
    op.execute("DROP FUNCTION execution.remember_browser_execution_binding()")
    op.drop_table("browser_execution_bindings", schema="execution")
