from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from werkzeug.serving import make_server

from app import create_app


API_KEY = "integration-secret"

MODEL_VERSIONS = {
    501: {
        "id": 501,
        "name": "v1",
        "trainedWords": ["amber style"],
        "images": [
            {
                "url": (
                    "https://image.civitai.com/example/original=true/amber-v1.jpeg"
                ),
                "width": 768,
                "height": 1024,
            }
        ],
        "files": [
            {
                "id": 7001,
                "name": "amberStyle_v1.safetensors",
                "primary": True,
                "sizeKB": 144000,
                "metadata": {"format": "SafeTensor", "fp": "fp16"},
            }
        ],
    },
    502: {
        "id": 502,
        "name": "v2",
        "trainedWords": ["blue detail"],
        "files": [
            {
                "id": 7002,
                "name": "blueDetail_v2.safetensors",
                "primary": True,
                "sizeKB": 72000,
                "metadata": {"format": "SafeTensor"},
            }
        ],
    },
    503: {
        "id": 503,
        "name": "release",
        "trainedWords": ["cobalt", "silver eyes"],
        "files": [
            {
                "id": 7003,
                "name": "cobaltCharacter.safetensors",
                "primary": True,
                "sizeKB": 80000,
                "metadata": {"format": "SafeTensor"},
            },
            {
                "id": 7004,
                "name": "cobaltCharacter.preview.png",
                "primary": False,
                "sizeKB": 512,
                "metadata": {"format": "Other"},
            },
        ],
    },
    504: {
        "id": 504,
        "name": "v1",
        "trainedWords": ["pov trigger"],
        "images": [
            {
                "type": "video",
                "url": "https://image.civitai.com/example/original=true/mature.mp4",
                "width": 768,
                "height": 1024,
            },
            {
                "type": "image",
                "url": "https://image.civitai.com/example/original=true/mature.jpeg",
                "width": 832,
                "height": 1216,
            },
        ],
        "files": [
            {
                "id": 7005,
                "name": "maturePov_v1.safetensors",
                "primary": True,
                "sizeKB": 64000,
                "metadata": {"format": "SafeTensor", "fp": "fp16"},
            }
        ],
    },
    505: {
        "id": 505,
        "name": "legacy",
        "trainedWords": ["amber legacy"],
        "images": [
            {
                "url": "https://images.example.test/models/amber-legacy.jpeg",
                "width": 1024,
                "height": 768,
            }
        ],
        "files": [
            {
                "id": 7006,
                "name": "amberStyle_legacy.safetensors",
                "primary": True,
                "sizeKB": 128000,
                "metadata": {"format": "SafeTensor", "fp": "fp16"},
            }
        ],
    },
}

MODEL_VERSION_IDS = {
    1001: [501, 505],
    1002: [502],
    2001: [503],
    3001: [504],
}


def trpc(data):
    return {"result": {"data": {"json": data}}}


class FakeCivitaiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    model_attempts = {}
    model_attempts_lock = threading.Lock()

    def log_message(self, format, *args):
        return

    def send_json(self, payload, status=200, headers=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {API_KEY}":
            self.send_json({"error": "Unauthorized"}, status=401)
            return

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/api/trpc/collection.getAllUser":
            self.send_json(
                trpc(
                    [
                        {
                            "id": 11,
                            "name": "Private Styles",
                            "description": "Style models",
                            "read": "Private",
                            "type": "Model",
                            "imageId": None,
                        },
                        {
                            "id": 22,
                            "name": "Private Characters",
                            "description": "Character models",
                            "read": "Private",
                            "type": "Model",
                            "imageId": 9002,
                        },
                        {
                            "id": 33,
                            "name": "Public NSFW Models",
                            "description": "Public model collection",
                            "read": "Public",
                            "type": "Model",
                            "imageId": None,
                        },
                        {
                            "id": 44,
                            "name": "Private Articles",
                            "description": "Article bookmarks",
                            "read": "Private",
                            "type": "Article",
                            "imageId": None,
                        },
                    ]
                )
            )
            return

        if parsed.path == "/api/trpc/collection.getAllCollectionItems":
            request_input = json.loads(query["input"][0])["json"]
            collection_id = request_input["collectionId"]
            cursor = request_input.get("cursor")
            is_mature_domain = getattr(self.server, "is_mature_domain", False)

            if collection_id == 33:
                if not is_mature_domain or request_input.get("browsingLevel") != 31:
                    self.send_json(
                        trpc({"nextCursor": None, "collectionItems": []})
                    )
                    return
                self.send_json(
                    trpc(
                        {
                            "nextCursor": None,
                            "collectionItems": [
                                {
                                    "id": 301,
                                    "type": "model",
                                    "data": {
                                        "id": 3001,
                                        "name": "Mature POV",
                                        "version": {
                                            "id": 504,
                                            "name": "v1",
                                            "trainedWords": ["pov trigger"],
                                        },
                                        "images": [],
                                    },
                                }
                            ],
                        }
                    )
                )
                return

            if collection_id == 11 and cursor is None:
                self.send_json(
                    trpc(
                        {
                            "nextCursor": "102",
                            "collectionItems": [
                                {
                                    "id": 101,
                                    "type": "model",
                                    "data": {
                                        "id": 1001,
                                        "name": "Amber Style",
                                        "version": {
                                            "id": 501,
                                            "name": "v1",
                                            "trainedWords": ["amber style"],
                                        },
                                        "images": [{"id": 9001}],
                                    },
                                }
                            ],
                        }
                    )
                )
                return

            if collection_id == 11 and cursor == "102":
                self.send_json(
                    trpc(
                        {
                            "nextCursor": None,
                            "collectionItems": [
                                {
                                    "id": 102,
                                    "type": "model",
                                    "data": {
                                        "id": 1002,
                                        "name": "Blue Detail",
                                        "version": {
                                            "id": 502,
                                            "name": "v2",
                                            "trainedWords": ["blue detail"],
                                        },
                                        "images": [],
                                    },
                                }
                            ],
                        }
                    )
                )
                return

            if collection_id == 22:
                self.send_json(
                    trpc(
                        {
                            "nextCursor": None,
                            "collectionItems": [
                                {
                                    "id": 201,
                                    "type": "model",
                                    "data": {
                                        "id": 2001,
                                        "name": "Cobalt Character",
                                        "version": {
                                            "id": 503,
                                            "name": "release",
                                            "trainedWords": ["cobalt", "silver eyes"],
                                        },
                                        "images": [],
                                    },
                                }
                            ],
                        }
                    )
                )
                return

        if parsed.path.startswith("/api/v1/models/"):
            model_id = int(parsed.path.rsplit("/", 1)[1])
            with self.model_attempts_lock:
                attempts = self.model_attempts.get(model_id, 0) + 1
                self.model_attempts[model_id] = attempts
            if model_id == 1001 and attempts == 1:
                self.send_json(
                    {"error": "Rate limited"},
                    status=429,
                    headers={"Retry-After": "0"},
                )
                return
            self.send_json(
                {
                    "id": model_id,
                    "modelVersions": [
                        MODEL_VERSIONS[version_id]
                        for version_id in MODEL_VERSION_IDS[model_id]
                    ],
                }
            )
            return

        if parsed.path.startswith("/api/v1/model-versions/"):
            version_id = int(parsed.path.rsplit("/", 1)[1])
            self.send_json(MODEL_VERSIONS[version_id])
            return

        if parsed.path == "/api/v1/images":
            image_id = int(query["imageId"][0])
            self.send_json(
                {
                    "items": [
                        {
                            "id": image_id,
                            "url": f"https://images.example.test/{image_id}.jpeg",
                        }
                    ],
                    "metadata": {},
                }
            )
            return

        self.send_json({"error": "Not found"}, status=404)


@contextmanager
def running_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture
def live_app():
    FakeCivitaiHandler.model_attempts = {}
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeCivitaiHandler)
    upstream_url = f"http://127.0.0.1:{upstream.server_port}"
    mature_upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeCivitaiHandler)
    mature_upstream.is_mature_domain = True
    mature_upstream_url = f"http://127.0.0.1:{mature_upstream.server_port}"

    app = create_app(
        {
            "TESTING": True,
            "CIVITAI_API_KEY": API_KEY,
            "CIVITAI_BASE_URL": upstream_url,
            "CIVITAI_MATURE_BASE_URL": mature_upstream_url,
            "CIVITAI_TIMEOUT": 2,
            "USE_PERSISTENT_CATALOG": False,
        }
    )
    web = make_server("127.0.0.1", 0, app, threaded=True)
    web_url = f"http://127.0.0.1:{web.server_port}"

    with running_server(upstream), running_server(mature_upstream), running_server(web):
        yield web_url


def test_private_collections_are_selectable_from_the_browser(live_app):
    response = requests.get(live_app, timeout=3)

    assert response.status_code == 200
    assert "Private Styles" in response.text
    assert "Private Characters" in response.text
    assert 'value="11"' in response.text
    assert 'value="22"' in response.text
    assert "/collections/11/thumbnail" in response.text
    assert "ファイル情報を表示" not in response.text
    assert 'id="selection-status"' in response.text


def test_public_model_collections_are_shown_but_article_collections_are_not(live_app):
    response = requests.get(live_app, timeout=3)

    assert response.status_code == 200
    assert "Public NSFW Models" in response.text
    assert 'value="33"' in response.text
    assert "PUBLIC" in response.text
    assert "Private Articles" not in response.text


def test_browser_exposes_collection_then_item_selection_before_results(live_app):
    response = requests.get(live_app, timeout=3)

    assert response.status_code == 200
    assert 'id="item-picker"' in response.text
    assert 'id="item-select-all"' in response.text
    assert 'id="item-clear-all"' in response.text
    assert 'id="selected-results"' in response.text
    assert "アイテムを選択" in response.text


def test_browser_exposes_realtime_model_and_filename_search_without_submit_button(
    live_app,
):
    response = requests.get(live_app, timeout=3)

    assert response.status_code == 200
    assert 'type="search"' in response.text
    assert 'id="item-search"' in response.text
    assert 'id="global-search"' in response.text
    assert 'placeholder="モデル名・ファイル名で検索"' in response.text
    assert 'id="item-search-button"' not in response.text
    item_tools = response.text.split('id="item-selection-tools"', 1)[1].split(
        'id="item-picker-empty"', 1
    )[0]
    assert 'id="item-search"' not in item_tools


def test_browser_exposes_named_selection_template_controls(live_app):
    response = requests.get(live_app, timeout=3)

    assert response.status_code == 200
    assert 'id="template-name"' in response.text
    assert 'placeholder="テンプレート名"' in response.text
    assert 'id="template-save"' in response.text
    assert 'id="template-list"' in response.text
    assert 'id="template-load"' in response.text
    assert 'id="template-delete"' in response.text


def test_browser_exposes_explicit_catalog_sync_and_blocking_progress_overlay(live_app):
    response = requests.get(live_app, timeout=3)

    assert response.status_code == 200
    assert 'id="catalog-sync"' in response.text
    assert 'id="catalog-loading-overlay"' in response.text
    assert 'id="catalog-progress"' in response.text
    assert 'id="catalog-progress-message"' in response.text


def test_multiple_collections_export_filenames_and_trained_words(live_app):
    response = requests.post(
        f"{live_app}/api/selection",
        json={"collectionIds": [11, 22]},
        timeout=5,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [collection["name"] for collection in payload["collections"]] == [
        "Private Styles",
        "Private Characters",
    ]
    assert payload["files"] == [
        {"name": "amberStyle_v1.safetensors"},
        {"name": "blueDetail_v2.safetensors"},
        {"name": "cobaltCharacter.safetensors"},
        {"name": "cobaltCharacter.preview.png"},
    ]
    assert payload["collections"][0]["items"][0]["modelUrl"] == (
        "https://civitai.com/models/1001?modelVersionId=501"
    )
    assert payload["collections"][0]["items"][0]["versions"] == [
        {
            "versionId": 501,
            "versionName": "v1",
            "modelUrl": "https://civitai.com/models/1001?modelVersionId=501",
            "thumbnailUrl": "https://image.civitai.com/example/width=450/amber-v1.jpeg",
            "thumbnailWidth": 768,
            "thumbnailHeight": 1024,
            "trainedWords": ["amber style"],
            "files": [
                {
                    "id": 7001,
                    "name": "amberStyle_v1.safetensors",
                    "primary": True,
                    "sizeKB": 144000,
                    "format": "SafeTensor",
                    "precision": "fp16",
                }
            ],
        },
        {
            "versionId": 505,
            "versionName": "legacy",
            "modelUrl": "https://civitai.com/models/1001?modelVersionId=505",
            "thumbnailUrl": "https://images.example.test/models/amber-legacy.jpeg",
            "thumbnailWidth": 1024,
            "thumbnailHeight": 768,
            "trainedWords": ["amber legacy"],
            "files": [
                {
                    "id": 7006,
                    "name": "amberStyle_legacy.safetensors",
                    "primary": True,
                    "sizeKB": 128000,
                    "format": "SafeTensor",
                    "precision": "fp16",
                }
            ],
        },
    ]
    assert [
        {
            key: value
            for key, value in item.items()
            if key
            not in {"versions", "thumbnailUrl", "thumbnailWidth", "thumbnailHeight"}
        }
        for item in payload["collections"][0]["items"]
    ] == [
        {
            "modelId": 1001,
            "modelName": "Amber Style",
            "versionId": 501,
            "versionName": "v1",
            "modelUrl": "https://civitai.com/models/1001?modelVersionId=501",
            "trainedWords": ["amber style"],
            "files": [
                {
                    "id": 7001,
                    "name": "amberStyle_v1.safetensors",
                    "primary": True,
                    "sizeKB": 144000,
                    "format": "SafeTensor",
                    "precision": "fp16",
                }
            ],
        },
        {
            "modelId": 1002,
            "modelName": "Blue Detail",
            "versionId": 502,
            "versionName": "v2",
            "modelUrl": "https://civitai.com/models/1002?modelVersionId=502",
            "trainedWords": ["blue detail"],
            "files": [
                {
                    "id": 7002,
                    "name": "blueDetail_v2.safetensors",
                    "primary": True,
                    "sizeKB": 72000,
                    "format": "SafeTensor",
                    "precision": None,
                }
            ],
        },
    ]
    assert payload["collections"][0]["items"][1]["versions"] == [
        {
            "versionId": 502,
            "versionName": "v2",
            "modelUrl": "https://civitai.com/models/1002?modelVersionId=502",
            "thumbnailUrl": None,
            "thumbnailWidth": None,
            "thumbnailHeight": None,
            "trainedWords": ["blue detail"],
            "files": [
                {
                    "id": 7002,
                    "name": "blueDetail_v2.safetensors",
                    "primary": True,
                    "sizeKB": 72000,
                    "format": "SafeTensor",
                    "precision": None,
                }
            ],
        }
    ]
    assert payload["collections"][1]["items"][0]["trainedWords"] == [
        "cobalt",
        "silver eyes",
    ]
    assert [
        file["name"] for file in payload["collections"][1]["items"][0]["files"]
    ] == ["cobaltCharacter.safetensors", "cobaltCharacter.preview.png"]


def test_selection_includes_version_aware_model_thumbnails(live_app):
    response = requests.post(
        f"{live_app}/api/selection",
        json={"collectionIds": [11]},
        timeout=5,
    )

    assert response.status_code == 200
    item = response.json()["collections"][0]["items"][0]
    assert item["thumbnailUrl"] == (
        "https://image.civitai.com/example/width=450/amber-v1.jpeg"
    )
    assert item["thumbnailWidth"] == 768
    assert item["thumbnailHeight"] == 1024
    assert item["versions"][1]["thumbnailUrl"] == (
        "https://images.example.test/models/amber-legacy.jpeg"
    )


def test_nsfw_collection_uses_mature_domain_and_exports_models(live_app):
    response = requests.post(
        f"{live_app}/api/selection",
        json={"collectionIds": [33]},
        timeout=5,
    )

    assert response.status_code == 200
    collection = response.json()["collections"][0]
    assert collection["name"] == "Public NSFW Models"
    assert [
        {
            key: value
            for key, value in item.items()
            if key
            not in {"versions", "thumbnailUrl", "thumbnailWidth", "thumbnailHeight"}
        }
        for item in collection["items"]
    ] == [
        {
            "modelId": 3001,
            "modelName": "Mature POV",
            "versionId": 504,
            "versionName": "v1",
            "modelUrl": "https://civitai.com/models/3001?modelVersionId=504",
            "trainedWords": ["pov trigger"],
            "files": [
                {
                    "id": 7005,
                    "name": "maturePov_v1.safetensors",
                    "primary": True,
                    "sizeKB": 64000,
                    "format": "SafeTensor",
                    "precision": "fp16",
                }
            ],
        }
    ]
    assert collection["items"][0]["versions"][0]["versionId"] == 504


def test_nsfw_model_thumbnail_skips_video_media(live_app):
    response = requests.post(
        f"{live_app}/api/selection",
        json={"collectionIds": [33]},
        timeout=5,
    )

    assert response.status_code == 200
    item = response.json()["collections"][0]["items"][0]
    assert item["thumbnailUrl"] == (
        "https://image.civitai.com/example/width=450/mature.jpeg"
    )
    assert item["thumbnailWidth"] == 832
    assert item["thumbnailHeight"] == 1216


def test_collection_thumbnail_redirects_to_civitai_image(live_app):
    response = requests.get(
        f"{live_app}/collections/11/thumbnail",
        allow_redirects=False,
        timeout=5,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "https://images.example.test/9001.jpeg"


def test_catalog_is_persisted_on_startup_and_only_resynced_explicitly():
    FakeCivitaiHandler.model_attempts = {}
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeCivitaiHandler)
    upstream_url = f"http://127.0.0.1:{upstream.server_port}"
    mature_upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeCivitaiHandler)
    mature_upstream.is_mature_domain = True
    mature_upstream_url = f"http://127.0.0.1:{mature_upstream.server_port}"
    catalog_path = Path("pytest-cache-files-catalog-model.json").resolve()
    catalog_path.unlink(missing_ok=True)
    app = create_app(
        {
            "TESTING": True,
            "CIVITAI_API_KEY": API_KEY,
            "CIVITAI_BASE_URL": upstream_url,
            "CIVITAI_MATURE_BASE_URL": mature_upstream_url,
            "CIVITAI_TIMEOUT": 2,
            "CIVITAI_CATALOG_PATH": str(catalog_path),
            "USE_PERSISTENT_CATALOG": True,
            "START_CATALOG_SYNC": True,
        }
    )
    web = make_server("127.0.0.1", 0, app, threaded=True)
    web_url = f"http://127.0.0.1:{web.server_port}"

    with running_server(upstream), running_server(mature_upstream), running_server(web):
        deadline = time.monotonic() + 8
        status = {}
        while time.monotonic() < deadline:
            response = requests.get(f"{web_url}/api/catalog/status", timeout=3)
            assert response.status_code == 200
            status = response.json()
            if status["state"] == "ready":
                break
            time.sleep(0.05)

        assert status["state"] == "ready"
        assert status["completed"] == status["total"]
        assert catalog_path.exists()
        saved = json.loads(catalog_path.read_text(encoding="utf-8"))
        assert saved["schemaVersion"] == 1
        assert [collection["name"] for collection in saved["collections"]] == [
            "Private Styles",
            "Private Characters",
            "Public NSFW Models",
        ]
        assert saved["collections"][0]["items"][0]["versions"][1]["files"][0][
            "name"
        ] == "amberStyle_legacy.safetensors"

        first_generation = status["generation"]
        requests.get(web_url, timeout=3)
        reloaded_status = requests.get(
            f"{web_url}/api/catalog/status", timeout=3
        ).json()
        assert reloaded_status["generation"] == first_generation
        assert reloaded_status["state"] == "ready"

        sync_response = requests.post(f"{web_url}/api/catalog/sync", timeout=3)
        assert sync_response.status_code == 202
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            status = requests.get(
                f"{web_url}/api/catalog/status", timeout=3
            ).json()
            if status["state"] == "ready" and status["generation"] > first_generation:
                break
            time.sleep(0.05)

        assert status["state"] == "ready"
        assert status["generation"] == first_generation + 1
        assert status["changes"] == {"added": 0, "removed": 0, "updated": 0}
    catalog_path.unlink(missing_ok=True)
