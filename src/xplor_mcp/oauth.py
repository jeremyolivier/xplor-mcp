"""OAuth 2.1 provider bridging MCP auth to Xplor's own login.

Completing the OAuth authorization flow *is* logging into Xplor: the
`/authorize` redirect lands on our own email+code form instead of a
third-party identity provider. Each issued token carries the Xplor
member's own user id as its `subject`, so tools can look up the right
member's Xplor tokens instead of a single shared one (see `server.py`).
Transaction/code/token bookkeeping is in-memory and resets on server
restart; only registered DCR clients and each member's Xplor tokens are
persisted to disk (`store.py`).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from fastmcp.server.auth.auth import (
    AccessToken,
    AuthorizationCode,
    ClientRegistrationOptions,
    OAuthClientInformationFull,
    OAuthProvider,
)
from fastmcp.server.auth.auth import (
    RefreshToken as RefreshTokenModel,
)
from mcp.server.auth.provider import AuthorizationParams, construct_redirect_uri
from mcp.shared.auth import OAuthToken
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from xplor_mcp.client import XplorClient
from xplor_mcp.store import device_id, load_clients, save, save_client

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ACCESS_TOKEN_TTL = 3600
AUTH_CODE_TTL = 300


@dataclass
class _PendingAuthorization:
    client: OAuthClientInformationFull
    params: AuthorizationParams


@dataclass
class _PendingXplorLogin:
    request_id: str
    secret: str
    email: str


class XplorOAuthProvider(OAuthProvider):
    """Our own OAuth authorization server; the login screen is Xplor's."""

    def __init__(self, base_url: str) -> None:
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )
        self._clients: dict[str, OAuthClientInformationFull] = load_clients()
        self._pending_auth: dict[str, _PendingAuthorization] = {}
        self._pending_login: dict[str, _PendingXplorLogin] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshTokenModel] = {}

    # -- dynamic client registration --------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info
        save_client(client_info)

    # -- authorization: hand off to our Xplor login page -------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        txn = secrets.token_urlsafe(16)
        self._pending_auth[txn] = _PendingAuthorization(client=client, params=params)
        return f"{str(self.base_url).rstrip('/')}/xplor/login?txn={txn}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self._auth_codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        del self._auth_codes[authorization_code.code]  # one-time use
        return self._issue_tokens(
            client.client_id, authorization_code.scopes, authorization_code.subject
        )

    # -- tokens -------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        access = self._access_tokens.get(token)
        if access is None or (access.expires_at and access.expires_at < time.time()):
            return None
        return access

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshTokenModel | None:
        token = self._refresh_tokens.get(refresh_token)
        if token is None or token.client_id != client.client_id:
            return None
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshTokenModel,
        scopes: list[str],
    ) -> OAuthToken:
        del self._refresh_tokens[refresh_token.token]
        return self._issue_tokens(client.client_id, scopes, refresh_token.subject)

    async def revoke_token(self, token: AccessToken | RefreshTokenModel) -> None:
        self._access_tokens.pop(token.token, None)
        self._refresh_tokens.pop(token.token, None)

    def _issue_tokens(
        self, client_id: str, scopes: list[str], subject: str | None
    ) -> OAuthToken:
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        self._access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time() + ACCESS_TOKEN_TTL),
            subject=subject,
        )
        self._refresh_tokens[refresh_token] = RefreshTokenModel(
            token=refresh_token, client_id=client_id, scopes=scopes, subject=subject
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_token,
            scope=" ".join(scopes),
        )

    # -- the Xplor login form itself -----------------------------------

    async def login_page(self, request: Request) -> Response:
        txn = request.query_params.get("txn", "")
        return _templates.TemplateResponse(request, "login_email.html", {"txn": txn})

    async def login_start(self, request: Request) -> Response:
        form = await request.form()
        txn = str(form.get("txn", ""))
        email = str(form.get("email", "")).strip()
        with XplorClient(device_id=device_id()) as client:
            request_id, secret = client.request_login_code(email)
        self._pending_login[txn] = _PendingXplorLogin(request_id, secret, email)
        return _templates.TemplateResponse(
            request, "login_code.html", {"txn": txn, "email": email}
        )

    async def login_confirm(self, request: Request) -> Response:
        form = await request.form()
        txn = str(form.get("txn", ""))
        code = str(form.get("code", "")).strip()

        pending_auth = self._pending_auth.pop(txn, None)
        pending_login = self._pending_login.pop(txn, None)
        if pending_auth is None or pending_login is None:
            return PlainTextResponse("Expired or unknown login attempt.", status_code=400)

        with XplorClient(device_id=device_id()) as client:
            tokens = client.confirm_login_code(
                pending_login.request_id, pending_login.secret, code, pending_login.email
            )
        save(tokens)

        auth_code = secrets.token_urlsafe(32)
        self._auth_codes[auth_code] = AuthorizationCode(
            code=auth_code,
            scopes=pending_auth.params.scopes or [],
            expires_at=time.time() + AUTH_CODE_TTL,
            client_id=pending_auth.client.client_id,
            code_challenge=pending_auth.params.code_challenge,
            redirect_uri=pending_auth.params.redirect_uri,
            redirect_uri_provided_explicitly=pending_auth.params.redirect_uri_provided_explicitly,
            subject=tokens.user_id,
        )
        redirect_url = construct_redirect_uri(
            str(pending_auth.params.redirect_uri),
            code=auth_code,
            state=pending_auth.params.state,
        )
        return RedirectResponse(url=redirect_url, status_code=302)
