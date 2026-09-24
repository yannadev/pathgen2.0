from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from jsonschema import Draft202012Validator, RefResolver

from .models import (
    Lesson,
    LessonSkill,
    Question,
    QuestionChoice,
    QuestionSet,
    QuestionSetItem,
    Skill,
    Video,
)


LOTS = {"remember", "understand", "apply"}
HOTS = {"analyze", "evaluate", "create"}
SAFE_VISUAL_COMPONENTS = {
    "integer_chip_choice_models",
    "integer_chip_model",
    "integer_number_line",
    "integer_number_line_choice_models",
    "integer_sign_rule",
    "operation_order_steps",
    "signed_vertical_scale",
}
LESSON_CONTENT_TYPES = {
    "objectives",
    "callout",
    "heading",
    "paragraph",
    "visual",
    "video",
    "worked_example",
    "practice_transition",
}
EXPECTED_ACTIVITY_SKILLS = {"S1": 3, "S2": 2, "S3": 3, "S4": 3, "S5": 2, "S6": 2}
SKILL_COPY = {
    "S1": ("Integers, opposites, and absolute value", "Identify integers, opposites, and absolute value."),
    "S2": ("Adding and subtracting integers", "Add and subtract integers accurately."),
    "S3": ("Multiplying and dividing integers", "Multiply and divide integers using sign rules."),
    "S4": ("Order of operations with integers", "Evaluate integer expressions using the order of operations."),
    "S5": ("Representing, comparing, and ordering integers", "Represent, compare, and order integers on a number line."),
    "S6": ("Applying integer operations", "Solve contextual problems involving integer operations."),
}


class SeedValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class SeedPackage:
    source_root: Path
    manifest: dict[str, Any]
    lesson_documents: list[dict[str, Any]]
    activity: dict[str, Any]
    prepost: dict[str, Any]
    media: dict[str, Any]

    @property
    def lessons(self) -> list[dict[str, Any]]:
        return [document["lesson"] for document in self.lesson_documents]

    @property
    def questions(self) -> list[dict[str, Any]]:
        return [
            *[question for document in self.lesson_documents for question in document["questions"]],
            *self.activity["questions"],
            *self.prepost["questions"],
        ]

    @property
    def question_sets(self) -> list[dict[str, Any]]:
        return [
            *[question_set for document in self.lesson_documents for question_set in document["question_sets"]],
            self.activity["question_set"],
            self.prepost["question_set"],
        ]


def default_seed_root() -> Path:
    return Path(settings.BASE_DIR).parent / "pathgen2.0docs" / "json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SeedValidationError([f"{path}: cannot read valid JSON ({error})."]) from error


def _schema_validator(schema_name: str) -> Draft202012Validator:
    schema_root = Path(__file__).resolve().parent / "schemas"
    common = _read_json(schema_root / "common.schema.json")
    schema = _read_json(schema_root / schema_name)
    Draft202012Validator.check_schema(common)
    Draft202012Validator.check_schema(schema)
    resolver = RefResolver.from_schema(common, store={common["$id"]: common, schema["$id"]: schema})
    return Draft202012Validator(schema, resolver=resolver)


def _validate_schema(document: dict[str, Any], schema_name: str, label: str) -> list[str]:
    validator = _schema_validator(schema_name)
    errors = []
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{label} schema error at {location}: {error.message}")
    return errors


def _require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _safe_relative_path(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and value == path.as_posix()


def _validate_question(errors: list[str], question: dict[str, Any], *, video_codes: set[str], app_root: Path) -> None:
    code = question["code"]
    choices = question["choices"]
    _require(errors, [choice["label"] for choice in choices] == list("ABCD"), f"{code}: choices must be ordered A-D.")
    _require(errors, [choice["display_order"] for choice in choices] == [1, 2, 3, 4], f"{code}: choice display order must be 1-4.")
    _require(errors, len({choice["text"].strip() for choice in choices}) == 4, f"{code}: choices must be distinct.")
    _require(errors, sum(choice["is_correct"] for choice in choices) == 1, f"{code}: exactly one choice must be correct.")
    _require(errors, question["is_published"] is True, f"{code}: reviewed questions must be published.")

    presentation = question["presentation_type"]
    visual_component = question["visual_component"]
    visual_config = question["visual_config"]
    image_asset = question["image_asset"]
    image_alt = question["image_alt"]
    video_code = question["video_code"]
    pause = question["video_pause_seconds"]
    if presentation == "text":
        _require(errors, all(value is None for value in (visual_component, visual_config, image_asset, image_alt, video_code, pause)), f"{code}: text questions cannot carry media.")
    elif presentation == "figure":
        _require(errors, isinstance(image_alt, str) and bool(image_alt.strip()), f"{code}: figures require alt text.")
        uses_component = visual_component is not None and visual_config is not None and image_asset is None
        uses_image = image_asset is not None and visual_component is None and visual_config is None
        _require(errors, uses_component ^ uses_image, f"{code}: figures require exactly one safe component or managed image.")
        _require(errors, video_code is None and pause is None, f"{code}: figures cannot carry video data.")
        if uses_component:
            _require(errors, visual_component in SAFE_VISUAL_COMPONENTS, f"{code}: visual component is not allowlisted.")
        if uses_image:
            _require(errors, _safe_relative_path(image_asset), f"{code}: image path is not a safe relative path.")
            _require(errors, bool(re.fullmatch(r"lessons/lesson-0[1-3]/[^/]+\.(?:png|webp|svg)", image_asset)), f"{code}: image must live in a managed per-lesson directory.")
            _require(errors, (app_root / "static" / "src" / "images" / image_asset).is_file(), f"{code}: managed image does not exist: {image_asset}.")
    else:
        _require(errors, video_code in video_codes and pause is not None, f"{code}: video questions require a known video and cue.")
        _require(errors, all(value is None for value in (visual_component, visual_config, image_asset, image_alt)), f"{code}: video questions cannot carry figure data.")


def load_and_validate_seed_package(source_root: Path | None = None) -> SeedPackage:
    source_root = (source_root or default_seed_root()).resolve()
    app_root = Path(settings.BASE_DIR).resolve()
    errors: list[str] = []
    manifest = _read_json(source_root / "manifest.json")
    errors.extend(_validate_schema(manifest, "manifest.schema.json", "manifest.json"))
    if errors:
        raise SeedValidationError(errors)

    lesson_paths = [source_root / entry["path"] for entry in manifest["lessons"]]
    activity_path = source_root / manifest["activity_path"]
    prepost_path = source_root / manifest["prepost_path"]
    media_path = source_root / manifest["media_manifest_path"]
    expected_json_paths = {source_root / "manifest.json", *lesson_paths, activity_path, prepost_path, media_path}
    actual_json_paths = set(source_root.rglob("*.json"))
    _require(errors, actual_json_paths == expected_json_paths, "Seed JSON inventory must match the manifest exactly.")

    lesson_documents = [_read_json(path) for path in lesson_paths]
    activity = _read_json(activity_path)
    prepost = _read_json(prepost_path)
    media = _read_json(media_path)
    for path, document in zip(lesson_paths, lesson_documents, strict=True):
        errors.extend(_validate_schema(document, "lesson.schema.json", path.relative_to(source_root).as_posix()))
    errors.extend(_validate_schema(activity, "activity.schema.json", activity_path.name))
    errors.extend(_validate_schema(prepost, "pretest_posttest.schema.json", prepost_path.name))
    errors.extend(_validate_schema(media, "media_manifest.schema.json", media_path.name))
    if errors:
        raise SeedValidationError(errors)

    package = SeedPackage(source_root, manifest, lesson_documents, activity, prepost, media)
    lessons = package.lessons
    questions = package.questions
    question_sets = package.question_sets
    by_code = {question["code"]: question for question in questions}
    lesson_by_code = {lesson["code"]: lesson for lesson in lessons}
    set_codes = [question_set["code"] for question_set in question_sets]
    video_by_code = {video["code"]: video for video in media["videos"]}
    skill_codes = [code for lesson in lessons for code in lesson["skill_codes"]]

    _require(errors, len(lessons) == len(lesson_by_code) == 3, "Exactly three unique lessons are required.")
    _require(errors, sorted(lesson["lesson_order"] for lesson in lessons) == [1, 2, 3], "Lesson order must be 1-3.")
    _require(errors, len(skill_codes) == len(set(skill_codes)) == 6 and set(skill_codes) == set(SKILL_COPY), "Each of the six skills must map to exactly one lesson.")
    _require(errors, len(questions) == len(by_code) == 135, "Exactly 135 unique questions are required.")
    _require(errors, len(set_codes) == len(set(set_codes)) == 14, "Exactly 14 uniquely coded question sets are required.")
    _require(errors, len(video_by_code) == len(media["videos"]), "Video codes must be unique.")

    for directory in media["lesson_image_directories"]:
        expected = app_root / "static" / "src" / "images" / "lessons" / directory
        _require(errors, expected.is_dir(), f"Managed lesson image directory is missing: {expected}.")

    for video in media["videos"]:
        transcript = source_root / video["transcript_path"]
        _require(errors, transcript.is_file() and transcript.stat().st_size > 500, f"{video['code']}: transcript is missing or incomplete.")
        _require(errors, video["canonical_url"] == f"https://www.youtube.com/watch?v={video['youtube_video_id']}", f"{video['code']}: canonical URL does not match the YouTube ID.")
        for segment in video["approved_segments"]:
            _require(errors, 0 <= segment["start_seconds"] < segment["end_seconds"] <= video["duration_seconds"], f"{video['code']}: approved segment is outside the video duration.")

    for lesson in lessons:
        _require(errors, lesson["is_published"] is True, f"{lesson['code']}: lesson must be published.")
        for block in lesson["content"]:
            block_type = block["type"]
            _require(errors, block_type in LESSON_CONTENT_TYPES, f"{lesson['code']}: unsupported content block {block_type!r}.")
            if block_type == "visual":
                _require(errors, block.get("component") in SAFE_VISUAL_COMPONENTS, f"{lesson['code']}: lesson visual is not allowlisted.")
                _require(errors, bool(str(block.get("text_alternative", "")).strip()), f"{lesson['code']}: lesson visual needs a text alternative.")
            if block_type == "video":
                code = block.get("video_code")
                _require(errors, code in video_by_code, f"{lesson['code']}: lesson video {code!r} is unknown.")
                if code in video_by_code:
                    _require(errors, 0 <= block.get("start_seconds", -1) < block.get("end_seconds", -1) <= video_by_code[code]["duration_seconds"], f"{lesson['code']}: lesson video segment is invalid.")

    video_codes = set(video_by_code)
    for question in questions:
        _require(errors, question["skill_code"] in set(skill_codes), f"{question['code']}: unknown skill code.")
        _validate_question(errors, question, video_codes=video_codes, app_root=app_root)
        if question["presentation_type"] == "video" and question["video_code"] in video_by_code:
            _require(errors, question["video_pause_seconds"] <= video_by_code[question["video_code"]]["duration_seconds"], f"{question['code']}: video cue exceeds duration.")

    expected_membership: list[str] = []
    type_counts: Counter[str] = Counter()
    for question_set in question_sets:
        set_type = question_set["set_type"]
        items = question_set["items"]
        codes = [item["question_code"] for item in items]
        expected_membership.extend(codes)
        type_counts[set_type] += len(codes)
        _require(errors, question_set["is_published"] is True, f"{question_set['code']}: set must be published.")
        _require(errors, len(codes) == len(set(codes)), f"{question_set['code']}: item questions must be unique.")
        _require(errors, [item["display_order"] for item in items] == list(range(1, len(items) + 1)), f"{question_set['code']}: item order must be contiguous from 1.")
        _require(errors, all(code in by_code for code in codes), f"{question_set['code']}: set references an unknown question.")
        if not all(code in by_code for code in codes):
            continue
        if set_type in {"regular", "additional"}:
            lesson = lesson_by_code.get(question_set["lesson_code"])
            _require(errors, lesson is not None and question_set["skill_code"] is None, f"{question_set['code']}: lesson exercise scope is invalid.")
            if lesson:
                distribution = Counter(by_code[code]["skill_code"] for code in codes)
                _require(errors, len(codes) == 10 and distribution == Counter({skill: 5 for skill in lesson["skill_codes"]}), f"{question_set['code']}: exercise must contain five questions per lesson skill.")
                levels = [by_code[code]["cognitive_level"] for code in codes]
                _require(errors, sum(level in LOTS for level in levels) == 6 and sum(level in HOTS for level in levels) == 4, f"{question_set['code']}: exercise must be 6 LOTS / 4 HOTS.")
        elif set_type == "foundational":
            _require(errors, question_set["lesson_code"] is None and question_set["skill_code"] in set(skill_codes), f"{question_set['code']}: foundational scope is invalid.")
            _require(errors, len(codes) == 5 and all(by_code[code]["skill_code"] == question_set["skill_code"] for code in codes), f"{question_set['code']}: foundational set must contain five questions for its skill.")
        elif set_type in {"activity", "prepost"}:
            _require(errors, question_set["lesson_code"] is None and question_set["skill_code"] is None, f"{question_set['code']}: global set scope is invalid.")

    _require(errors, len(expected_membership) == len(set(expected_membership)) == 135 and set(expected_membership) == set(by_code), "Every question must belong to exactly one approved set.")
    _require(errors, type_counts == Counter({"prepost": 30, "regular": 30, "additional": 30, "foundational": 30, "activity": 15}), "Question counts by set type must be 30/30/30/30/15.")

    for document in lesson_documents:
        lesson = document["lesson"]
        foundational_codes = [
            item["question_code"]
            for question_set in document["question_sets"]
            if question_set["set_type"] == "foundational"
            for item in question_set["items"]
        ]
        levels = [by_code[code]["cognitive_level"] for code in foundational_codes]
        _require(errors, len(levels) == 10 and sum(level in LOTS for level in levels) == 6 and sum(level in HOTS for level in levels) == 4, f"{lesson['code']}: combined foundational exercise must be 6 LOTS / 4 HOTS.")

    activity_questions = activity["questions"]
    activity_distribution = dict(sorted(Counter(item["skill_code"] for item in activity_questions).items()))
    _require(errors, activity_distribution == EXPECTED_ACTIVITY_SKILLS, "Activity skill distribution must be S1=3, S2=2, S3=3, S4=3, S5=2, S6=2.")
    _require(errors, manifest["activity_skill_distribution"] == EXPECTED_ACTIVITY_SKILLS, "Manifest activity skill distribution is invalid.")
    activity_levels = [item["cognitive_level"] for item in activity_questions]
    _require(errors, sum(level in LOTS for level in activity_levels) == 9 and sum(level in HOTS for level in activity_levels) == 6, "Activity must be 9 LOTS / 6 HOTS.")
    _require(errors, all(question["presentation_type"] in {"text", "figure"} for document in lesson_documents for question in document["questions"]), "Lesson exercises may contain only text or figure questions.")
    _require(errors, all(question["presentation_type"] != "video" for question in prepost["questions"]), "Protected pre/post questions cannot contain video.")

    protected_codes = [item["question_code"] for item in prepost["question_set"]["items"]]
    _require(errors, protected_codes == [f"PP-{number:02d}" for number in range(1, 31)], "Protected pre/post order must remain PP-01 through PP-30.")
    _require(errors, all(question.get("source_item_number") == number for number, question in enumerate(prepost["questions"], 1)), "Protected source item numbers must remain fixed 1-30.")
    pp13 = by_code.get("PP-13")
    if pp13:
        correct = [choice["label"] for choice in pp13["choices"] if choice["is_correct"]]
        _require(errors, correct == ["B"], "PP-13 must keep B as the official answer.")

    pdf_path = (source_root.parent / prepost["source_pdf"]).resolve()
    _require(errors, pdf_path.is_file(), "Protected pre/post source PDF is missing.")
    if pdf_path.is_file():
        digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        _require(errors, digest == prepost["source_sha256"], "Protected pre/post PDF SHA-256 does not match pretest_posttest.json.")

    if errors:
        raise SeedValidationError(errors)
    return package


def _sync(model, lookup: dict[str, Any], values: dict[str, Any]):
    instance = model.objects.filter(**lookup).first()
    if instance is None:
        return model.objects.create(**lookup, **values)
    changed = [field for field, value in values.items() if getattr(instance, field) != value]
    if changed:
        for field in changed:
            setattr(instance, field, values[field])
        instance.full_clean()
        instance.save(update_fields=[*changed, "updated_at"] if hasattr(instance, "updated_at") else changed)
    return instance


def _sync_publishable(model, lookup: dict[str, Any], values: dict[str, Any]):
    desired_published = values.pop("is_published")
    instance = model.objects.filter(**lookup).first()
    if instance is None:
        instance = model.objects.create(**lookup, **values, is_published=False)
    else:
        changed = [field for field, value in values.items() if getattr(instance, field) != value]
        if instance.is_published and changed:
            raise ValidationError(f"Published {model.__name__} {lookup} differs from the approved seed: {', '.join(changed)}.")
        if changed:
            for field in changed:
                setattr(instance, field, values[field])
            instance.full_clean()
            instance.save(update_fields=[*changed, "updated_at"])
    return instance, desired_published


@transaction.atomic
def import_seed_package(package: SeedPackage) -> dict[str, int]:
    bkt = package.manifest["adaptive_policy"]["bkt"]
    skill_values = {}
    for code, (name, description) in SKILL_COPY.items():
        skill_values[code] = {
            "name": name,
            "description": description,
            "p_l0": Decimal(str(bkt["p_l0"])),
            "p_t": Decimal(str(bkt["p_t"])),
            "p_g": Decimal(str(bkt["p_g"])),
            "p_s": Decimal(str(bkt["p_s"])),
        }
    skills = {item.code: item for item in Skill.objects.filter(code__in=skill_values)}
    Skill.objects.bulk_create(
        [Skill(code=code, **values) for code, values in skill_values.items() if code not in skills]
    )
    skills = {item.code: item for item in Skill.objects.filter(code__in=skill_values)}
    for code, values in skill_values.items():
        changed = [field for field, value in values.items() if getattr(skills[code], field) != value]
        if changed:
            if (
                skills[code].lesson_skills.filter(lesson__is_published=True).exists()
                or skills[code].questions.filter(is_published=True).exists()
            ):
                raise ValidationError(f"Published skill {code} differs from the approved seed: {', '.join(changed)}.")
            for field in changed:
                setattr(skills[code], field, values[field])
            skills[code].save(update_fields=[*changed, "updated_at"])

    video_values = {}
    for data in package.media["videos"]:
        transcript = (package.source_root / data["transcript_path"]).read_text(encoding="utf-8")
        video_values[data["code"]] = {
            "title": data["title"],
            "youtube_video_id": data["youtube_video_id"],
            "duration_seconds": data["duration_seconds"],
            "transcript": transcript,
        }
    videos = {item.code: item for item in Video.objects.filter(code__in=video_values)}
    Video.objects.bulk_create(
        [Video(code=code, **values) for code, values in video_values.items() if code not in videos]
    )
    videos = {item.code: item for item in Video.objects.filter(code__in=video_values)}
    for code, values in video_values.items():
        changed = [field for field, value in values.items() if getattr(videos[code], field) != value]
        if changed:
            if videos[code].questions.filter(is_published=True).exists():
                raise ValidationError(f"Published video {code} differs from the approved seed: {', '.join(changed)}.")
            for field in changed:
                setattr(videos[code], field, values[field])
            videos[code].save(update_fields=[*changed, "updated_at"])

    lesson_values = {}
    for data in package.lessons:
        lesson_values[data["code"]] = {
            "slug": data["slug"],
            "lesson_order": data["lesson_order"],
            "title": data["title"],
            "summary": data["summary"],
            "content_json": data["content"],
            "content_schema_version": data["content_schema_version"],
        }
    lessons = {item.code: item for item in Lesson.objects.filter(code__in=lesson_values)}
    Lesson.objects.bulk_create(
        [Lesson(code=code, **values, is_published=False) for code, values in lesson_values.items() if code not in lessons]
    )
    lessons = {item.code: item for item in Lesson.objects.filter(code__in=lesson_values)}
    for code, values in lesson_values.items():
        changed = [field for field, value in values.items() if getattr(lessons[code], field) != value]
        if changed:
            if lessons[code].is_published:
                raise ValidationError(f"Published lesson {code} differs from the approved seed: {', '.join(changed)}.")
            for field in changed:
                setattr(lessons[code], field, values[field])
            lessons[code].save(update_fields=[*changed, "updated_at"])

    desired_mappings = {}
    for data in package.lessons:
        for display_order, skill_code in enumerate(data["skill_codes"], 1):
            desired_mappings[(lessons[data["code"]].pk, skills[skill_code].pk)] = display_order
    existing_mappings = {
        (item.lesson_id, item.skill_id): item
        for item in LessonSkill.objects.filter(
            lesson_id__in=[key[0] for key in desired_mappings],
            skill_id__in=[key[1] for key in desired_mappings],
        )
    }
    LessonSkill.objects.bulk_create(
        [
            LessonSkill(lesson_id=lesson_id, skill_id=skill_id, display_order=display_order)
            for (lesson_id, skill_id), display_order in desired_mappings.items()
            if (lesson_id, skill_id) not in existing_mappings
        ]
    )
    for key, display_order in desired_mappings.items():
        existing = existing_mappings.get(key)
        if existing and existing.display_order != display_order:
            if lessons[next(code for code, lesson in lessons.items() if lesson.pk == key[0])].is_published:
                raise ValidationError("A published lesson skill mapping differs from the approved seed.")
            existing.display_order = display_order
            existing.save(update_fields=["display_order"])

    question_values = {}
    for data in package.questions:
        question_values[data["code"]] = {
            "skill": skills[data["skill_code"]],
            "prompt": data["prompt"],
            "difficulty": data["difficulty"],
            "presentation_type": data["presentation_type"],
            "cognitive_level": data["cognitive_level"],
            "solution_steps_json": data["solution_steps"],
            "explanation": data["explanation"],
            "hint": data["hint"],
            "feedback_correct": data["feedback_correct"],
            "feedback_incorrect": data["feedback_incorrect"],
            "image_asset": data["image_asset"],
            "image_alt": data["image_alt"],
            "visual_component": data["visual_component"],
            "visual_config_json": data["visual_config"],
            "video": videos.get(data["video_code"]),
            "video_pause_seconds": Decimal(str(data["video_pause_seconds"])) if data["video_pause_seconds"] is not None else None,
        }
    questions = {item.code: item for item in Question.objects.filter(code__in=question_values)}
    Question.objects.bulk_create(
        [Question(code=code, **values, is_published=False) for code, values in question_values.items() if code not in questions]
    )
    questions = {item.code: item for item in Question.objects.filter(code__in=question_values)}
    for code, values in question_values.items():
        changed = [field for field, value in values.items() if getattr(questions[code], field) != value]
        if changed:
            if questions[code].is_published:
                raise ValidationError(f"Published question {code} differs from the approved seed: {', '.join(changed)}.")
            for field in changed:
                setattr(questions[code], field, values[field])
            questions[code].save(update_fields=[*changed, "updated_at"])

    desired_choices = {}
    for data in package.questions:
        for choice in data["choices"]:
            desired_choices[(questions[data["code"]].pk, choice["label"])] = {
                "text": choice["text"],
                "is_correct": choice["is_correct"],
                "misconception_code": None,
                "display_order": choice["display_order"],
            }
    existing_choices = {
        (item.question_id, item.label): item
        for item in QuestionChoice.objects.filter(question_id__in=[key[0] for key in desired_choices])
    }
    QuestionChoice.objects.bulk_create(
        [
            QuestionChoice(question_id=question_id, label=label, **values)
            for (question_id, label), values in desired_choices.items()
            if (question_id, label) not in existing_choices
        ]
    )
    for key, values in desired_choices.items():
        existing = existing_choices.get(key)
        if existing:
            changed = [field for field, value in values.items() if getattr(existing, field) != value]
            if changed:
                question = next(item for item in questions.values() if item.pk == key[0])
                if question.is_published:
                    raise ValidationError(f"Published choices for {question.code} differ from the approved seed.")
                for field in changed:
                    setattr(existing, field, values[field])
                existing.save(update_fields=changed)

    set_values = {}
    for data in package.question_sets:
        set_values[data["code"]] = {
            "name": data["name"],
            "set_type": data["set_type"],
            "lesson": lessons.get(data["lesson_code"]),
            "skill": skills.get(data["skill_code"]),
        }
    def set_scope(values):
        return (
            values["set_type"],
            values["lesson"].pk if values["lesson"] else None,
            values["skill"].pk if values["skill"] else None,
        )

    existing_sets = {
        (item.set_type, item.lesson_id, item.skill_id): item
        for item in QuestionSet.objects.filter(set_type__in={values["set_type"] for values in set_values.values()})
    }
    QuestionSet.objects.bulk_create(
        [
            QuestionSet(**values, is_published=False)
            for values in set_values.values()
            if set_scope(values) not in existing_sets
        ]
    )
    existing_sets = {
        (item.set_type, item.lesson_id, item.skill_id): item
        for item in QuestionSet.objects.filter(set_type__in={values["set_type"] for values in set_values.values()})
    }
    question_sets = {code: existing_sets[set_scope(values)] for code, values in set_values.items()}
    for code, values in set_values.items():
        changed = [field for field, value in values.items() if getattr(question_sets[code], field) != value]
        if changed:
            if question_sets[code].is_published:
                raise ValidationError(f"Published question set {code} differs from the approved seed: {', '.join(changed)}.")
            for field in changed:
                setattr(question_sets[code], field, values[field])
            question_sets[code].save(update_fields=[*changed, "updated_at"])

    desired_items = {}
    for data in package.question_sets:
        for item in data["items"]:
            desired_items[(question_sets[data["code"]].pk, questions[item["question_code"]].pk)] = item["display_order"]
    existing_items = {
        (item.question_set_id, item.question_id): item
        for item in QuestionSetItem.objects.filter(question_set_id__in=[key[0] for key in desired_items])
    }
    QuestionSetItem.objects.bulk_create(
        [
            QuestionSetItem(question_set_id=set_id, question_id=question_id, display_order=display_order)
            for (set_id, question_id), display_order in desired_items.items()
            if (set_id, question_id) not in existing_items
        ]
    )
    for key, display_order in desired_items.items():
        existing = existing_items.get(key)
        if existing and existing.display_order != display_order:
            question_set = next(item for item in question_sets.values() if item.pk == key[0])
            if question_set.is_published:
                raise ValidationError(f"Published set items for {question_set.name} differ from the approved seed.")
            existing.display_order = display_order
            existing.save(update_fields=["display_order"])

    Question.objects.filter(code__in=question_values, is_published=False).update(is_published=True)
    QuestionSet.objects.filter(pk__in=[item.pk for item in question_sets.values()], is_published=False).update(is_published=True)
    Lesson.objects.filter(code__in=lesson_values, is_published=False).update(is_published=True)

    return {
        "lessons": len(lessons),
        "skills": len(skills),
        "questions": len(questions),
        "choices": len(desired_choices),
        "question_sets": len(question_sets),
        "videos": len(videos),
    }
