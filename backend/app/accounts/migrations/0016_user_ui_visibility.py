from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_sitesettings_oidc_oidcidentity")]

    operations = [
        migrations.AddField(
            model_name="user", name="hide_chat_work_toggle",
            field=models.BooleanField(default=False, verbose_name="隐藏聊天/工作切换栏"),
        ),
        migrations.AddField(
            model_name="user", name="hide_library",
            field=models.BooleanField(default=False, verbose_name="隐藏资料库"),
        ),
    ]
