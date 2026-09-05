from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from civitai_client import CivitaiClient, CivitaiError


class CatalogStore:
    schema_version = 1

    def __init__(self, client: CivitaiClient, path: str | Path):
        self.client = client
        self.path = Path(path).resolve()
        self._lock = threading.RLock()
        self._snapshot = self._read_snapshot()
        self._status: dict[str, Any] = {
            "state": "ready" if self._snapshot else "idle",
            "phase": "待機中",
            "completed": 0,
            "total": 0,
            "message": "保存済みカタログを使用できます" if self._snapshot else "同期待ち",
            "generation": int((self._snapshot or {}).get("generation", 0)),
            "changes": {"added": 0, "updated": 0, "removed": 0},
            "error": None,
        }
        self._thread: threading.Thread | None = None

    def _read_snapshot(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("schemaVersion") != self.schema_version:
            return None
        if not isinstance(payload.get("collections"), list):
            return None
        return payload

    def status(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._status)

    def snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self._snapshot)

    def collections_for_ui(self) -> list[dict[str, Any]]:
        snapshot = self.snapshot() or {}
        return [
            {
                key: collection.get(key)
                for key in (
                    "id",
                    "name",
                    "description",
                    "read",
                    "type",
                    "imageId",
                    "thumbnailUrl",
                )
            }
            for collection in snapshot.get("collections", [])
        ]

    def selected_collections(self, collection_ids: list[int]) -> list[dict[str, Any]]:
        snapshot = self.snapshot()
        if not snapshot:
            raise CivitaiError("モデルカタログを同期中です。", 503)
        available = {
            int(collection["id"]): collection
            for collection in snapshot.get("collections", [])
        }
        unknown = [collection_id for collection_id in collection_ids if collection_id not in available]
        if unknown:
            raise CivitaiError("選択されたモデルコレクションを確認できません。", 400)
        return [deepcopy(available[collection_id]) for collection_id in collection_ids]

    def start_sync(self) -> bool:
        with self._lock:
            if self._status["state"] == "running":
                return False
            self._status.update(
                {
                    "state": "running",
                    "phase": "準備中",
                    "completed": 0,
                    "total": 1,
                    "message": "Civitaiからコレクション一覧を取得しています",
                    "changes": {"added": 0, "updated": 0, "removed": 0},
                    "error": None,
                }
            )
            self._thread = threading.Thread(
                target=self._sync_worker,
                name="civitai-catalog-sync",
                daemon=True,
            )
            self._thread.start()
            return True

    def _set_progress(self, completed: int, total: int, message: str) -> None:
        if message.startswith("コレクション"):
            phase = "コレクション確認中"
        elif message.startswith("サムネイル"):
            phase = "サムネイル確認中"
        else:
            phase = "モデル収集中"
        with self._lock:
            self._status.update(
                {
                    "phase": phase,
                    "completed": completed,
                    "total": max(total, 1),
                    "message": message,
                }
            )

    def _sync_worker(self) -> None:
        try:
            snapshot, changes = self._collect_snapshot()
            self._write_snapshot(snapshot)
            with self._lock:
                self._snapshot = snapshot
                self._status.update(
                    {
                        "state": "ready",
                        "phase": "完了",
                        "completed": self._status["total"],
                        "message": "モデルカタログを更新しました",
                        "generation": snapshot["generation"],
                        "changes": changes,
                        "error": None,
                    }
                )
        except Exception as exc:
            with self._lock:
                self._status.update(
                    {
                        "state": "error",
                        "phase": "同期失敗",
                        "message": "モデルカタログを更新できませんでした",
                        "error": str(exc),
                    }
                )

    def _collect_snapshot(self) -> tuple[dict[str, Any], dict[str, int]]:
        collections = self.client.get_model_collections(refresh=True)
        collection_ids = [int(collection["id"]) for collection in collections]
        if not collection_ids:
            raise CivitaiError("同期できるModelコレクションがありません。")

        exported = self.client.export_collections(
            collection_ids,
            refresh_models=True,
            progress_callback=self._set_progress,
        )
        export_by_id = {int(collection["id"]): collection for collection in exported}
        metadata_by_id = {int(collection["id"]): collection for collection in collections}

        errors = [
            item["error"]
            for collection in exported
            for item in collection.get("items", [])
            if item.get("error")
        ]
        if errors:
            raise CivitaiError(errors[0])

        enriched: list[dict[str, Any]] = []
        for index, collection_id in enumerate(collection_ids, start=1):
            metadata = metadata_by_id[collection_id]
            data = export_by_id[collection_id]
            self._set_progress(
                index,
                len(collection_ids),
                f"サムネイル {index}/{len(collection_ids)} を確認中",
            )
            try:
                thumbnail_url = self.client.get_collection_thumbnail(collection_id)
            except CivitaiError:
                thumbnail_url = None
            enriched.append(
                {
                    "id": collection_id,
                    "name": data["name"],
                    "description": metadata.get("description") or "",
                    "read": metadata.get("read") or "Private",
                    "type": metadata.get("type") or "Model",
                    "imageId": metadata.get("imageId"),
                    "thumbnailUrl": thumbnail_url,
                    "items": data.get("items", []),
                }
            )

        previous = self.snapshot() or {}
        previous_by_id = {
            int(collection["id"]): collection
            for collection in previous.get("collections", [])
        }
        current_by_id = {int(collection["id"]): collection for collection in enriched}
        added = len(current_by_id.keys() - previous_by_id.keys())
        removed = len(previous_by_id.keys() - current_by_id.keys())
        updated = sum(
            current_by_id[collection_id] != previous_by_id[collection_id]
            for collection_id in current_by_id.keys() & previous_by_id.keys()
        )
        generation = int(previous.get("generation", 0)) + 1
        return (
            {
                "schemaVersion": self.schema_version,
                "generation": generation,
                "generatedAt": datetime.now(UTC).isoformat(),
                "collections": enriched,
            },
            {"added": added, "updated": updated, "removed": removed},
        )

    def _write_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
