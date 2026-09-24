from __future__ import annotations

from django import forms

from apps.accounts.forms import AccessibleFormMixin, FIELD_CLASS
from apps.accounts.models import User


class ClassroomCreateForm(AccessibleFormMixin, forms.Form):
    code = forms.CharField(max_length=64, widget=forms.TextInput(attrs={"class": FIELD_CLASS}))
    name = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": FIELD_CLASS}))
    teacher = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.none(),
        empty_label="No teacher assigned",
        widget=forms.Select(attrs={"class": FIELD_CLASS}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = User.objects.filter(
            role=User.Role.TEACHER, is_active=True
        ).order_by("last_name", "first_name", "username")


class ClassroomUpdateForm(AccessibleFormMixin, forms.Form):
    code = forms.CharField(max_length=64, widget=forms.TextInput(attrs={"class": FIELD_CLASS}))
    name = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": FIELD_CLASS}))


class AssignTeacherForm(AccessibleFormMixin, forms.Form):
    teacher = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.none(),
        empty_label="Unassigned",
        widget=forms.Select(attrs={"class": FIELD_CLASS}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = User.objects.filter(
            role=User.Role.TEACHER, is_active=True
        ).order_by("last_name", "first_name", "username")


class AddStudentsForm(AccessibleFormMixin, forms.Form):
    students = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": FIELD_CLASS, "size": 7}),
    )

    def __init__(self, *args, **kwargs):
        classroom=None
        if "classroom" in kwargs:
            classroom=kwargs.pop("classroom")
        super().__init__(*args, **kwargs)
        queryset = User.objects.filter(role=User.Role.STUDENT, is_active=True)
        if classroom is not None:
            queryset = queryset.exclude(
                classroom_memberships__classroom=classroom,
                classroom_memberships__left_at__isnull=True,
            )
        self.fields["students"].queryset = queryset.order_by(
            "last_name", "first_name", "username"
        )


class OptionalReasonForm(AccessibleFormMixin, forms.Form):
    reason = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": FIELD_CLASS, "rows": 3}),
    )


class RequiredReasonForm(OptionalReasonForm):
    reason = forms.CharField(
        required=True,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": FIELD_CLASS, "rows": 4}),
    )

    def clean_reason(self) -> str:
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("Enter a reason.")
        return reason


class ConfirmForm(AccessibleFormMixin, forms.Form):
    pass


class DeleteClassroomForm(RequiredReasonForm):
    code_confirmation = forms.CharField(
        max_length=64,
        widget=forms.TextInput(attrs={"class": FIELD_CLASS, "autocomplete": "off"}),
    )
