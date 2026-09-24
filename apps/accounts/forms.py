from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from apps.accounts.models import User


GENERIC_LOGIN_ERROR = "Unable to sign in with those credentials."
FIELD_CLASS = (
    "mt-2 block min-h-11 w-full rounded-lg border "
    "border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3.5 py-2.5 "
    "text-base text-[var(--color-foreground)] shadow-sm outline-none "
    "placeholder:text-[var(--color-foreground-muted)] "
    "focus:border-[var(--color-ring)] focus:ring-2 focus:ring-[var(--color-primary-subtle)]"
)


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": GENERIC_LOGIN_ERROR,
        "inactive": GENERIC_LOGIN_ERROR,
    }
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "autofocus": True,
                "class": FIELD_CLASS,
            }
        ),
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "class": FIELD_CLASS}
        ),
    )


class OwnNameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name"]
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name", "class": FIELD_CLASS}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name", "class": FIELD_CLASS}),
        }

    def clean_first_name(self) -> str:
        value = self.cleaned_data["first_name"].strip()
        if not value:
            raise forms.ValidationError("Enter your first name.")
        return value

    def clean_last_name(self) -> str:
        value = self.cleaned_data["last_name"].strip()
        if not value:
            raise forms.ValidationError("Enter your last name.")
        return value


class OwnPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = FIELD_CLASS
