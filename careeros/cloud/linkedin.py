"""Sign in with LinkedIn (OpenID Connect).

LinkedIn's self-serve sign-in product gives an app the member's name, email and
photo, nothing else: no connections, no messaging, no posting. CareerOS uses it
only to sign people in. Finding referrers works from the member's own
Connections.csv export and LinkedIn searches they open in their own browser.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

AUTHORIZE = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO = "https://api.linkedin.com/v2/userinfo"
SCOPES = "openid profile email"


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    return AUTHORIZE + "?" + urllib.parse.urlencode({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
                                                     "state": state, "scope": SCOPES})


def exchange(code: str, redirect_uri: str, client_id: str, client_secret: str, timeout: float = 15) -> str:
    """The access token for an authorization code."""
    body = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                                   "client_id": client_id, "client_secret": client_secret}).encode()
    req = urllib.request.Request(TOKEN, data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())["access_token"]


def userinfo(access_token: str, timeout: float = 15) -> dict:
    """{sub, name, given_name, family_name, picture, email, email_verified, locale}."""
    req = urllib.request.Request(USERINFO, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())
