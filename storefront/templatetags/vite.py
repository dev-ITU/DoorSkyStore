import json
import os
from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def vite_asset(entry):
    dev_server = os.getenv('VITE_DEV_SERVER', '')
    if dev_server:
        dev_server = dev_server.rstrip('/')
        return mark_safe(
            '\n'.join(
                [
                    format_html('<script type="module" src="{}/@vite/client"></script>', dev_server),
                    format_html('<script type="module" src="{}/{}"></script>', dev_server, entry),
                ]
            )
        )

    manifest_path = Path(settings.BASE_DIR) / 'static' / 'react' / 'manifest.json'
    if not manifest_path.exists():
        return ''

    with manifest_path.open(encoding='utf-8') as manifest_file:
        manifest = json.load(manifest_file)

    chunk = manifest.get(entry)
    if not chunk:
        return ''

    tags = []
    for css_file in chunk.get('css', []):
        tags.append(format_html('<link rel="stylesheet" href="{}">', static(f'react/{css_file}')))
    tags.append(format_html('<script type="module" src="{}" defer></script>', static(f"react/{chunk['file']}")))
    return mark_safe('\n'.join(tags))
