# factorio-blueprints

Factorio（バニラ）の生産ライン Blueprint を、コードで組み立てて実機で検証するためのリポジトリ。

```bash
scripts/setup.sh              # 依存の導入、ヘッドレス版 Factorio の取得、バニラデータへの切り替え
uv run fbp sim green-circuits # ビルド → 静的検証 → ヘッドレス実機で生産量を実測
```

ゲームに貼り付ける文字列は `blueprints/<name>/blueprint.txt`。使い方と規約は `CLAUDE.md`。
