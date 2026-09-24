from __future__ import annotations

from django import forms
from django.db import models

from apps.accounts.forms import FIELD_CLASS


class GlobalOverrideForm(forms.Form):
    class Action(models.TextChoices):
        OPEN_STUDY = "open_study", "Open Student Study Access"
        CLOSE_STUDY = "close_study", "Close Student Study Access"
        UNLOCK_POSTTEST = "unlock_posttest", "Unlock Post-test Access"
        LOCK_POSTTEST = "lock_posttest", "Lock Post-test Access"

    action = forms.ChoiceField(choices=Action.choices, widget=forms.HiddenInput)
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    reason = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": FIELD_CLASS,
                "placeholder": "Record the operational reason for this change.",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        source = self.data if self.is_bound else self.initial
        action = source.get("action", "override")
        self.fields["reason"].widget.attrs["aria-describedby"] = (
            f"id_{action}_reason_help id_{action}_reason_error"
        )

    def clean_reason(self) -> str:
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("Explain why this access setting is changing.")
        return reason

    def setting_change(self) -> tuple[str, bool]:
        action = self.cleaned_data["action"]
        mapping = {
            self.Action.OPEN_STUDY: ("study_access_enabled", True),
            self.Action.CLOSE_STUDY: ("study_access_enabled", False),
            self.Action.UNLOCK_POSTTEST: ("posttest_access_enabled", True),
            self.Action.LOCK_POSTTEST: ("posttest_access_enabled", False),
        }
        return mapping[action]
