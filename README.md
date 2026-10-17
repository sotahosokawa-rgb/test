# boatrace research data pipeline

公式サイトの成績(K)・出走表(B)ファイルを低頻度で取得し、age で暗号化して保存する。
データは私的な分析専用。復号鍵はリポジトリ外で管理する。

- `.github/workflows/backfill.yml`: 過去分(scripts/backfill_request.txt の期間)を月単位で取得
- `.github/workflows/daily.yml`: 毎日 00:30 / 06:30 JST に直近分を取得
- `data/lzh/YYYYMM.tar.age`, `data/daily/{K,B}/YYYYMMDD.tar.age`: 暗号化済みデータ
