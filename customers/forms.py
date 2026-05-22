from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import CustomerProfile, DeliveryAddress
from .services import get_customer_profile, set_default_address


class CustomerRegistrationForm(UserCreationForm):
    full_name = forms.CharField(label='Имя', max_length=160)
    email = forms.EmailField(label='Email')
    phone = forms.CharField(label='Телефон', max_length=32, required=False)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username', 'full_name', 'email', 'phone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Логин'
        self.fields['username'].help_text = ''
        self.fields['password1'].label = 'Пароль'
        self.fields['password1'].help_text = ''
        self.fields['password2'].label = 'Повторите пароль'
        self.fields['password2'].help_text = ''

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже зарегистрирован.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data['full_name'].strip()
        name_parts = full_name.split(' ', 1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            CustomerProfile.objects.create(
                user=user,
                full_name=full_name,
                phone=self.cleaned_data.get('phone') or '',
            )
        return user


class CustomerAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label='Логин')
    password = forms.CharField(
        label='Пароль',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )


class CustomerProfileForm(forms.Form):
    full_name = forms.CharField(label='Имя', max_length=160)
    email = forms.EmailField(label='Email')
    phone = forms.CharField(label='Телефон', max_length=32, required=False)
    customer_type = forms.ChoiceField(
        label='Тип покупателя',
        choices=CustomerProfile.CUSTOMER_TYPE_CHOICES,
        widget=forms.RadioSelect,
        required=False,
    )
    company_name = forms.CharField(label='Компания', max_length=220, required=False)
    company_inn = forms.CharField(label='ИНН', max_length=12, required=False)
    company_kpp = forms.CharField(label='КПП', max_length=9, required=False)
    company_address = forms.CharField(
        label='Юридический адрес',
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False,
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        profile = get_customer_profile(user)
        initial = {
            'full_name': profile.full_name or user.get_full_name() or user.get_username(),
            'email': user.email,
            'phone': profile.phone,
            'customer_type': profile.customer_type,
            'company_name': profile.company_name,
            'company_inn': profile.company_inn,
            'company_kpp': profile.company_kpp,
            'company_address': profile.company_address,
        }
        initial.update(kwargs.pop('initial', {}))
        super().__init__(*args, initial=initial, **kwargs)

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        user_exists = get_user_model().objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists()
        if user_exists:
            raise forms.ValidationError('Этот email уже используется другим пользователем.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('customer_type') == CustomerProfile.CUSTOMER_COMPANY:
            if not cleaned_data.get('company_name'):
                self.add_error('company_name', 'Укажите название компании.')
            if not cleaned_data.get('company_inn'):
                self.add_error('company_inn', 'Укажите ИНН для документов.')
        return cleaned_data

    def save(self):
        profile = get_customer_profile(self.user)
        full_name = self.cleaned_data['full_name'].strip()
        name_parts = full_name.split(' ', 1)
        self.user.first_name = name_parts[0]
        self.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        self.user.email = self.cleaned_data['email']
        self.user.save(update_fields=['first_name', 'last_name', 'email'])

        profile.full_name = full_name
        profile.phone = self.cleaned_data.get('phone') or ''
        profile.customer_type = self.cleaned_data.get('customer_type') or CustomerProfile.CUSTOMER_INDIVIDUAL
        profile.company_name = self.cleaned_data.get('company_name') or ''
        profile.company_inn = self.cleaned_data.get('company_inn') or ''
        profile.company_kpp = self.cleaned_data.get('company_kpp') or ''
        profile.company_address = self.cleaned_data.get('company_address') or ''
        profile.save()
        return profile


class DeliveryAddressForm(forms.ModelForm):
    class Meta:
        model = DeliveryAddress
        fields = ('title', 'recipient_name', 'phone', 'address', 'is_default')
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        address = super().save(commit=False)
        address.user = self.user
        if commit:
            address.save()
            has_other_addresses = self.user.delivery_addresses.exclude(pk=address.pk).exists()
            if address.is_default or not has_other_addresses:
                set_default_address(self.user, address)
            else:
                profile = get_customer_profile(self.user)
                if profile.default_address_id == address.pk:
                    profile.default_address = self.user.delivery_addresses.exclude(pk=address.pk).filter(is_default=True).first()
                    profile.save(update_fields=['default_address', 'updated_at'])
        return address
