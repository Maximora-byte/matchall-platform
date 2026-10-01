from pathlib import Path

from authentik.core.models import Application
from authentik.flows.models import Flow
from authentik.providers.oauth2.models import (
    OAuth2Provider,
    RedirectURI,
    RedirectURIMatchingMode,
    RedirectURIType,
)

secret = Path("/data/matchall-mirrors-client.secret").read_text().strip()
reference = OAuth2Provider.objects.get(name="Nextcloud")
authorization = Flow.objects.get(slug="default-provider-authorization-implicit-consent")
invalidation = Flow.objects.get(slug="default-provider-invalidation-flow")

provider, _ = OAuth2Provider.objects.update_or_create(
    name="MatchAll Mirrors",
    defaults={
        "authorization_flow": authorization,
        "invalidation_flow": invalidation,
        "client_type": "confidential",
        "client_id": "matchall-mirrors",
        "client_secret": secret,
        "grant_types": ["authorization_code", "refresh_token"],
        "include_claims_in_id_token": True,
        "sub_mode": "user_uuid",
        "issuer_mode": "per_provider",
        "signing_key": reference.signing_key,
    },
)
provider.redirect_uris = [
    RedirectURI(
        matching_mode=RedirectURIMatchingMode.STRICT,
        url="https://mirrors.maximoraverse.org/auth/callback",
        redirect_uri_type=RedirectURIType.AUTHORIZATION,
    )
]
provider.save()
provider.property_mappings.set(reference.property_mappings.all())

Application.objects.update_or_create(
    slug="matchall-mirrors",
    defaults={
        "name": "MatchAll Mirrors",
        "provider": provider,
        "meta_launch_url": "https://mirrors.maximoraverse.org/login",
        "meta_description": "软件版本发布、更新检查与高速下载平台",
        "meta_publisher": "MatchAll",
        "open_in_new_tab": False,
    },
)

print("configured MatchAll Mirrors OIDC")
