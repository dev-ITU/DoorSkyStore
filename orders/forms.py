from django import forms

from .models import Order


class CheckoutForm(forms.Form):
    customer_type = forms.ChoiceField(
        label='Покупатель',
        choices=Order.CUSTOMER_TYPE_CHOICES,
        widget=forms.RadioSelect,
        initial=Order.CUSTOMER_INDIVIDUAL,
        required=False,
    )
    customer_name = forms.CharField(label='Имя', max_length=160)
    customer_phone = forms.CharField(label='Телефон', max_length=32)
    customer_email = forms.EmailField(label='Email', required=False)
    company_name = forms.CharField(label='Компания', max_length=220, required=False)
    company_inn = forms.CharField(label='ИНН', max_length=12, required=False)
    company_kpp = forms.CharField(label='КПП', max_length=9, required=False)
    company_address = forms.CharField(
        label='Юридический адрес',
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False,
    )
    delivery_address = forms.CharField(label='Адрес доставки', widget=forms.Textarea(attrs={'rows': 3}), required=False)
    payment_method = forms.ChoiceField(
        label='Способ оплаты',
        choices=Order.PAYMENT_METHOD_CHOICES,
        widget=forms.RadioSelect,
        initial=Order.PAYMENT_CARD,
        required=False,
    )
    comment = forms.CharField(label='Комментарий', widget=forms.Textarea(attrs={'rows': 3}), required=False)

    def clean(self):
        cleaned_data = super().clean()
        customer_type = cleaned_data.get('customer_type') or Order.CUSTOMER_INDIVIDUAL
        payment_method = cleaned_data.get('payment_method') or Order.PAYMENT_CARD
        cleaned_data['customer_type'] = customer_type
        cleaned_data['payment_method'] = payment_method

        if customer_type == Order.CUSTOMER_COMPANY:
            if not cleaned_data.get('company_name'):
                self.add_error('company_name', 'Укажите название компании.')
            if not cleaned_data.get('company_inn'):
                self.add_error('company_inn', 'Укажите ИНН для документов.')
        return cleaned_data


class PaymentSimulationForm(forms.Form):
    SCENARIO_SUCCESS = 'success'
    SCENARIO_FAIL = 'fail'

    SCENARIO_CHOICES = [
        (SCENARIO_SUCCESS, 'Платеж проходит успешно'),
        (SCENARIO_FAIL, 'Банк отклоняет платеж'),
    ]

    scenario = forms.ChoiceField(
        label='Сценарий симуляции',
        choices=SCENARIO_CHOICES,
        widget=forms.RadioSelect,
        initial=SCENARIO_SUCCESS,
    )
    card_holder = forms.CharField(label='Держатель карты', max_length=120, required=False)
    card_number = forms.CharField(label='Номер карты', max_length=24, required=False)
    card_expiry = forms.CharField(label='Срок действия', max_length=7, required=False)
    card_cvc = forms.CharField(label='CVC', max_length=4, required=False, widget=forms.PasswordInput(render_value=True))
    payer_note = forms.CharField(
        label='Комментарий платежа',
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False,
    )
