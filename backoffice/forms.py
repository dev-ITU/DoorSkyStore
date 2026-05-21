from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission
from django.utils.text import slugify

from catalog.models import Category, DoorProduct, StockItem
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
