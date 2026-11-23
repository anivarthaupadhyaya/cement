"""SQL for the trigger-based audit log, shared by migrations.

Every audited table gets an AFTER INSERT/UPDATE/DELETE trigger that writes the old and new row
as JSONB, plus the acting user taken from the transaction-local setting `app.user_id`
(set per request in `app.api.deps`). Sensitive columns are stripped.
"""

CREATE_AUDIT_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_row_change() RETURNS trigger AS $$
DECLARE
    v_old jsonb;
    v_new jsonb;
    v_user int;
BEGIN
    v_user := NULLIF(current_setting('app.user_id', true), '')::int;
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        v_old := to_jsonb(OLD) - 'password_hash';
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        v_new := to_jsonb(NEW) - 'password_hash';
    END IF;
    IF TG_OP = 'UPDATE' AND v_old - 'updated_at' = v_new - 'updated_at' THEN
        RETURN NULL;  -- nothing meaningful changed
    END IF;
    INSERT INTO audit_log (table_name, record_id, action, user_id, old_data, new_data)
    VALUES (TG_TABLE_NAME, COALESCE(v_new, v_old) ->> 'id', TG_OP, v_user, v_old, v_new);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_AUDIT_GUARD = """
CREATE OR REPLACE FUNCTION audit_log_readonly() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_log_readonly
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION audit_log_readonly();
"""


def attach_audit_sql(table: str) -> str:
    return (
        f"CREATE TRIGGER trg_audit_{table} AFTER INSERT OR UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION audit_row_change();"
    )


def detach_audit_sql(table: str) -> str:
    return f"DROP TRIGGER IF EXISTS trg_audit_{table} ON {table};"
