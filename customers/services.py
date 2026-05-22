from .models import CustomerProfile, DeliveryAddress


def get_customer_profile(user):
    profile, _ = CustomerProfile.objects.get_or_create(
        user=user,
        defaults={
            'full_name': user.get_full_name() or user.get_username(),
            'phone': '',
        },
    )
    return profile


def set_default_address(user, address):
    DeliveryAddress.objects.filter(user=user).exclude(pk=address.pk).update(is_default=False)
    if not address.is_default:
        address.is_default = True
        address.save(update_fields=['is_default', 'updated_at'])
    profile = get_customer_profile(user)
    if profile.default_address_id != address.pk:
        profile.default_address = address
        profile.save(update_fields=['default_address', 'updated_at'])


def checkout_initial_for_user(user):
    if not user.is_authenticated:
        return {}

    profile = get_customer_profile(user)
    default_address = profile.default_address
    if default_address and default_address.user_id != user.id:
        default_address = None
    if not default_address:
        default_address = user.delivery_addresses.filter(is_default=True).first()
    if not default_address:
        default_address = user.delivery_addresses.first()

    return {
        'customer_type': profile.customer_type,
        'customer_name': profile.full_name or user.get_full_name() or user.get_username(),
        'customer_phone': profile.phone,
        'customer_email': user.email,
        'company_name': profile.company_name,
        'company_inn': profile.company_inn,
        'company_kpp': profile.company_kpp,
        'company_address': profile.company_address,
        'delivery_address_id': str(default_address.pk) if default_address else '',
        'delivery_address': default_address.address if default_address else '',
    }


def address_payloads_for_user(user):
    if not user.is_authenticated:
        return []
    return [
        {
            'id': address.pk,
            'title': address.title,
            'recipient_name': address.recipient_name,
            'phone': address.phone,
            'address': address.address,
            'is_default': address.is_default,
        }
        for address in user.delivery_addresses.all()
    ]


def save_customer_checkout_data(user, cleaned_data):
    if not user.is_authenticated:
        return None

    profile = get_customer_profile(user)
    profile.full_name = cleaned_data.get('customer_name') or profile.full_name
    profile.phone = cleaned_data.get('customer_phone') or profile.phone
    profile.customer_type = cleaned_data.get('customer_type') or profile.customer_type
    profile.company_name = cleaned_data.get('company_name') or ''
    profile.company_inn = cleaned_data.get('company_inn') or ''
    profile.company_kpp = cleaned_data.get('company_kpp') or ''
    profile.company_address = cleaned_data.get('company_address') or ''
    profile.save()

    email = cleaned_data.get('customer_email') or ''
    if email and user.email != email:
        user.email = email
        user.save(update_fields=['email'])

    if not cleaned_data.get('save_delivery_address'):
        return None

    delivery_address = (cleaned_data.get('delivery_address') or '').strip()
    if not delivery_address:
        return None

    selected_address = cleaned_data.get('selected_delivery_address')
    if selected_address:
        address = selected_address
        address.address = delivery_address
        address.recipient_name = cleaned_data.get('customer_name') or address.recipient_name
        address.phone = cleaned_data.get('customer_phone') or address.phone
        address.save(update_fields=['address', 'recipient_name', 'phone', 'updated_at'])
    else:
        address = user.delivery_addresses.filter(address__iexact=delivery_address).first()
        if address:
            address.recipient_name = cleaned_data.get('customer_name') or address.recipient_name
            address.phone = cleaned_data.get('customer_phone') or address.phone
            address.save(update_fields=['recipient_name', 'phone', 'updated_at'])
        else:
            address = DeliveryAddress.objects.create(
                user=user,
                title='Адрес доставки',
                recipient_name=cleaned_data.get('customer_name') or '',
                phone=cleaned_data.get('customer_phone') or '',
                address=delivery_address,
                is_default=not user.delivery_addresses.exists(),
            )

    if cleaned_data.get('make_default_address') or not profile.default_address_id:
        set_default_address(user, address)
    return address
