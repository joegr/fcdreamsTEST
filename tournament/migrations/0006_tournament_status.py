# Generated by Django 4.2.17 on 2025-02-11 06:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0005_remove_team_registration_code_alter_team_manager'),
    ]

    operations = [
        migrations.AddField(
            model_name='tournament',
            name='status',
            field=models.CharField(choices=[('REGISTRATION', 'Registration'), ('GROUP_STAGE', 'Group Stage'), ('KNOCKOUT', 'Knockout Stage'), ('COMPLETED', 'Completed')], default='REGISTRATION', max_length=20),
        ),
    ]
