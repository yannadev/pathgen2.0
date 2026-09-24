from django.db import migrations


CREATE_EVENT_FUNCTION = """
CREATE OR REPLACE FUNCTION adaptive_validate_mastery_event_scope()
RETURNS trigger AS $$
DECLARE
    response_session_type varchar;
    response_skill uuid;
    response_hint_used boolean;
    mastery_skill uuid;
BEGIN
    SELECT s.session_type, q.skill_id, r.hint_used
    INTO response_session_type, response_skill, response_hint_used
    FROM learning_response r
    JOIN learning_session_item si ON si.id = r.session_item_id
    JOIN learning_session s ON s.id = si.session_id
    JOIN curriculum_question q ON q.id = si.question_id
    WHERE r.id = NEW.response_id;

    SELECT skill_id INTO mastery_skill
    FROM adaptive_skill_mastery
    WHERE id = NEW.mastery_id;

    IF response_session_type = 'posttest' THEN
        RAISE EXCEPTION 'post-test responses cannot create mastery events'
            USING ERRCODE = '23514';
    END IF;
    IF response_skill IS DISTINCT FROM mastery_skill THEN
        RAISE EXCEPTION 'mastery event skill must match the response question skill'
            USING ERRCODE = '23514';
    END IF;
    IF response_hint_used AND (
        NEW.p_after_observation IS NOT NULL OR NOT NEW.learning_transition_applied
    ) THEN
        RAISE EXCEPTION 'hinted mastery events must be transition-only'
            USING ERRCODE = '23514';
    END IF;
    IF NOT response_hint_used AND NEW.p_after_observation IS NULL THEN
        RAISE EXCEPTION 'unhinted mastery events require an observation posterior'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_EVENT_TRIGGER = """
CREATE TRIGGER adaptive_mastery_event_scope_check
BEFORE INSERT OR UPDATE OF mastery_id, response_id
ON adaptive_mastery_event
FOR EACH ROW EXECUTE FUNCTION adaptive_validate_mastery_event_scope();
"""

CREATE_DECISION_FUNCTION = """
CREATE OR REPLACE FUNCTION adaptive_validate_decision_session()
RETURNS trigger AS $$
DECLARE
    routed_type varchar;
    routed_status varchar;
BEGIN
    SELECT session_type, status INTO routed_type, routed_status
    FROM learning_session
    WHERE id = NEW.session_id;

    IF routed_type NOT IN ('regular', 'additional', 'foundational')
       OR routed_status NOT IN ('submitted', 'completed') THEN
        RAISE EXCEPTION 'decision requires an eligible submitted or completed exercise session'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_DECISION_TRIGGER = """
CREATE TRIGGER adaptive_decision_session_check
BEFORE INSERT OR UPDATE OF session_id
ON adaptive_decision
FOR EACH ROW EXECUTE FUNCTION adaptive_validate_decision_session();
"""

CREATE_TARGET_FUNCTION = """
CREATE OR REPLACE FUNCTION adaptive_validate_target_skill_lesson()
RETURNS trigger AS $$
DECLARE
    routed_lesson uuid;
BEGIN
    SELECT s.lesson_id INTO routed_lesson
    FROM adaptive_decision d
    JOIN learning_session s ON s.id = d.session_id
    WHERE d.id = NEW.decision_id;

    IF NOT EXISTS (
        SELECT 1 FROM curriculum_lesson_skill ls
        WHERE ls.lesson_id = routed_lesson AND ls.skill_id = NEW.skill_id
    ) THEN
        RAISE EXCEPTION 'decision target skill must belong to the session lesson'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TARGET_TRIGGER = """
CREATE TRIGGER adaptive_target_skill_lesson_check
BEFORE INSERT OR UPDATE OF decision_id, skill_id
ON adaptive_decision_target_skill
FOR EACH ROW EXECUTE FUNCTION adaptive_validate_target_skill_lesson();
"""

DROP_TARGET_TRIGGER = "DROP TRIGGER IF EXISTS adaptive_target_skill_lesson_check ON adaptive_decision_target_skill;"
DROP_TARGET_FUNCTION = "DROP FUNCTION IF EXISTS adaptive_validate_target_skill_lesson();"
DROP_DECISION_TRIGGER = "DROP TRIGGER IF EXISTS adaptive_decision_session_check ON adaptive_decision;"
DROP_DECISION_FUNCTION = "DROP FUNCTION IF EXISTS adaptive_validate_decision_session();"
DROP_EVENT_TRIGGER = "DROP TRIGGER IF EXISTS adaptive_mastery_event_scope_check ON adaptive_mastery_event;"
DROP_EVENT_FUNCTION = "DROP FUNCTION IF EXISTS adaptive_validate_mastery_event_scope();"


class Migration(migrations.Migration):
    dependencies = [
        ("adaptive", "0001_initial"),
        ("learning", "0002_response_choice_trigger"),
    ]

    operations = [
        migrations.RunSQL(CREATE_EVENT_FUNCTION, reverse_sql=DROP_EVENT_FUNCTION),
        migrations.RunSQL(CREATE_EVENT_TRIGGER, reverse_sql=DROP_EVENT_TRIGGER),
        migrations.RunSQL(CREATE_DECISION_FUNCTION, reverse_sql=DROP_DECISION_FUNCTION),
        migrations.RunSQL(CREATE_DECISION_TRIGGER, reverse_sql=DROP_DECISION_TRIGGER),
        migrations.RunSQL(CREATE_TARGET_FUNCTION, reverse_sql=DROP_TARGET_FUNCTION),
        migrations.RunSQL(CREATE_TARGET_TRIGGER, reverse_sql=DROP_TARGET_TRIGGER),
    ]
