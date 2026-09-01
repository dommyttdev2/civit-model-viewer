from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import requests


class CivitaiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class CachedValue:
    value: Any
    expires_at: float


class CivitaiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://civitai.com",
        mature_base_url: str = "https://civitai.red",
        timeout: float = 20,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.mature_base_url = mature_base_url.rstrip("/")
        self.timeout = timeout
        self._local = threading.local()
        self._cache: dict[str, CachedValue] = {}
        self._cache_lock = threading.Lock()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "User-Agent": "civitai-collection-viewer/1.0",
                }
            )
            self._local.session = session
        return session

    def _get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        base_url: str | None = None,
    ) -> Any:
        try:
            response = self._session().get(
                f"{base_url or self.base_url}{path}",
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise CivitaiError(f"Civitaiへの接続に失敗しました: {exc}") from exc

        if response.status_code in (401, 403):
            raise CivitaiError(
                "CIVIT_API_KEYが無効か、CollectionsRead権限がありません。",
                response.status_code,
            )
        if response.status_code == 429:
            raise CivitaiError(
                "Civitaiのレート制限に達しました。しばらく待ってから再試行してください。",
                429,
            )
        if not response.ok:
            raise CivitaiError(
                f"Civitai APIがHTTP {response.status_code}を返しました。",
                response.status_code,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise CivitaiError("Civitai APIから不正なJSONが返されました。") from exc

    def _trpc(
        self,
        procedure: str,
        payload: dict[str, Any],
        *,
        base_url: str | None = None,
    ) -> Any:
        envelope = json.dumps({"json": payload}, separators=(",", ":"), ensure_ascii=False)
        body = self._get_json(
            f"/api/trpc/{procedure}",
            params={"input": envelope},
            base_url=base_url,
        )
        try:
            return body["result"]["data"]["json"]
        except (KeyError, TypeError) as exc:
            message = (
                body.get("error", {}).get("json", {}).get("message")
                if isinstance(body, dict)
                else None
            )
            raise CivitaiError(message or "Civitai内部APIの形式が変更されました。") from exc

    def _cache_get(self, key: str) -> Any | None:
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached and cached.expires_at > time.monotonic():
                return cached.value
            self._cache.pop(key, None)
        return None

    def _cache_put(self, key: str, value: Any, ttl: float) -> Any:
        with self._cache_lock:
            self._cache[key] = CachedValue(value, time.monotonic() + ttl)
        return value

    def get_model_collections(self, refresh: bool = False) -> list[dict[str, Any]]:
        cache_key = "model-collections"
        if not refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        collections = self._trpc("collection.getAllUser", {})
        if not isinstance(collections, list):
            raise CivitaiError("コレクション一覧の形式が変更されました。")

        result = [
            {
                "id": int(collection["id"]),
                "name": str(collection.get("name") or "名称未設定"),
                "description": str(collection.get("description") or ""),
                "read": collection.get("read"),
                "type": collection.get("type"),
                "imageId": collection.get("imageId"),
            }
            for collection in collections
            if collection.get("type") in ("Model", None)
        ]
        return self._cache_put(cache_key, result, ttl=60)

    def get_collection_items(
        self, collection_id: int, *, all_pages: bool = True
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()

        for _ in range(1000):
            payload: dict[str, Any] = {
                "collectionId": collection_id,
                "limit": 100,
                # PG through XXX. Blocked content is intentionally excluded.
                "browsingLevel": 31,
            }
            if cursor:
                payload["cursor"] = cursor
            page = self._trpc(
                "collection.getAllCollectionItems",
                payload,
                base_url=self.mature_base_url,
            )
            page_items = page.get("collectionItems", []) if isinstance(page, dict) else []
            if not isinstance(page_items, list):
                raise CivitaiError("コレクションアイテムの形式が変更されました。")
            items.extend(page_items)

            next_cursor = page.get("nextCursor") if isinstance(page, dict) else None
            if not all_pages or not next_cursor:
                break
            cursor = str(next_cursor)
            if cursor in seen_cursors:
                raise CivitaiError("Civitai APIが同じページカーソルを返しました。")
            seen_cursors.add(cursor)
        else:
            raise CivitaiError("コレクションのページ数が安全上限を超えました。")

        return items

    def get_model_version(self, version_id: int) -> dict[str, Any]:
        return self._get_json(f"/api/v1/model-versions/{version_id}")

    def get_model(self, model_id: int) -> dict[str, Any]:
        return self._get_json(f"/api/v1/models/{model_id}")

    def get_image_url(self, image_id: int) -> str | None:
        response = self._get_json(
            "/api/v1/images", params={"imageId": image_id, "limit": 1}
        )
        items = response.get("items", []) if isinstance(response, dict) else []
        if items and isinstance(items[0], dict):
            return items[0].get("url")
        return None

    def get_collection_thumbnail(self, collection_id: int) -> str | None:
        cache_key = f"thumbnail:{collection_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached or None

        collections = self.get_model_collections()
        collection = next((item for item in collections if item["id"] == collection_id), None)
        if collection is None:
            raise CivitaiError("コレクションが見つかりません。", 404)

        image_id = collection.get("imageId")
        if not image_id:
            for item in self.get_collection_items(collection_id, all_pages=False):
                images = item.get("data", {}).get("images", [])
                if images and images[0].get("id"):
                    image_id = images[0]["id"]
                    break

        url = self.get_image_url(int(image_id)) if image_id else None
        return self._cache_put(cache_key, url or "", ttl=600) or None

    def export_collections(self, collection_ids: list[int]) -> list[dict[str, Any]]:
        available = {item["id"]: item for item in self.get_model_collections()}
        unknown = [collection_id for collection_id in collection_ids if collection_id not in available]
        if unknown:
            raise CivitaiError("選択されたモデルコレクションを確認できません。", 400)

        item_sets: dict[int, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=min(6, len(collection_ids))) as executor:
            futures = {
                executor.submit(self.get_collection_items, collection_id): collection_id
                for collection_id in collection_ids
            }
            for future in as_completed(futures):
                item_sets[futures[future]] = future.result()

        model_rows: list[tuple[int, dict[str, Any]]] = []
        for collection_id in collection_ids:
            for item in item_sets[collection_id]:
                if item.get("type") != "model":
                    continue
                data = item.get("data") or {}
                version = data.get("version") or {}
                if data.get("id") and version.get("id"):
                    model_rows.append((collection_id, item))

        model_ids = list(
            dict.fromkeys(int(item["data"]["id"]) for _, item in model_rows)
        )
        models: dict[int, dict[str, Any]] = {}
        model_errors: dict[int, str] = {}
        if model_ids:
            with ThreadPoolExecutor(max_workers=min(8, len(model_ids))) as executor:
                futures = {
                    executor.submit(self.get_model, model_id): model_id
                    for model_id in model_ids
                }
                for future in as_completed(futures):
                    model_id = futures[future]
                    try:
                        models[model_id] = future.result()
                    except CivitaiError as exc:
                        model_errors[model_id] = str(exc)

        fallback_ids: list[int] = []
        for _, item in model_rows:
            data = item["data"]
            current_id = int(data["version"]["id"])
            candidates = models.get(int(data["id"]), {}).get("modelVersions", [])
            if not isinstance(candidates, list) or not any(
                isinstance(candidate, dict) and candidate.get("id") == current_id
                for candidate in candidates
            ):
                fallback_ids.append(current_id)

        fallback_versions: dict[int, dict[str, Any]] = {}
        version_errors: dict[int, str] = {}
        fallback_ids = list(dict.fromkeys(fallback_ids))
        if fallback_ids:
            with ThreadPoolExecutor(max_workers=min(8, len(fallback_ids))) as executor:
                futures = {
                    executor.submit(self.get_model_version, version_id): version_id
                    for version_id in fallback_ids
                }
                for future in as_completed(futures):
                    version_id = futures[future]
                    try:
                        fallback_versions[version_id] = future.result()
                    except CivitaiError as exc:
                        version_errors[version_id] = str(exc)

        def export_version(
            model_id: int,
            detail: dict[str, Any],
            fallback_name: str = "名称未設定",
        ) -> dict[str, Any]:
            version_id = int(detail["id"])
            trained_words = detail.get("trainedWords")
            if not isinstance(trained_words, list):
                trained_words = []
            files = []
            raw_files = detail.get("files")
            if not isinstance(raw_files, list):
                raw_files = []
            for file in raw_files:
                metadata = file.get("metadata") or {}
                files.append(
                    {
                        "id": file.get("id"),
                        "name": file.get("name") or "名称未設定",
                        "primary": bool(file.get("primary")),
                        "sizeKB": file.get("sizeKB"),
                        "format": metadata.get("format"),
                        "precision": metadata.get("fp"),
                    }
                )
            return {
                "versionId": version_id,
                "versionName": str(detail.get("name") or fallback_name),
                "modelUrl": (
                    f"https://civitai.com/models/{model_id}"
                    f"?modelVersionId={version_id}"
                ),
                "trainedWords": [str(word) for word in trained_words],
                "files": files,
            }

        exported_by_collection: dict[int, list[dict[str, Any]]] = {
            collection_id: [] for collection_id in collection_ids
        }
        for collection_id, item in model_rows:
            data = item["data"]
            internal_version = data["version"]
            version_id = int(internal_version["id"])
            model_id = int(data["id"])
            raw_versions = models.get(model_id, {}).get("modelVersions", [])
            if not isinstance(raw_versions, list):
                raw_versions = []
            candidate_versions = [
                export_version(model_id, candidate)
                for candidate in raw_versions
                if isinstance(candidate, dict) and candidate.get("id") is not None
            ]
            selected_version = next(
                (
                    candidate
                    for candidate in candidate_versions
                    if candidate["versionId"] == version_id
                ),
                None,
            )
            if selected_version is None:
                fallback_detail = fallback_versions.get(version_id, {})
                fallback_detail = {
                    **fallback_detail,
                    "id": version_id,
                    "name": fallback_detail.get("name")
                    or internal_version.get("name"),
                    "trainedWords": fallback_detail.get("trainedWords")
                    or internal_version.get("trainedWords")
                    or [],
                }
                selected_version = export_version(
                    model_id,
                    fallback_detail,
                    str(internal_version.get("name") or "名称未設定"),
                )
                candidate_versions.insert(0, selected_version)

            exported = {
                "modelId": model_id,
                "modelName": str(data.get("name") or "名称未設定"),
                **selected_version,
                "versions": candidate_versions,
            }
            if version_id in version_errors:
                exported["error"] = version_errors[version_id]
            elif model_id in model_errors:
                exported["error"] = (
                    "バージョン一覧を取得できませんでした: "
                    f"{model_errors[model_id]}"
                )
            exported_by_collection[collection_id].append(exported)

        return [
            {
                "id": collection_id,
                "name": available[collection_id]["name"],
                "items": exported_by_collection[collection_id],
            }
            for collection_id in collection_ids
        ]
