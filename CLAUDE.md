# factorio-blueprints

Factorio の Blueprint を「コードで組み立て → 静的検証 → 実機シミュレーションで実測」して作るリポジトリ。
対象は **バニラ（base mod のみ、Space Age / Quality なし）**、主題は生産ライン。

## 最初に

```bash
uv run fbp info          # ゲームデータの版とヘッドレス版の有無を表示
scripts/setup.sh         # 「mods: base」以外が出る／headless が MISSING のときに実行（再実行可）
```

`fbp info` が示す版（現在 2.1.x）のデータが唯一の正。**レシピ時間・機械速度・寸法・搬送量を記憶から書かない**。
必ず下の参照コマンドで引く（記憶と実データが食い違う例が実際にある）。

## コマンド（すべて `uv run fbp ...`）

| 目的 | コマンド |
| --- | --- |
| 必要台数・原料量の計算 | `fbp rates <item> <毎分> [--stop-at iron-plate] [--machine crafting=assembling-machine-3] [--module productivity-module=2]` |
| レシピ／エンティティのデータ | `fbp recipe <名前>` / `fbp entity <名前>`（寸法・流体ポート位置・速度） / `fbp search <文字列>` |
| ビルド＋静的検証＋プレビュー出力 | `fbp build <name>` |
| 実機シミュレーション（ビルド込み） | `fbp sim <name>`（約10秒。`--json` で全データ、`--keep DIR` でログ保存） |
| 既存の文字列を調べる | `fbp decode` / `fbp validate` / `fbp render <file か ->` |
| テスト | `uv run pytest -q` |

## Blueprint の置き方

```
blueprints/<name>/
  build.py        正本。build() が draftsman の Blueprint を返す（fbp.kit のヘルパーを使う）
  spec.toml       目標（[[target]]）とシミュレーションの入出力（[sim]）
  blueprint.txt   生成物: ゲームに貼り付ける文字列
  preview.txt     生成物: 座標付き ASCII 図   preview.png: 人が見る用の図
```

- **`blueprint.txt` を手で書かない・直接編集しない。** 直すのは `build.py`。生成物は一緒にコミットする
  （テストが build.py と blueprint.txt の一致を確認する）。
- 手本は `blueprints/green-circuits` と `blueprints/red-science`。
- 新規作成・修正の手順は `.claude/skills/blueprint/SKILL.md`。

## 設計方針（既定）

依頼に指定がなければ、**プレイヤーの作業回数が最小になる設計**を選ぶ。

数えるもの:
- Blueprint を貼る回数
- 貼った後に手でつなぐ箇所（ブロック間のベルト・パイプ・電線）
- 建設ロボット入手前に手で置くエンティティの数
- レシピ設定などの手作業（Blueprint に含めて 0 にする）

数えないもの: 古い設備の撤去・置き換え（使わなくなった設備は放置してよい）、資源の消費量、面積、電力。

ここから導く原則:
- 序盤は「建設ロボットを最短で手に入れるための、手置き点数が最小の仮設ライン」。効率は問わない。
- ロボット入手後は、品目ごとに分けず、**関連するラインをまとめた大きな Blueprint 1 枚**にする
  （貼る回数とつなぐ箇所が減る）。内部のベルト・配管・電柱・レシピ・モジュールは全部含める。
- 入力はできるだけ原料（板・石炭・原油など）に寄せ、中間品を外から持ち込ませない。
- 入出力の位置をそろえ、ブロックを並べるだけでつながるようにする。

**曖昧な依頼では質問で止まらない。** この方針と無難な前提（規模は「無理なくロケットまで行ける最小限」、
研究ボーナスなし）で進め、置いた前提を報告に書く。確認が要るのは、方針そのものを変える必要があるときだけ。

報告には、その Blueprint に必要な**作業回数（貼る回数・手でつなぐ箇所・手置き点数）**を必ず書く。

ロケット発射までを通して作るときは `docs/roadmap.md` で進める（手順は `.claude/skills/blueprint/SKILL.md` の
「roadmap の進め方」）。

## 完了の基準

1. `fbp build <name>` が error 0（warning は意図を説明できること）。
2. `preview.txt` を読んで、物の流れが入力から出力までつながっていることを確認。
3. `fbp sim <name>` が PASSED。**目標値は実測で確認できた値だけを書く**（rates の理論値を達成済みとして報告しない）。
4. `uv run pytest -q` が通る。

sim が動かせない環境（headless MISSING）では、その旨を明記して「静的検証のみ・未実測」と報告する。

## 間違えやすい点（このリポジトリで実機確認済み）

- **座標**: `tile_position` は左上タイル。x は右、y は下が正。北は -y。3x3 の機械を (0, 2) に置くと x 0..2, y 2..4 を占有。
- **向き**: Factorio 2.x の direction は 16 方向で N=0, E=4, S=8, W=12（`fbp.kit` の `N/E/S/W` を使う）。
- **インサータ**: ゲーム上の `direction` は「拾う側」。逆に考えやすいので必ず `kit.inserter(bp, tile, moves=S)`
  （物が動く向きで指定）を使う。プレビューの ▲▶▼◀ も物が動く向き。
- **電柱**: Blueprint は保存された銅線しか張らない。最後に `kit.finalize(bp)` を呼ばないと電柱が孤立する。
- **地下ベルト**: 入口 `io_type="input"`、出口 `"output"`、同じ向き・同じ種類。`kit.underground(bp, 入口, 向き, gap)` を使う。
  届く距離は `fbp entity underground-belt` の max_distance（間の空きタイルは max_distance - 1 まで）。
- **流体ポート**は機械の向きで回る。位置は `fbp entity chemical-plant` などで確認する。
- **ボトルネックはたいていインサータ**。レシピ比率どおりに機械を並べても、受け渡しが追いつかず理論値は出ない。
  研究ボーナスなし・2.1.24 の実測目安: インサータ ベルト→機械 約 55 個/分、高速インサータ 機械→機械 約 110 個/分。
  設計値は必ず `fbp sim` の実測で確かめる。
- sim の既定は「全レシピ解放・研究ボーナスなし」（控えめな条件）。全研究済みで測るなら spec.toml の `[sim] research_all = true`。

詳細: `docs/sim.md`（spec.toml と結果の読み方）、`docs/blueprint-format.md`（文字列の中身）。
