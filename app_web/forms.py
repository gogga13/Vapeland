from allauth.account.forms import SignupForm
from django import forms
from phonenumber_field.formfields import PhoneNumberField

from .models import Profile, Review


class CustomSignupForm(SignupForm):
    phone_number = PhoneNumberField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "+380",
                "class": "input-field",
                "id": "phone_signup",
            }
        ),
        label="Номер телефону",
    )

    def save(self, request):
        user = super().save(request)
        phone_number = self.cleaned_data.get("phone_number")
        if phone_number and hasattr(user, "profile"):
            user.profile.phone = str(phone_number)
            user.profile.save(update_fields=["phone"])
        return user


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "input-field",
                "placeholder": "Ваш email",
            }
        ),
    )


class PasswordResetConfirmForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        label="Код підтвердження",
        widget=forms.TextInput(
            attrs={
                "class": "input-field",
                "placeholder": "6-значний код",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
            }
        ),
    )
    new_password1 = forms.CharField(
        label="Новий пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "input-field",
                "placeholder": "Новий пароль",
                "data-password-input": "true",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Повторіть пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "input-field",
                "placeholder": "Повторіть пароль",
                "data-password-input": "true",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("new_password1")
        password2 = cleaned_data.get("new_password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Паролі не співпадають.")
        return cleaned_data


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        label="Ім'я",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "input-field",
                "required": True,
                "placeholder": "Ваше ім'я",
            }
        ),
    )
    last_name = forms.CharField(
        label="Прізвище",
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "input-field",
                "placeholder": "Ваше прізвище",
            }
        ),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "input-field",
                "required": True,
                "placeholder": "name@example.com",
            }
        ),
    )

    birth_date = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "class": "input-field",
                "type": "date",
            }
        ),
    )
    class Meta:
        model = Profile
        fields = ("first_name", "last_name", "email", "patronymic", "phone", "birth_date", "city", "address")
        widgets = {
            "patronymic": forms.TextInput(
                attrs={
                    "class": "input-field",
                    "placeholder": "По батькові",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "input-field",
                    "placeholder": "+380",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "input-field",
                    "placeholder": "Почніть вводити місто",
                    "autocomplete": "off",
                }
            ),
            "address": forms.TextInput(
                attrs={
                    "class": "input-field",
                    "placeholder": "Відділення або пошттомат",
                    "autocomplete": "off",
                }
            ),
        }
        labels = {
            "patronymic": "По батькові",
            "phone": "Номер телефону",
            "birth_date": "Дата народження",
            "city": "Місто доставки",
            "address": "Відділення / адреса доставки",
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["email"].initial = user.email

    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.user is not None:
            self.user.first_name = self.cleaned_data["first_name"]
            self.user.last_name = self.cleaned_data["last_name"]
            self.user.email = self.cleaned_data["email"]
            if commit:
                self.user.save(update_fields=["first_name", "last_name", "email"])

        if commit:
            profile.save()
        return profile


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "text")
        widgets = {
            "rating": forms.Select(
                choices=[(value, f"{value} / 5") for value in range(5, 0, -1)],
                attrs={"class": "input-field"},
            ),
            "text": forms.Textarea(
                attrs={
                    "class": "input-field",
                    "rows": 5,
                    "placeholder": "Напишіть ваш відгук",
                }
            ),
        }
        labels = {
            "rating": "Оцінка",
            "text": "Відгук",
        }

