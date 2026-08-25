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
from django.views.decorators.http import require_GET, require_http_methods, require_POST

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
        "aa_url": request.build_absolute_uri("/").rstrip("/").replace("http://", "https://"),
    }
    return render(request, "aa_eveaio/index.html", context)


@login_required
@permission_required("aa_eveaio.basic_access")
@require_http_methods(["GET", "POST"])
def license_config(request):
    if not request.user.is_staff:
        return redirect("aa_eveaio:index")

    license_obj = EveAioLicense.get_solo()
    saved = False

    if request.method == "POST":
        license_obj.license_key = request.POST.get("license_key", "").strip()
        corp_id_str = request.POST.get("corp_id", "").strip()
        license_obj.corp_id = int(corp_id_str) if corp_id_str else None
        license_obj.save()
        from django.core.cache import cache
        cache.delete("eveaio_license_valid")
        saved = True

    context = {
        "license": license_obj,
        "saved": saved,
    }
    return render(request, "aa_eveaio/license_config.html", context)


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
        "aa_url": request.build_absolute_uri("/").rstrip("/").replace("http://", "https://"),
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
        params = {"key": license_obj.license_key}
        if license_obj.corp_id:
            params["corp_id"] = license_obj.corp_id
        resp = django_requests.get(
            f"{LICENSE_SERVER_URL}/api/validate",
            params=params,
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

    all_tokens = (
        Token.objects
        .filter(character_id__in=char_ids)
        .prefetch_related("scopes")
        .select_related()
    )

    tokens_by_char = {}
    for token in all_tokens:
        tokens_by_char.setdefault(token.character_id, []).append(token)

    tokens = []
    for cid in char_ids:
        try:
            char_tokens = tokens_by_char.get(cid)
            if not char_tokens:
                continue

            all_scopes = set()
            best_token = None
            best_scope_count = -1

            for token in char_tokens:
                # Refresh expired tokens up-front so the access_token we hand
                # back to EVE AIO is actually usable. Tokens that fail to
                # refresh are returned as-is (with their refresh_token) so
                # EVE AIO can try refreshing with its own ESI client
                # credentials. We deliberately do NOT use ``require_valid()``
                # because that method DELETES tokens that fail to refresh.
                if token.expired and token.can_refresh:
                    try:
                        token.refresh()
                    except Exception as e:
                        logger.info(
                            "Could not refresh token for character %s on AA side: %s. "
                            "Returning as-is — EVE AIO can try refreshing with its own credentials.",
                            cid, e,
                        )

                # Use the prefetched scopes cache instead of issuing a fresh
                # query per token (values_list bypasses the prefetch cache).
                token_scopes = {s.name for s in token.scopes.all()}
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


@require_http_methods(["GET", "POST"])
@csrf_exempt
@xframe_options_exempt
def api_data_sync(request):
    """Cloud sync endpoint for EVE AIO user data (build jobs, custom prices, etc.).

    GET: returns the user's saved data blobs.
    POST: stores/updates the user's data blobs.

    Auth: X-Eveaio-Token header or ?token= query param.
    Body (POST): {"data": {"ledger": {...}, "custom_prices": {...}, ...}, "version": "2.1.20"}
    Response (GET): {"data": {...}, "updated_at": "...", "version": "..."}
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

    from aa_eveaio.models import EveAioDataSync

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)
        data_blobs = body.get("data", {})
        app_version = body.get("version", "")
        if not isinstance(data_blobs, dict):
            return JsonResponse({"error": "data must be a JSON object"}, status=400)
        obj, created = EveAioDataSync.objects.update_or_create(
            user=token_obj.user,
            defaults={
                "data_json": json.dumps(data_blobs),
                "app_version": app_version,
            },
        )
        logger.info(
            "EVE AIO data sync: %s uploaded %d blobs (version %s)",
            token_obj.user, len(data_blobs), app_version,
        )
        return JsonResponse({
            "status": "ok",
            "updated_at": obj.updated_at.isoformat(),
            "blobs_stored": len(data_blobs),
        })

    else:  # GET
        try:
            obj = EveAioDataSync.objects.get(user=token_obj.user)
            return JsonResponse({
                "data": json.loads(obj.data_json),
                "updated_at": obj.updated_at.isoformat(),
                "version": obj.app_version,
            })
        except EveAioDataSync.DoesNotExist:
            return JsonResponse({
                "data": None,
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
        sign_body = {"challenge": challenge, "key": license_obj.license_key}
        if license_obj.corp_id:
            sign_body["corp_id"] = license_obj.corp_id
        resp = django_requests.post(
            f"{LICENSE_SERVER_URL}/api/sign",
            json=sign_body,
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


def _auth_and_get_token(request):
    """Shared auth check for Fleet Manager endpoints. Returns (token_obj, None) or (None, JsonResponse)."""
    license_error = _check_license()
    if license_error:
        return None, license_error
    token_str = _get_token_from_request(request)
    if not token_str:
        return None, JsonResponse({"error": _("Missing token")}, status=401)
    try:
        token_obj = EveAioServiceToken.objects.select_related("user").get(token=token_str)
    except EveAioServiceToken.DoesNotExist:
        return None, JsonResponse({"error": _("Invalid token")}, status=403)
    return token_obj, None


def _get_user_corp_id(user_id):
    """Return (corp_id, corp_name) from the user's main character."""
    chars = _get_user_characters_from_aa(user_id)
    if not chars:
        return None, None
    c = chars[0]
    return c.get("corporation_id"), c.get("corporation_name")


def _get_corp_member_chars(corp_id):
    """Return list of EveCharacter dicts in the same corp, linked to AA users."""
    try:
        from allianceauth.eveonline.models import EveCharacter
        qs = EveCharacter.objects.filter(corporation_id=corp_id).values(
            "character_id", "character_name", "corporation_id", "corporation_name",
        )
        return [dict(c) for c in qs]
    except Exception as e:
        logger.warning("Failed to get corp members: %s", e)
        return []


def _get_esi_token_for_char(character_id, scopes_required=None):
    """Return a valid access token for a character, or None."""
    try:
        from esi.models import Token
        qs = Token.objects.filter(character_id=character_id)
        if scopes_required:
            for sc in scopes_required:
                qs = qs.filter(scopes__name=sc)
        token = qs.first()
        if not token:
            return None
        if token.expired and token.can_refresh:
            try:
                token.refresh()
            except Exception:
                return None
        return token.access_token
    except Exception:
        return None


def _esi_get(url, access_token, params=None):
    """Make a GET request to ESI with auth and compatibility header."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Compatibility-Date": "2025-07-22",
    }
    try:
        resp = django_requests.get(url, headers=headers, params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_fleet_roster(request):
    """Return corp members with online status, ship, and system."""
    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    corp_id, corp_name = _get_user_corp_id(token_obj.user_id)
    if not corp_id:
        return JsonResponse({"members": [], "corp_id": None, "corp_name": None})

    cache_key = f"eveaio_roster_{corp_id}"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    members_data = _get_corp_member_chars(corp_id)
    if not members_data:
        result = {"members": [], "corp_id": corp_id, "corp_name": corp_name}
        cache.set(cache_key, result, 60)
        return JsonResponse(result)

    result_members = []
    # Scopes required for the roster lookups below. Requesting a token that
    # actually has these scopes avoids silent 403s from ESI.
    roster_scopes = [
        "esi-location.read_online.v1",
        "esi-location.read_location.v1",
        "esi-location.read_ship_type.v1",
    ]
    for m in members_data:
        cid = m["character_id"]
        entry = {
            "character_id": cid,
            "character_name": m.get("character_name", ""),
            "online": False,
            "ship_name": None,
            "system_name": None,
            "solar_system_id": None,
        }
        access_token = _get_esi_token_for_char(cid, scopes_required=roster_scopes)
        if access_token:
            online = _esi_get(f"{ESI_BASE}/characters/{cid}/online/", access_token)
            if online and online.get("online"):
                entry["online"] = True
                loc = _esi_get(f"{ESI_BASE}/characters/{cid}/location/", access_token)
                if loc and loc.get("solar_system_id"):
                    entry["solar_system_id"] = loc["solar_system_id"]
                    sys_info = _esi_get(f"{ESI_BASE}/universe/systems/{loc['solar_system_id']}/", access_token)
                    if sys_info:
                        entry["system_name"] = sys_info.get("name")
                ship = _esi_get(f"{ESI_BASE}/characters/{cid}/ship/", access_token)
                if ship and ship.get("ship_type_id"):
                    ship_info = _esi_get(f"{ESI_BASE}/universe/types/{ship['ship_type_id']}/", access_token)
                    if ship_info:
                        entry["ship_name"] = ship_info.get("name")
        result_members.append(entry)

    result = {"members": result_members, "corp_id": corp_id, "corp_name": corp_name}
    cache.set(cache_key, result, 60)
    return JsonResponse(result)


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_discord_map(request):
    """Return {character_id: {discord_id, discord_username}} for corp members."""
    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    corp_id, _ = _get_user_corp_id(token_obj.user_id)
    if not corp_id:
        return JsonResponse({"discord_map": {}})

    try:
        from allianceauth.services.modules.discord.models import DiscordUser
    except ImportError:
        return JsonResponse({"discord_map": {}, "error": "Discord service not installed"})

    raw = _map_members_to_user_attr(corp_id, _discord_info_for_user)
    # Drop members with no linked Discord account (fn returned None).
    discord_map = {cid: info for cid, info in raw.items() if info is not None}
    return JsonResponse({"discord_map": discord_map})


def _discord_info_for_user(user):
    """Return {discord_id, discord_username} for a user, or None."""
    if user is None:
        return None
    try:
        from allianceauth.services.modules.discord.models import DiscordUser
        du = DiscordUser.objects.get(user=user)
        return {
            "discord_id": str(du.uid),
            "discord_username": du.username or "",
        }
    except DiscordUser.DoesNotExist:
        return None
    except Exception:
        return None


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_groups(request):
    """Return AA groups per character for corp members."""
    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    corp_id, _ = _get_user_corp_id(token_obj.user_id)
    if not corp_id:
        return JsonResponse({"groups": {}})

    groups_map = _map_members_to_user_attr(
        corp_id,
        lambda user: [g.name for g in user.groups.all()] if user is not None else [],
    )
    return JsonResponse({"groups": groups_map})


def _map_members_to_user_attr(corp_id, fn):
    """
    Build {str(character_id): fn(user)} for every EveCharacter in corp_id.

    Uses EveCharacter.user directly (one query with select_related) instead
    of iterating every AA user for every member. ``fn`` receives the owning
    User (or None if the character isn't linked to a user) and returns the
    per-character payload. ``user__groups`` is prefetched so callers reading
    ``user.groups.all()`` don't trigger an extra query per member.
    """
    out = {}
    try:
        from allianceauth.eveonline.models import EveCharacter
        qs = (
            EveCharacter.objects
            .filter(corporation_id=corp_id)
            .select_related("user")
            .prefetch_related("user__groups")
        )
        for char in qs.iterator():
            try:
                out[str(char.character_id)] = fn(getattr(char, "user", None))
            except Exception as e:
                logger.warning(
                    "Failed to map user attr for character %s: %s",
                    char.character_id, e,
                )
                continue
    except Exception as e:
        logger.warning("Failed to build member->user map for corp %s: %s", corp_id, e)
    return out


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_doctrines(request):
    """Return corp doctrine fittings from the fittings plugin."""
    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    try:
        from fittings.models import Doctrine, Fitting
    except ImportError:
        return JsonResponse({"doctrines": [], "error": "Fittings plugin not installed"})

    doctrines = []
    try:
        for doctrine in Doctrine.objects.all().order_by("name"):
            fits = []
            for fit in doctrine.fittings.all():
                fits.append({
                    "name": fit.name,
                    "ship_type_id": fit.ship_type_type_id,
                    "ship_name": fit.ship_type.name_en if hasattr(fit.ship_type, "name_en") else str(fit.ship_type),
                    "description": fit.description,
                })
            doctrines.append({
                "name": doctrine.name,
                "description": doctrine.description,
                "fittings": fits,
            })
    except Exception as e:
        logger.warning("Failed to read doctrines: %s", e)
        return JsonResponse({"doctrines": [], "error": f"Failed to read doctrines: {e}"})

    return JsonResponse({"doctrines": doctrines})


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_fat(request):
    """Return per-pilot fleet attendance from the FAT plugin."""
    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    corp_id, _ = _get_user_corp_id(token_obj.user_id)
    if not corp_id:
        return JsonResponse({"fat_data": {}})

    fat_models = None
    try:
        from afat.models import Fatlink, FatLinkCharacter
        fat_models = (Fatlink, FatLinkCharacter)
    except ImportError:
        pass

    if not fat_models:
        return JsonResponse({"fat_data": {}, "error": "FAT plugin not installed"})

    FatLink, FatLinkCharacter = fat_models
    members = _get_corp_member_chars(corp_id)
    member_ids = {m["character_id"] for m in members}

    ninety_days_ago = timezone.now() - timedelta(days=90)
    try:
        total_fleets = FatLink.objects.filter(fatdatetime__gte=ninety_days_ago).count()
    except Exception:
        total_fleets = 0

    fat_data = {}
    for cid in member_ids:
        try:
            attended = FatLinkCharacter.objects.filter(
                character_id=cid,
                fatlink__fatdatetime__gte=ninety_days_ago,
            ).count()
            last = FatLinkCharacter.objects.filter(
                character_id=cid,
            ).order_by("-fatlink__fatdatetime").first()
            last_fleet = None
            if last and hasattr(last, "fatlink") and last.fatlink:
                last_fleet = last.fatlink.fatdatetime.isoformat() if last.fatlink.fatdatetime else None
            rate = attended / total_fleets if total_fleets > 0 else 0
            fat_data[str(cid)] = {
                "fleets_attended": attended,
                "total_fleets": total_fleets,
                "rate": round(rate, 2),
                "last_fleet": last_fleet,
            }
        except Exception:
            continue

    return JsonResponse({"fat_data": fat_data})


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_srp_eligible(request):
    """Return SRP-eligible ship types and payout rates."""
    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    try:
        from srp.models import SrpShipType
    except ImportError:
        return JsonResponse({"srp_eligible": {}, "error": "SRP plugin not installed"})

    srp_eligible = {}
    try:
        for st in SrpShipType.objects.all():
            srp_eligible[str(st.ship_type_id)] = {
                "ship_name": getattr(st, "ship_name", ""),
                "payout": getattr(st, "srp_lose_amount", 0) or 0,
            }
    except Exception as e:
        logger.warning("Failed to read SRP ship types: %s", e)

    return JsonResponse({"srp_eligible": srp_eligible})


@require_POST
@csrf_exempt
@xframe_options_exempt
def api_srp_claim(request):
    """Submit an SRP claim from the Fleet Manager.

    Only characters belonging to the requesting user's corp are accepted, so
    one authenticated EVE AIO user cannot file SRP claims on behalf of an
    arbitrary character outside their corporation.
    """
    import json

    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    try:
        from srp.models import SrpShipRequest
    except ImportError:
        return JsonResponse({"error": "SRP plugin not installed"}, status=400)

    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    character_id = body.get("character_id")
    killmail_id = body.get("killmail_id")
    ship_type_id = body.get("ship_type_id")
    if not character_id or not killmail_id or not ship_type_id:
        return JsonResponse(
            {"error": "character_id, killmail_id and ship_type_id are required"},
            status=400,
        )

    # Authorisation: the character must belong to the caller's corp.
    corp_id, _ = _get_user_corp_id(token_obj.user_id)
    if not corp_id:
        return JsonResponse({"error": "No corp found for user"}, status=403)
    member_ids = {m["character_id"] for m in _get_corp_member_chars(corp_id)}
    if character_id not in member_ids:
        return JsonResponse(
            {"error": "Character is not a member of your corporation"},
            status=403,
        )

    ship_name = body.get("ship_name", "")
    total_value = body.get("total_value", 0)

    from allianceauth.eveonline.models import EveCharacter
    char = EveCharacter.objects.filter(character_id=character_id).first()
    if not char:
        return JsonResponse(
            {"error": "Character not found in Alliance Auth"},
            status=400,
        )

    try:
        claim = SrpShipRequest.objects.create(
            character=char,
            killmail_id=killmail_id,
            ship_name=ship_name,
            ship_type_id=ship_type_id,
            srp_total_amount=total_value,
            request_status="pending",
        )
        return JsonResponse({"status": "ok", "claim_id": claim.pk})
    except Exception as e:
        return JsonResponse({"error": f"Failed to create SRP claim: {e}"}, status=500)


@require_GET
@csrf_exempt
@xframe_options_exempt
def api_timers(request):
    """Return upcoming structure timers from the timerboard plugin.

    Field names vary between timerboard plugins (``timer`` vs
    ``timer_date`` vs ``date`` for the datetime; ``system`` vs
    ``eve_solar_system_id`` for the location, etc.). We probe the model
    for a usable datetime field and fall back gracefully so a schema
    mismatch returns ``[]`` with a logged warning rather than crashing.
    """
    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    try:
        from allianceauth.timerboard.models import Timer
    except ImportError:
        return JsonResponse({"timers": [], "error": "Timerboard plugin not installed"})

    # Pick the first datetime field that actually exists on the model.
    candidate_time_fields = ("timer", "timer_date", "date", "evetime", "time")
    time_field = None
    try:
        field_names = {f.name for f in Timer._meta.get_fields()}
        for cand in candidate_time_fields:
            if cand in field_names:
                time_field = cand
                break
    except Exception as e:
        logger.warning("Timer model introspection failed: %s", e)

    if not time_field:
        logger.warning(
            "Timerboard plugin installed but no recognised timer datetime "
            "field found on %s (tried %s)",
            Timer.__name__, candidate_time_fields,
        )
        return JsonResponse({"timers": [], "error": "Unsupported timerboard schema"})

    now = timezone.now()
    soon = now + timedelta(hours=48)
    timers = []
    try:
        qs = (
            Timer.objects
            .filter(**{f"{time_field}__gte": now, f"{time_field}__lte": soon})
            .order_by(time_field)[:50]
        )
        for t in qs:
            tv = getattr(t, time_field, None)
            entry = {
                "system": _first_present(t, ("system", "solar_system", "location", "")),
                "structure_type": _first_present(t, ("structure_type", "structure", "type", "")),
                "timer_time": tv.isoformat() if tv and hasattr(tv, "isoformat") else None,
                "time_remaining": None,
                "importance": _first_present(t, ("importance", "priority", ""), default="medium"),
            }
            if tv and hasattr(tv, "isoformat"):
                delta = tv - now
                if delta.total_seconds() > 0:
                    hours = int(delta.total_seconds() // 3600)
                    minutes = int((delta.total_seconds() % 3600) // 60)
                    entry["time_remaining"] = f"{hours}h {minutes}m"
            timers.append(entry)
    except Exception as e:
        logger.warning("Timer query failed: %s", e)

    return JsonResponse({"timers": timers})


def _first_present(obj, names, default=None):
    """Return the first non-empty attribute from ``names`` on ``obj``."""
    for n in names:
        if not n:
            continue
        v = getattr(obj, n, None)
        if v not in (None, ""):
            return v
    return default


@require_http_methods(["GET", "POST"])
@csrf_exempt
@xframe_options_exempt
def api_fleet_templates(request):
    """GET: return all corp fleet templates. POST: create/update (staff only).

    Note: ``name`` is the natural key. Reusing an existing name on POST will
    overwrite that template — including templates created by other staff
    members. This is intentional (corp-wide shared templates), but callers
    should be aware.
    """
    import json

    token_obj, err = _auth_and_get_token(request)
    if err:
        return err

    from aa_eveaio.models import EveAioFleetTemplate

    if request.method == "POST":
        if not token_obj.user.is_staff:
            return JsonResponse({"error": "Staff access required"}, status=403)
        try:
            body = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)
        name = body.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "name required"}, status=400)
        template_json = body.get("template_json", "{}")
        if not isinstance(template_json, str):
            template_json = json.dumps(template_json)

        # Preserve the original author on update: only set created_by when
        # actually creating a new row. update_or_create applies ``defaults``
        # on both create and update, so we split the two paths.
        defaults = {
            "description": body.get("description", ""),
            "template_json": template_json,
        }
        obj, created = EveAioFleetTemplate.objects.get_or_create(
            name=name,
            defaults={**defaults, "created_by": token_obj.user},
        )
        if not created:
            # Update mutable fields without touching created_by.
            obj.description = defaults["description"]
            obj.template_json = defaults["template_json"]
            obj.save(update_fields=["description", "template_json", "updated_at"])

        return JsonResponse({
            "status": "ok",
            "created": created,
            "template": {
                "name": obj.name,
                "description": obj.description,
                "template_json": obj.template_json,
                "updated_at": obj.updated_at.isoformat(),
            },
        })

    templates = []
    for t in EveAioFleetTemplate.objects.all().order_by("name"):
        templates.append({
            "name": t.name,
            "description": t.description,
            "template_json": t.template_json,
            "updated_at": t.updated_at.isoformat(),
        })
    return JsonResponse({"templates": templates})
