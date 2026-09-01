from __future__ import annotations

import os
from datetime import UTC, datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for

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

    @app.get("/")
    def index():
        if not client.api_key:
            return render_template(
                "index.html",
                collections=[],
                error="環境変数 CIVIT_API_KEY が設定されていません。",
            )
        try:
            collections = client.get_model_collections()
            return render_template("index.html", collections=collections, error=None)
        except CivitaiError as exc:
            return render_template("index.html", collections=[], error=str(exc)), exc.status_code

    @app.get("/collections/<int:collection_id>/thumbnail")
    def collection_thumbnail(collection_id: int):
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

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "ページが見つかりません。"}), 404

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5055"))
    app.run(host="127.0.0.1", port=port, debug=False)
