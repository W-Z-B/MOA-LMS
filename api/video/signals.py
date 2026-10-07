"""A video's files leave the file store with their records: lecture video is the largest thing a site keeps,
so a removed video, or a copy made again, must not go on filling the disk. Files go only once the
deletion is committed, so a deletion that is rolled back keeps them."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from video.models import Rendition, Video


def _remove_later(*fields) -> None:
    for field in fields:
        if field:
            storage, name = field.storage, field.name
            transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))


@receiver(post_delete, sender=Rendition)
def rendition_removed(sender, instance: Rendition, **kwargs) -> None:
    _remove_later(instance.file)


@receiver(post_delete, sender=Video)
def video_removed(sender, instance: Video, **kwargs) -> None:
    _remove_later(instance.original, instance.poster)
