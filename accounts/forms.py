from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class StyledMixin:
    def _style(self):
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "field-input")
            f.widget.attrs.setdefault("placeholder", " ")


class RegisterForm(StyledMixin, UserCreationForm):
    first_name = forms.CharField(max_length=60, label="First name")
    last_name = forms.CharField(max_length=60, label="Last name", required=False)
    email = forms.EmailField()
    phone = forms.CharField(max_length=15, label="Mobile number")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "username")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try signing in.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CUSTOMER  # never trust client-side role input
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class LoginForm(StyledMixin, AuthenticationForm):
    username = forms.CharField(label="Username or email")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean(self):
        ident = self.cleaned_data.get("username")
        if ident and "@" in ident:
            u = User.objects.filter(email__iexact=ident).first()
            if u:
                self.cleaned_data["username"] = u.username
                self.data = self.data.copy()
                self.data["username"] = u.username
        return super().clean()


class ProfileForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "address", "avatar")
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()
        self.fields["avatar"].widget.attrs["class"] = "field-file"

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.exclude(pk=self.instance.pk).filter(email__iexact=email).exists():
            raise forms.ValidationError("That email is already used by another account.")
        return email

    def clean_avatar(self):
        img = self.cleaned_data.get("avatar")
        if img and hasattr(img, "size"):
            if img.size > 2 * 1024 * 1024:
                raise forms.ValidationError("Image must be under 2 MB.")
            if getattr(img, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
                raise forms.ValidationError("Use a JPG, PNG or WebP image.")
        return img
