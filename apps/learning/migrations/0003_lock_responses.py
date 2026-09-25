from django.db import migrations


CREATE_RESPONSE_LOCK = """
CREATE OR REPLACE FUNCTION learning_reject_response_change()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Submitted responses are locked and cannot be changed.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER learning_response_lock
BEFORE UPDATE OR DELETE
ON learning_response
FOR EACH ROW EXECUTE FUNCTION learning_reject_response_change();
"""

DROP_RESPONSE_LOCK = """
DROP TRIGGER IF EXISTS learning_response_lock ON learning_response;
DROP FUNCTION IF EXISTS learning_reject_response_change();
"""


class Migration(migrations.Migration):
    dependencies = [("learning", "0002_response_choice_trigger")]

    operations = [
        migrations.RunSQL(CREATE_RESPONSE_LOCK, DROP_RESPONSE_LOCK),
    ]
