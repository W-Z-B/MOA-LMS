"""Serializer base classes shared by the modules."""

from rest_framework import serializers


class ErrorSerializer(serializers.Serializer):
    """The body of every refusal the API writes itself: a stable code for programs, a sentence for people."""

    code = serializers.CharField()
    detail = serializers.CharField()


class TimeStampedSerializer(serializers.ModelSerializer):
    """Exposes audit stamps read-only; the view sets the acting user."""

    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        read_only_fields = ("id", "created_at", "updated_at")
