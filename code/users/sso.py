"""Map Core Connect Identity → local User (keyed by issuer + sub)."""

from __future__ import annotations

import hashlib

from core_connect_sso import CoreConnectSSOError, Identity
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.http import HttpRequest


def username_from_identity(issuer: str, sub: str) -> str:
    """Internal unique username; SSO identity remains ``(issuer, sub)``."""
    digest = hashlib.sha256(f"{issuer}\0{sub}".encode()).hexdigest()[:32]
    return f"cc_{digest}"


def _split_name(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0][:150], ""
    return parts[0][:150], parts[1][:150]


def _picture_from_identity(identity: Identity) -> str:
    raw = identity.raw or {}
    picture = raw.get("picture") or raw.get("avatar_url") or ""
    return str(picture).strip()[:500] if picture else ""


def _get_by_issuer_sub(User, issuer: str, sub: str):
    return User.objects.filter(core_connect_issuer=issuer, core_connect_sub=sub).first()


def _apply_identity_fields(user, *, email: str, first_name: str, last_name: str, avatar_url: str) -> list[str]:
    """Sync Core Connect–owned identity onto the local user; return changed field names."""
    update_fields: list[str] = []
    if user.email != email:
        user.email = email
        update_fields.append("email")
    if user.first_name != first_name:
        user.first_name = first_name
        update_fields.append("first_name")
    if user.last_name != last_name:
        user.last_name = last_name
        update_fields.append("last_name")
    if user.avatar_url != avatar_url:
        user.avatar_url = avatar_url
        update_fields.append("avatar_url")
    return update_fields


def _create_sso_user(User, *, issuer: str, sub: str, defaults: dict):
    """Create a user, recovering from a concurrent insert of the same (issuer, sub)."""
    try:
        with transaction.atomic():
            return (
                User.objects.create(
                    core_connect_issuer=issuer,
                    core_connect_sub=sub,
                    **defaults,
                ),
                True,
            )
    except IntegrityError:
        user = _get_by_issuer_sub(User, issuer, sub)
        if user is not None:
            return user, False
        raise CoreConnectSSOError(
            "could not provision user; concurrent create failed without an (issuer, sub) match"
        ) from None


@transaction.atomic
def map_core_connect_identity(identity: Identity, request: HttpRequest):
    """Create or update the local user from SSO identity; key by ``(issuer, sub)``."""
    User = get_user_model()
    sub = (identity.sub or "").strip()
    issuer = (identity.issuer or "").strip()
    if not sub:
        raise CoreConnectSSOError("identity has no sub; refusing to provision user")
    if not issuer:
        raise CoreConnectSSOError("identity has no issuer; refusing to provision user")

    email = (identity.email or "").strip()
    for field, value in (("core_connect_issuer", issuer), ("core_connect_sub", sub), ("email", email)):
        if len(value) > User._meta.get_field(field).max_length:
            raise CoreConnectSSOError(f"identity {field} exceeds the local field length")
    first_name, last_name = _split_name(identity.name or "")
    avatar_url = _picture_from_identity(identity)

    user = _get_by_issuer_sub(User, issuer, sub)
    created = user is None

    if created:
        defaults = {
            "username": username_from_identity(issuer, sub),
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "is_active": True,
            "password": make_password(None),
        }
        if avatar_url:
            defaults["avatar_url"] = avatar_url
        user, created = _create_sso_user(User, issuer=issuer, sub=sub, defaults=defaults)
        if created:
            return user

    update_fields: list[str] = []
    if user.has_usable_password():
        user.set_unusable_password()
        update_fields.append("password")
    update_fields.extend(
        _apply_identity_fields(
            user,
            email=email,
            first_name=first_name,
            last_name=last_name,
            avatar_url=avatar_url,
        )
    )
    if update_fields:
        user.save(update_fields=update_fields)

    return user
