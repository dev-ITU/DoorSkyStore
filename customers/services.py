import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection, send_mail
from django.utils import timezone

from .models import CustomerEmailVerification, CustomerProfile, DeliveryAddress, EmailClientSettings


EMAIL_CODE_TTL_MINUTES = int(getattr(settings, 'CUSTOMER_EMAIL_CODE_TTL_MINUTES', 15))
EMAIL_CODE_RESEND_COOLDOWN_SECONDS = int(getattr(settings, 'CUSTOMER_EMAIL_CODE_RESEND_COOLDOWN_SECONDS', 60))


def _generate_email_code():
    return f'{secrets.randbelow(1_000_000):06d}'


def send_configured_email(subject, message, recipient_list, from_email=None):
    email_settings = EmailClientSettings.objects.filter(pk=1).first()
    if email_settings and email_settings.is_configured:
        connection = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=email_settings.host,
            port=email_settings.port,
            username=email_settings.username or None,
            password=email_settings.get_password() or None,
            use_tls=email_settings.use_tls,
            use_ssl=email_settings.use_ssl,
            timeout=email_settings.timeout_seconds,
        )
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=from_email or email_settings.from_email,
            to=recipient_list,
            connection=connection,
        )
        return email.send(fail_silently=False)

    return send_mail(
        subject=subject,
        message=message,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False,
    )


def send_email_verification_code(user, resend=False):
    email = (user.email or '').strip().lower()
    if not email:
        raise ValidationError('Укажите email перед отправкой кода подтверждения.')

    latest = user.email_verification_codes.filter(email__iexact=email, verified_at__isnull=True).first()
    if latest and latest.expires_at > timezone.now() and not resend:
        return latest, False
    if latest and resend:
        cooldown_until = latest.sent_at + timedelta(seconds=EMAIL_CODE_RESEND_COOLDOWN_SECONDS)
        if cooldown_until > timezone.now():
            seconds_left = int((cooldown_until - timezone.now()).total_seconds())
            raise ValidationError(f'Повторная отправка будет доступна через {max(seconds_left, 1)} сек.')

    code = _generate_email_code()
    verification = CustomerEmailVerification.objects.create(
        user=user,
        email=email,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=EMAIL_CODE_TTL_MINUTES),
    )
    send_configured_email(
        subject='Код подтверждения DoorSky',
        message=(
            f'Ваш код подтверждения DoorSky: {code}\n\n'
            f'Код действует {EMAIL_CODE_TTL_MINUTES} минут. '
            'Если вы не регистрировались на DoorSky, просто проигнорируйте письмо.'
        ),
        recipient_list=[email],
    )
    return verification, True


def verify_email_code(user, code):
    email = (user.email or '').strip().lower()
    if not email:
        raise ValidationError('У пользователя не указан email.')

    verification = user.email_verification_codes.filter(
        email__iexact=email,
        verified_at__isnull=True,
    ).first()
    if not verification:
        raise ValidationError('Для этого email нет активного кода. Запросите новый код.')
    if verification.is_expired:
        raise ValidationError('Срок действия кода истек. Запросите новый код.')
    if verification.attempts >= verification.max_attempts:
        raise ValidationError('Превышено количество попыток. Запросите новый код.')

    verification.attempts += 1
    if not check_password(code, verification.code_hash):
        verification.save(update_fields=['attempts'])
        raise ValidationError('Неверный код подтверждения.')

    now = timezone.now()
    verification.verified_at = now
    verification.save(update_fields=['attempts', 'verified_at'])
    user.email_verification_codes.filter(email__iexact=email, verified_at__isnull=True).exclude(
        pk=verification.pk
    ).update(verified_at=now)

    profile = get_customer_profile(user)
    profile.email_verified_at = now
    profile.save(update_fields=['email_verified_at', 'updated_at'])
    return verification


def reset_email_verification(profile):
    if profile.email_verified_at:
        profile.email_verified_at = None
        profile.save(update_fields=['email_verified_at', 'updated_at'])


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
    old_email = (user.email or '').strip().lower()
    new_email = (cleaned_data.get('customer_email') or '').strip().lower()

    profile.full_name = cleaned_data.get('customer_name') or profile.full_name
    profile.phone = cleaned_data.get('customer_phone') or profile.phone
    profile.customer_type = cleaned_data.get('customer_type') or profile.customer_type
    profile.company_name = cleaned_data.get('company_name') or ''
    profile.company_inn = cleaned_data.get('company_inn') or ''
    profile.company_kpp = cleaned_data.get('company_kpp') or ''
    profile.company_address = cleaned_data.get('company_address') or ''
    if new_email and old_email != new_email:
        profile.email_verified_at = None
    profile.save()

    if new_email and old_email != new_email:
        user.email = new_email
        user.save(update_fields=['email'])
        try:
            send_email_verification_code(user)
        except Exception:
            pass

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
