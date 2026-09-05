from __future__ import annotations

import os
from datetime import UTC, datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for

from catalog_store import CatalogStore
from civitai_client import CivitaiClient, CivitaiError


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        CIVITAI_API_KEY=os.environ.get("CIVIT_API_KEY", ""),
        CIVITAI_BASE_URL=os.environ.get("CIVITAI_BASE_URL", "https://civitai.com"),
        CIVITAI_MATURE_BASE_URL=os.environ.get(
            "CIVITAI_MATURE_BASE_URL", "https://civitai.red"
        ),
        CIVITAI_TIMEOUT=float(os.environ.get("CIVITAI_TIMEOUT", "20")),
        CIVITAI_CATALOG_PATH=os.environ.get(
            "CIVITAI_CATALOG_PATH", os.path.join("data", "model_catalog.json")
        ),
        USE_PERSISTENT_CATALOG=True,
        START_CATALOG_SYNC=False,
        MAX_SELECTED_COLLECTIONS=20,
    )
    if config:
        app.config.update(config)

    client = CivitaiClient(
        api_key=app.config["CIVITAI_API_KEY"],
        base_url=app.config["CIVITAI_BASE_URL"],
        mature_base_url=app.config["CIVITAI_MATURE_BASE_URL"],
        timeout=float(app.config["CIVITAI_TIMEOUT"]),
    )
    app.extensions["civitai_client"] = client
    catalog_store = CatalogStore(client, app.config["CIVITAI_CATALOG_PATH"])
    app.extensions["catalog_store"] = catalog_store

    @app.get("/")
    def index():
        if not client.api_key:
            return render_template(
                "index.html",
                collections=[],
                error="環境変数 CIVIT_API_KEY が設定されていません。",
            )
        if app.config["USE_PERSISTENT_CATALOG"]:
            status = catalog_store.status()
            collections = catalog_store.collections_for_ui()
            error = status["error"] if status["state"] == "error" and not collections else None
            return render_template(
                "index.html",
                collections=collections,
                error=error,
                catalog_status=status,
            )
        try:
            collections = client.get_model_collections()
            return render_template(
                "index.html", collections=collections, error=None, catalog_status=None
            )
        except CivitaiError as exc:
            return (
                render_template(
                    "index.html",
                    collections=[],
                    error=str(exc),
                    catalog_status=None,
                ),
                exc.status_code,
            )

    @app.get("/collections/<int:collection_id>/thumbnail")
    def collection_thumbnail(collection_id: int):
        if app.config["USE_PERSISTENT_CATALOG"]:
            collection = next(
                (
                    item
                    for item in catalog_store.collections_for_ui()
                    if int(item["id"]) == collection_id
                ),
                None,
            )
            if collection and collection.get("thumbnailUrl"):
                return redirect(collection["thumbnailUrl"])
            return redirect(url_for("static", filename="collection-placeholder.svg"))
        try:
            image_url = client.get_collection_thumbnail(collection_id)
        except CivitaiError as exc:
            if exc.status_code == 404:
                return redirect(url_for("static", filename="collection-placeholder.svg"))
            return redirect(url_for("static", filename="collection-placeholder.svg"))
        if not image_url:
            return redirect(url_for("static", filename="collection-placeholder.svg"))
        return redirect(image_url)

    @app.post("/api/selection")
    def export_selection():
        payload = request.get_json(silent=True) or {}
        raw_ids = payload.get("collectionIds")
        if not isinstance(raw_ids, list):
            return jsonify({"error": "collectionIdsは配列で指定してください。"}), 400

        try:
            collection_ids = list(dict.fromkeys(int(value) for value in raw_ids))
        except (TypeError, ValueError):
            return jsonify({"error": "コレクションIDが不正です。"}), 400

        if not collection_ids or any(value <= 0 for value in collection_ids):
            return jsonify({"error": "コレクションを1件以上選択してください。"}), 400
        if len(collection_ids) > app.config["MAX_SELECTED_COLLECTIONS"]:
            return jsonify(
                {
                    "error": (
                        f"一度に選択できるのは"
                        f"{app.config['MAX_SELECTED_COLLECTIONS']}件までです。"
                    )
                }
            ), 400

        try:
            if app.config["USE_PERSISTENT_CATALOG"]:
                stored = catalog_store.selected_collections(collection_ids)
                collections = [
                    {
                        "id": collection["id"],
                        "name": collection["name"],
                        "items": collection.get("items", []),
                    }
                    for collection in stored
                ]
            else:
                collections = client.export_collections(collection_ids)
        except CivitaiError as exc:
            return jsonify({"error": str(exc)}), exc.status_code

        files = []
        seen_file_names = set()
        for collection in collections:
            for item in collection["items"]:
                for file in item["files"]:
                    name = file.get("name")
                    if name and name not in seen_file_names:
                        seen_file_names.add(name)
                        files.append({"name": name})

        return jsonify(
            {
                "generatedAt": datetime.now(UTC).isoformat(),
                "files": files,
                "collections": collections,
            }
        )

    @app.get("/api/catalog/status")
    def catalog_status():
        return jsonify(catalog_store.status())

    @app.post("/api/catalog/sync")
    def sync_catalog():
        if not client.api_key:
            return jsonify({"error": "CIVIT_API_KEYが設定されていません。"}), 400
        started = catalog_store.start_sync()
        return jsonify(catalog_store.status()), 202 if started else 200

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "ページが見つかりません。"}), 404

    if app.config["START_CATALOG_SYNC"] and client.api_key:
        catalog_store.start_sync()

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5055"))
    if app.extensions["civitai_client"].api_key:
        app.extensions["catalog_store"].start_sync()
    app.run(host="127.0.0.1", port=port, debug=False)
