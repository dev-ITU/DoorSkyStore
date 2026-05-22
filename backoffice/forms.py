from email.utils import parseaddr

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission
from django.core.validators import validate_email
from django.utils.text import slugify

from catalog.models import Category, DoorProduct, StockItem
from customers.models import EmailClientSettings
from orders.models import Order


PERMISSION_APP_LABELS = ('auth', 'catalog', 'orders', 'webanalytics')


class BackofficeFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            field.widget.attrs.setdefault('class', 'office-input')


class CategoryForm(BackofficeFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'slug', 'description', 'source_url', 'is_active')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False

    def clean_slug(self):
        slug = self.cleaned_data.get('slug') or slugify(self.cleaned_data.get('name', ''))
        if not slug:
            raise forms.ValidationError('Укажите URL-ярлык.')
        queryset = Category.objects.filter(slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError('Категория с таким URL-ярлыком уже есть.')
        return slug


class ProductForm(BackofficeFormMixin, forms.ModelForm):
    class Meta:
        model = DoorProduct
        fields = (
            'category',
            'name',
            'slug',
            'sku',
            'description',
            'price',
            'width_min_mm',
            'width_max_mm',
            'height_min_mm',
            'height_max_mm',
            'material',
            'color',
            'finish',
            'opening_type',
            'image',
            'image_url',
            'source_url',
            'is_active',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.order_by('name')
        self.fields['slug'].required = False

    def clean_slug(self):
        slug = self.cleaned_data.get('slug') or slugify(self.cleaned_data.get('name', ''))
        if not slug:
            slug = slugify(self.cleaned_data.get('sku', '')) or 'door'
        base_slug = slug
        counter = 2
        queryset = DoorProduct.objects.filter(slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        while queryset.exists():
            slug = f'{base_slug}-{counter}'
            queryset = DoorProduct.objects.filter(slug=slug)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            counter += 1
        return slug


class StockForm(BackofficeFormMixin, forms.ModelForm):
    class Meta:
        model = StockItem
        fields = ('quantity', 'reserved_quantity', 'min_quantity')


class OrderBackofficeForm(BackofficeFormMixin, forms.ModelForm):
    class Meta:
        model = Order
        fields = (
            'status',
            'payment_status',
            'payment_method',
            'customer_type',
            'customer_name',
            'customer_phone',
            'customer_email',
            'company_name',
            'company_inn',
            'company_kpp',
            'company_address',
            'delivery_address',
            'comment',
            'payment_comment',
        )
        widgets = {
            'company_address': forms.Textarea(attrs={'rows': 2}),
            'delivery_address': forms.Textarea(attrs={'rows': 3}),
            'comment': forms.Textarea(attrs={'rows': 3}),
            'payment_comment': forms.Textarea(attrs={'rows': 2}),
        }


class EmailSettingsForm(BackofficeFormMixin, forms.ModelForm):
    password = forms.CharField(
        label='SMTP пароль',
        required=False,
        widget=forms.PasswordInput(
            attrs={
                'autocomplete': 'new-password',
                'placeholder': 'Оставьте пустым, чтобы не менять',
            }
        ),
    )
    clear_password = forms.BooleanField(label='Удалить сохраненный пароль', required=False)
    test_email = forms.EmailField(label='Email для теста', required=False)

    class Meta:
        model = EmailClientSettings
        fields = (
            'is_enabled',
            'host',
            'port',
            'username',
            'from_email',
            'use_tls',
            'use_ssl',
            'timeout_seconds',
        )

    def clean(self):
        cleaned_data = super().clean()
        is_enabled = cleaned_data.get('is_enabled')
        username = (cleaned_data.get('username') or '').strip()
        from_email = (cleaned_data.get('from_email') or '').strip()
        password = cleaned_data.get('password')
        clear_password = cleaned_data.get('clear_password')
        is_test = self.data.get('action') == 'send_test'

        if cleaned_data.get('use_tls') and cleaned_data.get('use_ssl'):
            self.add_error('use_ssl', 'TLS и SSL нельзя включать одновременно.')

        if password and clear_password:
            self.add_error('clear_password', 'Нельзя одновременно задать новый пароль и удалить текущий.')

        if password and not username:
            self.add_error('username', 'Для пароля нужен SMTP логин.')

        if from_email:
            parsed_email = parseaddr(from_email)[1] or from_email
            try:
                validate_email(parsed_email)
            except forms.ValidationError:
                self.add_error('from_email', 'Укажите корректный email отправителя.')

        if is_enabled:
            if not cleaned_data.get('host'):
                self.add_error('host', 'Укажите SMTP host.')
            if not cleaned_data.get('from_email'):
                self.add_error('from_email', 'Укажите email отправителя.')
            if username and not password and (clear_password or not self.instance.has_password):
                self.add_error('password', 'Укажите SMTP пароль для этого логина.')

        if is_test:
            if not is_enabled:
                self.add_error('is_enabled', 'Для тестовой отправки включите почтовые настройки.')
            if not cleaned_data.get('test_email'):
                self.add_error('test_email', 'Укажите адрес для тестовой отправки.')

        return cleaned_data

    def save(self, commit=True, updated_by=None):
        email_settings = super().save(commit=False)
        email_settings.updated_by = updated_by
        if self.cleaned_data.get('clear_password'):
            email_settings.encrypted_password = ''
        elif self.cleaned_data.get('password'):
            email_settings.set_password(self.cleaned_data['password'])
        if commit:
            email_settings.save()
        return email_settings


class UserPermissionMixin(BackofficeFormMixin):
    def _configure_permission_fields(self):
        permission_queryset = Permission.objects.select_related('content_type').filter(
            content_type__app_label__in=PERMISSION_APP_LABELS
        ).order_by('content_type__app_label', 'content_type__model', 'codename')
        if 'groups' in self.fields:
            self.fields['groups'].queryset = Group.objects.order_by('name')
            self.fields['groups'].required = False
            self.fields['groups'].widget.attrs.update({'class': 'office-input', 'size': 8})
        if 'user_permissions' in self.fields:
            self.fields['user_permissions'].queryset = permission_queryset
            self.fields['user_permissions'].required = False
            self.fields['user_permissions'].widget.attrs.update({'class': 'office-input', 'size': 12})


class BackofficeUserCreateForm(UserPermissionMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'is_staff',
            'is_superuser',
            'groups',
            'user_permissions',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_permission_fields()
        self.fields['is_active'].initial = True
        self.fields['is_staff'].initial = True

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            self.save_m2m()
        return user


class BackofficeUserEditForm(UserPermissionMixin, forms.ModelForm):
    new_password1 = forms.CharField(label='Новый пароль', required=False, widget=forms.PasswordInput)
    new_password2 = forms.CharField(label='Повтор пароля', required=False, widget=forms.PasswordInput)

    class Meta:
        model = get_user_model()
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'is_staff',
            'is_superuser',
            'groups',
            'user_permissions',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_permission_fields()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('new_password1')
        password2 = cleaned_data.get('new_password2')
        if password1 or password2:
            if password1 != password2:
                self.add_error('new_password2', 'Пароли не совпадают.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('new_password1')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_m2m()
        return user
