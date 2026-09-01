# Civitai Collection Lens

Civitaiの自分のモデルコレクション（Public・Private）を複数選択し、モデル名・ファイル名で絞り込みながら、収録モデルのバージョン、ファイル名、トリガーワードを確認・JSONコピーするローカルWebアプリです。

## 起動

1. CivitaiのAPIキーを環境変数 `CIVIT_API_KEY` に設定します。
2. `run.bat` を実行します。
3. ブラウザーで `http://127.0.0.1:5055` を開きます。

初回起動時は `.venv` を作成し、必要なPythonパッケージをインストールします。APIキーはFlaskサーバーからCivitai公式ドメインの `civitai.com` と `civitai.red` へ送信され、ブラウザーへは渡されません。`civitai.red` は成熟コンテンツを含むコレクション内容の取得に使用します。

PowerShellで現在のウィンドウだけにキーを設定する例:

```powershell
$env:CIVIT_API_KEY = "your-api-key"
.\run.bat
```

別のポートで起動する場合:

```powershell
.\run.bat 5056
```

## 結合テスト

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

テストはFlaskアプリと疑似Civitai HTTPサーバーを実際のローカルポートで起動し、ブラウザー相当のHTTPリクエストから認証、ページング、複数選択、ファイル情報、サムネイルを検証します。

## 注意

コレクション一覧・アイテム取得にはCivitaiサイト内部のtRPC APIを使用しています。非公開仕様のため、Civitai側の変更により動作しなくなる場合があります。

接続先を変更する場合は、環境変数 `CIVITAI_BASE_URL` と `CIVITAI_MATURE_BASE_URL` で個別に指定できます。
