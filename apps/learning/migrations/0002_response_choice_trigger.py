from django.db import migrations


CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION learning_validate_response_choice()
RETURNS trigger AS $$
DECLARE
    item_question uuid;
    choice_question uuid;
    response_session_type varchar;
BEGIN
    SELECT si.question_id, s.session_type
    INTO item_question, response_session_type
    FROM learning_session_item si
    JOIN learning_session s ON s.id = si.session_id
    WHERE si.id = NEW.session_item_id;

    SELECT question_id INTO choice_question
    FROM curriculum_question_choice
    WHERE id = NEW.selected_choice_id;

    IF item_question IS DISTINCT FROM choice_question THEN
        RAISE EXCEPTION 'selected choice must belong to the session item question'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.hint_used AND response_session_type <> 'foundational' THEN
        RAISE EXCEPTION 'hints may only be used in foundational sessions'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = """
CREATE TRIGGER learning_response_choice_check
BEFORE INSERT OR UPDATE OF session_item_id, selected_choice_id, hint_used
ON learning_response
FOR EACH ROW EXECUTE FUNCTION learning_validate_response_choice();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS learning_response_choice_check ON learning_response;
"""

DROP_FUNCTION = """
DROP FUNCTION IF EXISTS learning_validate_response_choice();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0002_question_video_cue_trigger"),
        ("learning", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(CREATE_FUNCTION, reverse_sql=DROP_FUNCTION),
        migrations.RunSQL(CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
