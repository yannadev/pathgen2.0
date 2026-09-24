from django.db import migrations


CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION curriculum_validate_question_video_cue()
RETURNS trigger AS $$
DECLARE
    video_duration integer;
BEGIN
    IF NEW.presentation_type = 'video' THEN
        SELECT duration_seconds INTO video_duration
        FROM curriculum_video
        WHERE id = NEW.video_id;

        IF NEW.video_pause_seconds > video_duration THEN
            RAISE EXCEPTION 'video cue must be within the referenced video duration'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = """
CREATE TRIGGER curriculum_question_video_cue_check
BEFORE INSERT OR UPDATE OF presentation_type, video_id, video_pause_seconds
ON curriculum_question
FOR EACH ROW EXECUTE FUNCTION curriculum_validate_question_video_cue();
"""

CREATE_VIDEO_FUNCTION = """
CREATE OR REPLACE FUNCTION curriculum_validate_video_duration()
RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM curriculum_question q
        WHERE q.video_id = NEW.id
          AND q.video_pause_seconds > NEW.duration_seconds
    ) THEN
        RAISE EXCEPTION 'video duration cannot be shorter than an existing question cue'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_VIDEO_TRIGGER = """
CREATE TRIGGER curriculum_video_duration_check
BEFORE UPDATE OF duration_seconds
ON curriculum_video
FOR EACH ROW EXECUTE FUNCTION curriculum_validate_video_duration();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS curriculum_question_video_cue_check ON curriculum_question;
"""

DROP_FUNCTION = """
DROP FUNCTION IF EXISTS curriculum_validate_question_video_cue();
"""

DROP_VIDEO_TRIGGER = "DROP TRIGGER IF EXISTS curriculum_video_duration_check ON curriculum_video;"
DROP_VIDEO_FUNCTION = "DROP FUNCTION IF EXISTS curriculum_validate_video_duration();"


class Migration(migrations.Migration):
    dependencies = [("curriculum", "0001_initial")]

    operations = [
        migrations.RunSQL(CREATE_FUNCTION, reverse_sql=DROP_FUNCTION),
        migrations.RunSQL(CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
        migrations.RunSQL(CREATE_VIDEO_FUNCTION, reverse_sql=DROP_VIDEO_FUNCTION),
        migrations.RunSQL(CREATE_VIDEO_TRIGGER, reverse_sql=DROP_VIDEO_TRIGGER),
    ]
