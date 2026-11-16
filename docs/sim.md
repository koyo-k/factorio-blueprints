# 実機シミュレーション（`fbp sim`）

ヘッドレス版 Factorio を base mod のみで起動し、何もない平地に Blueprint を建てて実際に動かし、
出力で回収できた量を数える。ハーネスは `src/fbp/sim/control.lua`、起動と判定は `src/fbp/sim/runner.py`。

## 条件

- 全レシピ解放。研究ボーナスは既定でなし（`research_all = true` で全研究済み）。
- 電力は無制限。Blueprint 内の電柱ネットワークごとに電源をつなぐ。電柱が配線されておらず
  ネットワークが2つ以上に分かれていると FAILED になる。
- モジュールは Blueprint の要求どおり挿入済みで始まる。
- 入力は無限に供給、出力は毎 tick 回収。warmup の後、measure の間だけ数える。

## spec.toml

```toml
[[target]]                 # 複数可。出力で回収した量が per_minute × (1 - tolerance) 以上で合格
item = "electronic-circuit"
per_minute = 140
tolerance = 0.05           # 省略時 0.05

[sim]
warmup_ticks = 3600        # 省略時 3600（60 tick = 1 秒）
measure_ticks = 14400      # 省略時 7200
fuel = "coal"              # 燃料式の機械・インサータに自動補給（省略時は補給しない）
research_all = false

[[sim.input]]              # ベルト: そのベルトの後端に品物を置き続ける
kind = "belt"
position = [0, 0]          # Blueprint のタイル座標。そこにあるベルトを使う
left = "iron-plate"        # 進行方向に対して左レーン
right = "copper-plate"     # 右レーン（両レーン同じなら item = "..." だけでよい）
per_minute = 300           # 省略時は満載。left/right 指定時はレーンごと、item 指定時は両レーン合計の上限

[[sim.input]]              # チェスト: 中身を補充し続ける
kind = "chest"
position = [-2, 1]
item = "coal"

[[sim.input]]              # 流体: そのパイプ／タンクを満たし続ける
kind = "fluid"
position = [0, -2]
fluid = "petroleum-gas"

[[sim.output]]             # belt / chest / fluid。そこに届いた物を回収して数える
kind = "belt"
position = [27, 6]
```

## 結果の読み方

- `collected at outputs`: 出力で回収した量（合否はこれで判定）。
- `fed at inputs`: 入力から実際に流れ込んだ量。
- `produced / consumed by machines`: ゲームの生産統計。中間品の流量が分かる。
- `utilisation`: 種類・レシピごとの稼働率と、止まっているときの主な理由（ゲームの entity status 名）。
- `never worked`: 測定中に一度も動かなかったもの。機械なら ERROR、インサータなら WARNING。
- `--json` で個々のエンティティの位置（中心座標）と status の内訳まで出る。
