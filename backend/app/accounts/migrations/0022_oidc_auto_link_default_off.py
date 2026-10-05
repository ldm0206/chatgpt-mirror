# -*- coding: utf-8 -*-
"""OIDC username auto-linking is no longer safe to leave on by default.

On a self-registration IdP the username claim is attacker-chosen, so linking an
existing local account by it lets any IdP user claim that account. The flag now
defaults to off, and rows still holding the old default-on value are flipped so
every existing installation re-enables it consciously.
"""

from django.db import migrations, models


def flip_legacy_default_on(apps, schema_editor):
    SiteSettings = apps.get_model("accounts", "SiteSettings")
    SiteSettings.objects.filter(oidc_auto_link_by_username=True).update(oidc_auto_link_by_username=False)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0021_oidcflow'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitesettings',
            name='oidc_auto_link_by_username',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(flip_legacy_default_on, migrations.RunPython.noop),
    ]
