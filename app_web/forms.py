from allauth.account.forms import SignupForm
from django import forms
from phonenumber_field.formfields import PhoneNumberField

from .models import Brand, Category, Product, Profile, Review


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


class ProductAdminForm(forms.ModelForm):
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "style": "width: 100%; max-width: 72em;",
            }
        ),
        label="Опис",
    )

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["subcategory"].queryset = Category.objects.filter(parent__isnull=False).select_related("parent").order_by(
            "parent__name",
            "name",
        )
        self.fields["brand_ref"].queryset = Brand.objects.order_by("name")
        self.fields["subcategory"].help_text = "Оберіть дочірню категорію. Якщо товар належить лише головній категорії, залиште поле порожнім."
        self.fields["brand_ref"].help_text = "Бренд з довідника. Текстове поле бренду буде синхронізоване автоматично."

        current_category = self.instance.category if getattr(self.instance, "pk", None) else None
        category_value = self.data.get("category")
        if category_value and category_value.isdigit():
            current_category = Category.objects.filter(pk=int(category_value)).first() or current_category
        if current_category and current_category.parent_id:
            current_category = current_category.parent

        if current_category:
            self.fields["subcategory"].queryset = (
                Category.objects.filter(parent=current_category).select_related("parent").order_by("name")
            )

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")
        brand = (cleaned_data.get("brand") or "").strip()
        brand_ref = cleaned_data.get("brand_ref")

        if subcategory:
            if not subcategory.parent_id:
                self.add_error("subcategory", "Оберіть саме підкатегорію з батьківською категорією.")
            elif category and subcategory.parent_id != category.id:
                self.add_error("subcategory", "Підкатегорія повинна належати вибраній категорії.")
            else:
                cleaned_data["category"] = subcategory.parent
        elif category and category.parent_id:
            cleaned_data["subcategory"] = category
            cleaned_data["category"] = category.parent

        if brand_ref:
            cleaned_data["brand"] = brand_ref.name
        elif brand:
            normalized_brand = Brand.get_or_create_from_name(brand)
            if normalized_brand:
                cleaned_data["brand_ref"] = normalized_brand
                cleaned_data["brand"] = normalized_brand.name

        if cleaned_data.get("glycerin_price") and cleaned_data["glycerin_price"] > 0:
            cleaned_data["includes_glycerin"] = True

        return cleaned_data

