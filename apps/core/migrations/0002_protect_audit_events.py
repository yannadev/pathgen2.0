from django.db import migrations


CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION core_protect_audit_event()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit events are append-only'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.actor_id IS NOT NULL
       AND NEW.actor_id IS NULL
       AND NEW.id IS NOT DISTINCT FROM OLD.id
       AND NEW.action IS NOT DISTINCT FROM OLD.action
       AND NEW.target_type IS NOT DISTINCT FROM OLD.target_type
       AND NEW.target_id IS NOT DISTINCT FROM OLD.target_id
       AND NEW.target_snapshot_json IS NOT DISTINCT FROM OLD.target_snapshot_json
       AND NEW.reason IS NOT DISTINCT FROM OLD.reason
       AND NEW.metadata_json IS NOT DISTINCT FROM OLD.metadata_json
       AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit events are append-only'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = """
CREATE TRIGGER core_audit_event_append_only
BEFORE UPDATE OR DELETE ON core_audit_event
FOR EACH ROW EXECUTE FUNCTION core_protect_audit_event();
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS core_audit_event_append_only ON core_audit_event;"
DROP_FUNCTION = "DROP FUNCTION IF EXISTS core_protect_audit_event();"


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.RunSQL(CREATE_FUNCTION, reverse_sql=DROP_FUNCTION),
        migrations.RunSQL(CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
