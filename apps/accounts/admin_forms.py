from __future__ import annotations

from django import forms

from apps.accounts.forms import AccessibleFormMixin, FIELD_CLASS
from apps.accounts.models import User


class ManagedUserCreateForm(AccessibleFormMixin, forms.Form):
    role = forms.ChoiceField(
        choices=[(User.Role.TEACHER, "Teacher"), (User.Role.STUDENT, "Student")],
        widget=forms.Select(attrs={"class": FIELD_CLASS}),
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": FIELD_CLASS, "autocomplete": "off"}),
    )
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": FIELD_CLASS}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": FIELD_CLASS}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": FIELD_CLASS}))
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": FIELD_CLASS, "autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": FIELD_CLASS, "autocomplete": "new-password"}),
    )

    def clean_username(self) -> str:
        username = User.normalize_username(self.cleaned_data["username"].strip())
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password_confirm"):
            if cleaned["password"] != cleaned["password_confirm"]:
                self.add_error("password_confirm", "The passwords do not match.")
        return cleaned


class ManagedUserUpdateForm(AccessibleFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": FIELD_CLASS}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": FIELD_CLASS}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": FIELD_CLASS}))


class RequiredReasonForm(AccessibleFormMixin, forms.Form):
    reason = forms.CharField(
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


class DeleteUserForm(RequiredReasonForm):
    username_confirmation = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": FIELD_CLASS, "autocomplete": "off"}),
    )
