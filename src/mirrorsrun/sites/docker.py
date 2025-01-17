import base64
import json
import logging
import re
import time
from typing import Dict

import httpx
from starlette.requests import Request
from starlette.responses import Response

from mirrorsrun.proxy.direct import direct_proxy
from mirrorsrun.proxy.file_cache import try_file_based_cache

logger = logging.getLogger(__name__)

BASE_URL = "https://registry-1.docker.io"


class CachedToken:
    token: str
    exp: int

    def __init__(self, token, exp):
        self.token = token
        self.exp = exp


cached_tokens: Dict[str, CachedToken] = {}

# https://github.com/opencontainers/distribution-spec/blob/main/spec.md
name_regex = "[a-z0-9]+((.|_|__|-+)[a-z0-9]+)*(/[a-z0-9]+((.|_|__|-+)[a-z0-9]+)*)*"
reference_regex = "[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127}"


def try_extract_image_name(path):
    pattern = r"^/v2/(.*)/([a-zA-Z]+)/(.*)$"
    match = re.search(pattern, path)

    if match:
        assert len(match.groups()) == 3
        name, resource, reference = match.groups()
        assert re.match(name_regex, name)
        assert re.match(reference_regex, reference)
        assert resource in ["manifests", "blobs", "tags"]
        return name, resource, reference

    return None, None, None


def get_docker_token(name):
    cached = cached_tokens.get(name, None)
    if cached and cached.exp > time.time():
        return cached.token

    url = "https://auth.docker.io/token"
    params = {
        "scope": f"repository:{name}:pull",
        "service": "registry.docker.io",
    }

    client = httpx.Client()
    response = client.get(url, params=params)
    response.raise_for_status()

    token_data = response.json()
    token = token_data["token"]
    payload = token.split(".")[1]
    padding = len(payload) % 4
    payload += "=" * padding

    payload = json.loads(base64.b64decode(payload))
    assert payload["iss"] == "auth.docker.io"
    assert len(payload["access"]) > 0

    cached_tokens[name] = CachedToken(exp=payload["exp"], token=token)

    return token


def inject_token(name: str, req: Request, httpx_req: httpx.Request):
    docker_token = get_docker_token(f"{name}")
    httpx_req.headers["Authorization"] = f"Bearer {docker_token}"
    return httpx_req


async def post_process(request: Request, response: Response):
    if response.status_code == 307:
        location = response.headers["location"]
        return await try_file_based_cache(request, location)

    return response


async def docker(request: Request):
    path = request.url.path
    if not path.startswith("/v2/"):
        return Response(content="Not Found", status_code=404)

    if path == "/v2/":
        return Response(content="OK")
        # return await direct_proxy(request, BASE_URL + '/v2/')

    name, resource, reference = try_extract_image_name(path)

    if not name:
        return Response(content="404 Not Found", status_code=404)

    # support docker pull xxx which name without library
    if "/" not in name:
        name = f"library/{name}"

    target_url = BASE_URL + f"/v2/{name}/{resource}/{reference}"

    logger.info(f"got docker request, {path=} {name=} {resource=} {reference=} {target_url=}")

    return await direct_proxy(
        request,
        target_url,
        pre_process=lambda req, http_req: inject_token(name, req, http_req),
        post_process=post_process,
    )
