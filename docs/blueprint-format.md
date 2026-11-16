# Blueprint 文字列の中身（Factorio 2.x）

通常は draftsman と `fbp.kit` が扱うので意識しなくてよい。既存の文字列を調べるときの参考。

- 文字列 = 版を表す `0` + base64( zlib( JSON ) )。`fbp decode` / `fbp encode` で相互変換。
- JSON の最上位は `{"blueprint": {...}}`（本なら `blueprint_book`。`fbp` の検証・sim は単体の blueprint のみ対応）。
- `entities[]`: `entity_number`（1 始まり）、`name`、`position`（**中心座標**。1x1 なら x+0.5、3x3 なら左上+1.5）、
  `direction`（0..15。N=0, E=4, S=8, W=12。省略時 0）、`recipe`、`items`（モジュール要求）、
  地下ベルトの `type`（"input" は省略される／"output"）、`mirror`（流体ポートの左右反転）。
- `wires[]`: `[entity_a, connector_a, entity_b, connector_b]`。電柱の銅線はコネクタ 5。
  回路線は 1（赤）/ 2（緑）、コンビネータ出力側は 3 / 4。
- インサータの `direction` は拾う側を向く。プロトタイプの pickup_position / insert_position を
  direction で回転した位置が、拾う・置くタイルになる（`fbp entity inserter` で確認）。
