# aa-eveaio

Alliance Auth plugin for EVE AIO.

> **Requires Alliance Auth v5.2+** (Python 3.10+, Django 5.2).

A license is required to use this plugin. Join the [EVEAIO Discord](https://discord.gg/sDadBzFHYY) to get access.

## Installation

```bash
pip install aa-eveaio
```

Add to your AA `settings/local.py`:

```python
INSTALLED_APPS += ["aa_eveaio"]
APPS_WITH_PUBLIC_VIEWS = ["aa_eveaio"]
```

Run migrations and collect static files:

```bash
python manage.py migrate aa_eveaio
python manage.py collectstatic --noinput
```

Restart your Alliance Auth server.

## Setup

1. Join the [EVEAIO Discord](https://discord.gg/sDadBzFHYY) to obtain a license key.
2. In Django Admin → EVE AIO → EVE AIO license, enter your license key.
3. **Admins:** Django Admin → EVE AIO → EVE AIO character roles. Assign roles to characters.
4. **Users:** Services → activate EVE AIO to get a key. Enter the AA URL and key in the EVE AIO app.

## Requirements

- Alliance Auth 5.2+
- django-esi 9+
- EVEAIO license (available via the [EVEAIO Discord](https://discord.gg/sDadBzFHYY))
