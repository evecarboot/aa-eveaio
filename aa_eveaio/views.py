"""
Views for the EVE AIO Alliance Auth plugin.

- index: EVE AIO dashboard (user: show key; staff: link to manage roles).
- activate / deactivate: create or delete the user's service token
  (used by the Services page).
- show_token / regenerate_token: reveal or regenerate the user's key.
- api_roles: for the EVE AIO app: GET with token returns the user's
  AA-authed characters and their EVE AIO role assignments.
- api_esi_tokens: exports ESI tokens for the user's characters, so EVE AIO
  can make direct ESI calls without re-authing each toon.
- api_esi_proxy: proxies ESI calls through AA using the user's stored tokens.
"""

import logging
from datetime import timedelta

import requests as django_requests
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from aa_eveaio.models import EveAioCharacterRole, EveAioServiceToken, EveAioLicense

logger = logging.getLogger(__name__)

LICENSE_SERVER_URL = "https://license.eveaio.com"
LICENSE_CACHE_TIMEOUT = 86400
LICENSE_FAIL_OPEN_DAYS = 3


@login_required
@permission_required("aa_eveaio.basic_access")
def index(request):
    """EVE AIO dashboard: show key for the user; for staff, link to admin."""
    token_obj = getattr(request.user, "eveaio_service_token", None)
    context = {
        "has_token": token_obj is not None,
        "token_preview": (
            f"{token_obj.token[:8]}…" if token_obj and token_obj.token else None
        ),
        "is_staff": request.user.is_staff,
        "aa_url": request.build_absolute_uri("/").rstrip("/"),
    }
    return render(request, "aa_eveaio/index.html", context)


@login_required
@permission_required("aa_eveaio.basic_access")
@require_GET
def show_token(request):
    """Reveal the full token for copying (user must be logged in)."""
    token_obj = getattr(request.user, "eveaio_service_token", None)
    if not token_obj:
        return redirect("aa_eveaio:index")
    return render(request, "aa_eveaio/show_token.html", {
        "token": token_obj.token,
        "aa_url": request.build_absolute_uri("/").rstrip("/"),
    })


@login_required
@permission_required("aa_eveaio.basic_access")
@require_http_methods(["GET", "POST"])
def activate(request):
    """Create an EVE AIO service token for the current user (used from Services page)."""
    if getattr(request.user, "eveaio_service_token", None):
        return redirect("aa_eveaio:index")
    if request.method == "POST":
        EveAioServiceToken.objects.create(user=request.user)
        return redirect("aa_eveaio:index")
    return render(request, "aa_eveaio/activate.html")


@login_required
@permission_required("aa_eveaio.basic_access")
@require_http_methods(["GET", "POST"])
def deactivate(request):
    """Remove the EVE AIO service token (used from the Services page)."""
    token_obj = getattr(request.user, "eveaio_service_token", None)
    if not token_obj:
        return redirect("aa_eveaio:index")
    if request.method == "POST":
        token_obj.delete()
        return redirect("aa_eveaio:index")
    return render(request, "aa_eveaio/deactivate.html", {"token": token_obj})


@login_required
@permission_required("aa_eveaio.basic_access")
@require_http_methods(["POST"])
def regenerate_token(request):
    """Regenerate the token (invalidates the old one)."""
    token_obj = getattr(request.user, "eveaio_service_token", None)
    if not token_obj:
        return redirect("aa_eveaio:index")
    token_obj.regenerate_token()
    return redirect("aa_eveaio:show_token")


API_TOKEN_HEADER = "X-Eveaio-Token"


def _check_license():
    cached = cache.get("eveaio_license_valid")
    if cached is True:
        return None

    license_obj = EveAioLicense.get_solo()

    if not license_obj.license_key:
        return JsonResponse(
            {"error": "No license key configured. Enter your license key in Django Admin → EVE AIO → EVE AIO license."},
            status=402,
        )

    try:
        headers = {}
        if license_obj.license_api_key:
            headers["X-License-Api-Key"] = license_obj.license_api_key
        params = {"key": license_obj.license_key}
        if license_obj.corp_id:
            params["corp_id"] = license_obj.corp_id
        resp = django_requests.get(
            f"{LICENSE_SERVER_URL}/api/validate",
            params=params,
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("valid"):
                cache.set("eveaio_license_valid", True, LICENSE_CACHE_TIMEOUT)
                license_obj.last_validated = timezone.now()
                license_obj.last_valid = True
                license_obj.license_tier = data.get("tier", "")
                license_obj.last_error = ""
                if data.get("expires"):
                    try:
                        from datetime import datetime
                        license_obj.license_expires = datetime.fromisoformat(
                            data["expires"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass
                license_obj.save(update_fields=[
                    "last_validated", "last_valid", "license_tier",
                    "license_expires", "last_error", "updated_at",
                ])
                return None
            else:
                license_obj.last_validated = timezone.now()
                license_obj.last_valid = False
                license_obj.last_error = data.get("reason", "License invalid or expired")
                license_obj.save(update_fields=[
                    "last_validated", "last_valid", "last_error", "updated_at",
                ])
                return JsonResponse(
                    {"error": f"License invalid or expired: {license_obj.last_error}"},
                    status=402,
                )
        else:
            logger.warning("License server returned %s", resp.status_code)
            return _fail_open_or_closed(license_obj)
    except Exception as e:
        logger.warning("License server unreachable: %s", e)
        return _fail_open_or_closed(license_obj)


def _fail_open_or_closed(license_obj):
    if license_obj.last_valid and license_obj.last_validated:
        grace = license_obj.last_validated + timedelta(days=LICENSE_FAIL_OPEN_DAYS)
        if timezone.now() < grace:
            return None
    return JsonResponse(
        {"error": "License server unreachable and no recent valid validation."},
        status=402,
    )


def _get_token_from_request(request):
    """Extract the token from the header or ?token= (for simple testing)."""
    return request.headers.get(API_TOKEN_HEADER) or request.GET.get("token")


def _get_user_characters_from_aa(user_id):
    """
    Return a list of EVE characters linked to this user in AA (main + alts).

    Each item is a dict with character_id, character_name, corporation_id,
    corporation_name, alliance_id and alliance_name (alliance optional).

    In AA 5, ``EveCharacter`` has no ``character_owner_id`` field — characters
    are linked to users via the ``CharacterOwnership`` model. We use AA's
    built-in helper ``get_all_characters_from_user`` which handles this
    correctly, with a fallback to ``CharacterOwnership`` for older versions.
    """
    try:
        from allianceauth.framework.api.user import get_all_characters_from_user
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.get(pk=user_id)
        chars = get_all_characters_from_user(user=user)
        return [
            {
                "character_id": c.character_id,
                "character_name": c.character_name,
                "corporation_id": c.corporation_id,
                "corporation_name": c.corporation_name,
                "alliance_id": c.alliance_id,
                "alliance_name": c.alliance_name,
            }
            for c in chars
        ]
    except ImportError:
        try:
            from allianceauth.eveonline.models import EveCharacter

            qs = EveCharacter.objects.filter(character_owner_id=user_id).values(
                "character_id",
                "character_name",
                "corporation_id",
                "corporation_name",
                "alliance_id",
                "alliance_name",
            )
            return [dict(c) for c in qs]
        except Exception as e:
            logger.exception("EveCharacter lookup failed: %s", e)
            return []
    except Exception as e:
        logger.exception("get_all_characters_from_user failed: %s", e)
        return []


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_roles(request):
    """
    Public API for EVE AIO.

    GET with ``X-Eveaio-Token`` (or ``?token=``) returns:
    - ``characters``: list of AA-authed toons for this user (character_id, name,
      corp, alliance) so EVE AIO can "Import from Alliance Auth" without
      re-authing toons in the app.
    - ``character_roles``: ``{ "character_id": ["station_manager", ...] }`` for
      EVE AIO role grants.
    """
    license_error = _check_license()
    if license_error:
        return license_error

    token_str = _get_token_from_request(request)
    if not token_str:
        return JsonResponse(
            {"error": _("Missing token (header X-Eveaio-Token or ?token=)")},
            status=401,
        )
    try:
        token_obj = EveAioServiceToken.objects.select_related("user").get(
            token=token_str
        )
    except EveAioServiceToken.DoesNotExist:
        return JsonResponse({"error": _("Invalid token")}, status=403)

    characters = _get_user_characters_from_aa(token_obj.user_id)
    character_ids = {c["character_id"] for c in characters}

    assignments = EveAioCharacterRole.objects.filter(character_id__in=character_ids)
    character_roles = {}
    for a in assignments:
        character_roles.setdefault(str(a.character_id), []).append(a.role)

    return JsonResponse(
        {
            "characters": characters,
            "character_roles": character_roles,
        }
    )


ESI_BASE = "https://esi.evetech.net/latest"


def _get_esi_tokens_for_user(user_id):
    """
    Return a list of ESI tokens for all characters linked to this user in AA.

    Each item is a dict with character_id, character_name, access_token,
    refresh_token, expires_at, scopes, token_type and character_owner_hash.

    Tokens are refreshed if expired, but tokens that fail to refresh are
    returned as-is (with their refresh_token) so EVE AIO can try refreshing
    them with its own ESI client credentials. We deliberately do NOT use
    ``require_valid()`` because that method DELETES tokens that fail to
    refresh — which would destroy the user's ESI tokens just by querying them.
    """
    try:
        from esi.models import Token
    except ImportError:
        return []

    characters = _get_user_characters_from_aa(user_id)
    if not characters:
        return []
    char_ids = [c["character_id"] for c in characters]

    tokens = []
    for cid in char_ids:
        try:
            char_tokens = Token.objects.filter(character_id=cid).select_related()
            if not char_tokens:
                continue

            all_scopes = set()
            best_token = None
            best_scope_count = -1

            for token in char_tokens:
                if token.expired and token.can_refresh:
                    try:
                        token.refresh()
                    except Exception as e:
                        logger.info(
                            "Could not refresh token for character %s on AA side: %s. "
                            "Returning as-is — EVE AIO can try refreshing with its own credentials.",
                            cid, e,
                        )

                token_scopes = set(
                    token.scopes.values_list("name", flat=True)
                )
                all_scopes |= token_scopes

                if len(token_scopes) > best_scope_count:
                    best_scope_count = len(token_scopes)
                    best_token = token

            if not best_token:
                continue

            tokens.append(
                {
                    "character_id": best_token.character_id,
                    "character_name": best_token.character_name,
                    "access_token": best_token.access_token,
                    "refresh_token": best_token.refresh_token,
                    "expires_at": best_token.expires.isoformat(),
                    "scopes": sorted(all_scopes),
                    "token_type": best_token.token_type,
                    "character_owner_hash": best_token.character_owner_hash,
                }
            )
        except Exception as e:
            logger.warning("Failed to get tokens for character %s: %s", cid, e)
            continue
    return tokens


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_esi_tokens(request):
    """
    Export ESI tokens for all of the user's AA-authed characters.

    EVE AIO imports these so it can make direct ESI calls without requiring
    each toon to be individually authed in the desktop app.

    Auth: ``X-Eveaio-Token`` header or ``?token=`` query param.
    """
    license_error = _check_license()
    if license_error:
        return license_error

    token_str = _get_token_from_request(request)
    if not token_str:
        return JsonResponse({"error": _("Missing token")}, status=401)
    try:
        token_obj = EveAioServiceToken.objects.select_related("user").get(
            token=token_str
        )
    except EveAioServiceToken.DoesNotExist:
        return JsonResponse({"error": _("Invalid token")}, status=403)

    tokens = _get_esi_tokens_for_user(token_obj.user_id)

    try:
        from esi import app_settings as esi_settings

        client_id = esi_settings.ESI_SSO_CLIENT_ID
    except Exception:
        client_id = ""

    return JsonResponse({
        "tokens": tokens,
        "count": len(tokens),
        "client_id": client_id,
    })


@require_http_methods(["GET", "POST"])
@csrf_exempt
@xframe_options_exempt
def api_esi_proxy(request, esi_path):
    """
    Proxy an ESI call through AA using the user's stored ESI tokens.

    EVE AIO calls this instead of ESI directly when AA proxy mode is enabled.

    URL format: ``/eveaio/api/esi/<path>``
    (e.g. ``/eveaio/api/esi/characters/123/wallet/``)
    Query params: ``?character_id=123&datasource=tranquility&page=1``
    The ``character_id`` is used to look up the correct ESI token in AA.

    Auth: ``X-Eveaio-Token`` header or ``?token=`` query param.
    """
    license_error = _check_license()
    if license_error:
        return license_error

    token_str = _get_token_from_request(request)
    if not token_str:
        return JsonResponse({"error": _("Missing token")}, status=401)
    try:
        token_obj = EveAioServiceToken.objects.select_related("user").get(
            token=token_str
        )
    except EveAioServiceToken.DoesNotExist:
        return JsonResponse({"error": _("Invalid token")}, status=403)

    character_id = request.GET.get("character_id") or request.POST.get("character_id")
    if not character_id:
        return JsonResponse({"error": _("character_id required")}, status=400)

    try:
        from esi.models import Token

        esi_token = Token.objects.filter(character_id=int(character_id)).first()
        if not esi_token:
            return JsonResponse(
                {"error": _(f"No ESI token for character {character_id}")},
                status=403,
            )
        if esi_token.expired and esi_token.can_refresh:
            try:
                esi_token.refresh()
            except Exception as e:
                return JsonResponse(
                    {"error": f"ESI token for character {character_id} is expired and could not be refreshed: {e}"},
                    status=403,
                )
    except Exception as e:
        return JsonResponse({"error": f"Token lookup failed: {e}"}, status=500)

    esi_url = f"{ESI_BASE}/{esi_path}"

    params = {}
    for key, val in request.GET.items():
        if key not in ("token", "character_id"):
            params[key] = val
    if "datasource" not in params:
        params["datasource"] = "tranquility"

    headers = {
        "Authorization": f"Bearer {esi_token.access_token}",
        "X-Compatibility-Date": "2025-07-22",
    }

    try:
        if request.method == "GET":
            resp = django_requests.get(esi_url, headers=headers, params=params, timeout=30)
        else:
            body = request.body if request.body else None
            headers["Content-Type"] = "application/json"
            resp = django_requests.post(
                esi_url, headers=headers, params=params, data=body, timeout=30
            )

        content_type = resp.headers.get("Content-Type", "application/json")
        response = HttpResponse(
            resp.content, status=resp.status_code, content_type=content_type
        )
        for h in ("X-Pages", "Expires", "Cache-Control", "ETag", "X-Esi-Error-Limit-Remain"):
            if h in resp.headers:
                response[h] = resp.headers[h]
        return response
    except Exception as e:
        return JsonResponse({"error": f"ESI proxy failed: {e}"}, status=502)





@require_http_methods(["GET", "POST"])
@csrf_exempt
@xframe_options_exempt
def api_settings_sync(request):
    """Cloud sync endpoint for EVE AIO app settings.

    GET: returns the user's saved settings JSON blob.
    POST: stores/updates the user's settings JSON blob.

    Auth: X-Eveaio-Token header or ?token= query param.
    Body (POST): {"settings": {...}, "version": "2.1.18"}
    """
    license_error = _check_license()
    if license_error:
        return license_error

    import json

    token_str = _get_token_from_request(request)
    if not token_str:
        return JsonResponse({"error": _("Missing token")}, status=401)
    try:
        token_obj = EveAioServiceToken.objects.select_related("user").get(
            token=token_str
        )
    except EveAioServiceToken.DoesNotExist:
        return JsonResponse({"error": _("Invalid token")}, status=403)

    from aa_eveaio.models import EveAioSettingsSync

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)
        settings_data = body.get("settings", {})
        app_version = body.get("version", "")
        if not isinstance(settings_data, dict):
            return JsonResponse({"error": "settings must be a JSON object"}, status=400)
        obj, created = EveAioSettingsSync.objects.update_or_create(
            user=token_obj.user,
            defaults={
                "settings_json": json.dumps(settings_data),
                "app_version": app_version,
            },
        )
        logger.info(
            "EVE AIO settings sync: %s uploaded %d keys (version %s)",
            token_obj.user, len(settings_data), app_version,
        )
        return JsonResponse({
            "status": "ok",
            "updated_at": obj.updated_at.isoformat(),
            "keys_stored": len(settings_data),
        })

    else:  # GET
        try:
            obj = EveAioSettingsSync.objects.get(user=token_obj.user)
            return JsonResponse({
                "settings": json.loads(obj.settings_json),
                "updated_at": obj.updated_at.isoformat(),
                "version": obj.app_version,
            })
        except EveAioSettingsSync.DoesNotExist:
            return JsonResponse({
                "settings": None,
                "updated_at": None,
                "version": "",
            })





@require_POST
@csrf_exempt
@xframe_options_exempt
def api_auth(request):
    import json

    token_str = _get_token_from_request(request)
    if not token_str:
        return JsonResponse({"error": _("Missing token")}, status=401)
    try:
        EveAioServiceToken.objects.select_related("user").get(token=token_str)
    except EveAioServiceToken.DoesNotExist:
        return JsonResponse({"error": _("Invalid token")}, status=403)

    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    challenge = body.get("challenge", "")
    if not challenge or not isinstance(challenge, str):
        return JsonResponse({"error": "challenge required (non-empty string)"}, status=400)

    license_obj = EveAioLicense.get_solo()
    if not license_obj.license_key:
        return JsonResponse(
            {"error": "No license key configured. Enter your license key in Django Admin → EVE AIO → EVE AIO license."},
            status=402,
        )

    try:
        headers = {}
        if license_obj.license_api_key:
            headers["X-License-Api-Key"] = license_obj.license_api_key
        sign_body = {"challenge": challenge, "key": license_obj.license_key}
        if license_obj.corp_id:
            sign_body["corp_id"] = license_obj.corp_id
        resp = django_requests.post(
            f"{LICENSE_SERVER_URL}/api/sign",
            json=sign_body,
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("valid"):
                license_obj.last_validated = timezone.now()
                license_obj.last_valid = True
                license_obj.license_tier = data.get("tier", "")
                license_obj.last_error = ""
                if data.get("expires"):
                    try:
                        from datetime import datetime as _dt
                        license_obj.license_expires = _dt.fromisoformat(
                            data["expires"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass
                license_obj.save(update_fields=[
                    "last_validated", "last_valid", "license_tier",
                    "license_expires", "last_error", "updated_at",
                ])
                cache.set("eveaio_license_valid", True, LICENSE_CACHE_TIMEOUT)
            else:
                license_obj.last_validated = timezone.now()
                license_obj.last_valid = False
                license_obj.last_error = data.get("reason", "License invalid or expired")
                license_obj.save(update_fields=[
                    "last_validated", "last_valid", "last_error", "updated_at",
                ])
                cache.delete("eveaio_license_valid")
            return JsonResponse(data)
        else:
            logger.warning("License server returned %s", resp.status_code)
            return _fail_open_or_closed_signed(license_obj)
    except Exception as e:
        logger.warning("License server unreachable: %s", e)
        return _fail_open_or_closed_signed(license_obj)


def _fail_open_or_closed_signed(license_obj):
    if license_obj.last_valid and license_obj.last_validated:
        grace = license_obj.last_validated + timedelta(days=LICENSE_FAIL_OPEN_DAYS)
        if timezone.now() < grace:
            return JsonResponse({
                "valid": True,
                "fail_open": True,
                "reason": "License server unreachable",
                "valid_until": grace.isoformat(),
            })
    return JsonResponse(
        {"valid": False, "reason": "License server unreachable and no recent valid validation."},
        status=402,
    )
