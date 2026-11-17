
import accounts.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_consultationnote_retracted_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='psychologueprofile',
            name='photo',
            field=models.ImageField(blank=True, null=True, storage=accounts.models.get_psychologist_photo_storage, upload_to='psychologues/photos/', verbose_name='Photo de profil'),
        ),
    ]
