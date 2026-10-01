from pathlib import Path
from django.db import transaction
from authentik.core.models import Application
from authentik.flows.models import Flow
from authentik.providers.oauth2.models import OAuth2Provider, RedirectURI, RedirectURIMatchingMode, RedirectURIType

with transaction.atomic():
    ref=OAuth2Provider.objects.get(name='Nextcloud')
    provider,created=OAuth2Provider.objects.get_or_create(name='MatchAll DNS',defaults={
      'authorization_flow':Flow.objects.get(slug='default-provider-authorization-implicit-consent'),
      'invalidation_flow':Flow.objects.get(slug='default-provider-invalidation-flow'),
      'client_type':'confidential','client_id':'matchall-dns',
      'client_secret':Path('/data/matchall-dns-client.secret').read_text().strip(),
      'grant_types':['authorization_code'],'include_claims_in_id_token':True,
      'sub_mode':'user_uuid','issuer_mode':'per_provider','signing_key':ref.signing_key})
    assert created, 'Existing DNS provider: inspect before modifying'
    provider.redirect_uris=[RedirectURI(matching_mode=RedirectURIMatchingMode.STRICT,url='https://dns.maximoraverse.org/auth/callback',redirect_uri_type=RedirectURIType.AUTHORIZATION)]
    provider.save();provider.property_mappings.set(ref.property_mappings.all())
    Application.objects.create(slug='matchall-dns',name='MatchAll DNS',provider=provider,
      meta_launch_url='https://dns.maximoraverse.org/login',meta_description='为每台设备创建独立加密 DNS 令牌',meta_publisher='MatchAll')
print('Created MatchAll DNS OIDC provider/application; no user/group restrictions added')
