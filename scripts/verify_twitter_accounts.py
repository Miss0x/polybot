"""verify_twitter_accounts.py — X 账号关联性验证脚本（用户本地运行）

用途：对候选账号逐个调 twitterapi.io，打印昵称/简介/粉丝数/最近 3 条推文，
供人工判断"是否与塞尔维亚选举专题直接相关"。句柄标注 [GUESS] 的是搜索推断、
未被文档证实，若 404 就需要先用 /twitter/tweet/advanced_search 反查真实句柄。

用法：
  python scripts/verify_twitter_accounts.py            # 全部验证
  python scripts/verify_twitter_accounts.py avucic     # 验证单个
成本：每个账号 1 次 profile 调用（$0.00018），非常便宜。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KEY = os.environ.get("TWITTERAPI_IO_KEY", "")
if not KEY:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("TWITTERAPI_IO_KEY="):
            KEY = line.split("=", 1)[1].strip()
            break

# 文档已证实的句柄（Media Landscapes / NIN / 学术论文引用）
DOCUMENTED = ["avucic", "balkaninsight", "AgencijaBeta", "RSE_Balkan", "AJBalkans", "EuropeElects"]
# 搜索推断的句柄（[GUESS]）——人物本身已被证实与专题相关，句柄拼写待 API 确认
GUESSES = [
    "Dojcinovic",        # Stevan Dojčinović, KRIK 主编
    "SlobodanGeorgiev",  # Slobodan Georgiev, 记者
    "dusanmasic",        # Dušan Masić, 调查记者
    "AntonelaRiha",      # Antonela Riha, N1
    "VladimirDjuk",      # Vladimir Đukanović, SNS MP（反向分析对象）
    "AnaBrnabic",        # Ana Brnabić（反向分析对象）
    "PonosZdravko",      # Zdravko Ponoš, 反对派
    "MarinikaTepic",     # Marinika Tepić, 反对派
]

CANDIDATES = [h for h in (sys.argv[1:] or (DOCUMENTED + GUESSES))]


def main() -> None:
    if not KEY:
        print("错误：.env 中没有 TWITTERAPI_IO_KEY")
        sys.exit(1)
    print(f"验证 {len(CANDIDATES)} 个账号（每个 1 次调用，约 ${len(CANDIDATES) * 0.00018:.5f}）\n")
    with httpx.Client(timeout=25.0) as client:
        for handle in CANDIDATES:
            label = f"{handle} [GUESS]" if handle in GUESSES else handle
            try:
                resp = client.get(
                    "https://api.twitterapi.io/twitter/user/info",
                    params={"userName": handle},
                    headers={"X-API-Key": KEY},
                )
                data = resp.json()
            except Exception as exc:
                print(f"= {label}: 请求失败 {exc}")
                continue
            profile = ((data.get("data") or {}) if isinstance(data, dict) else {})
            if not profile.get("userName"):
                print(f"= {label}: 不存在或不可用（句柄需修正）")
                print()
                continue
            bio = profile.get("description") or ""
            print(f"= @{profile['userName']}（输入: {label}）{profile.get('name', '')}")
            print(f"  粉丝 {profile.get('followers', '?')} | 认证: {profile.get('verifiedType') or '-'} | 简介: {bio[:160]}")
            try:
                tw = client.get(
                    "https://api.twitterapi.io/twitter/user/last_tweets",
                    params={"userName": profile["userName"]},
                    headers={"X-API-Key": KEY},
                ).json()
                tweets = ((tw.get("data") or {}).get("tweets")) or tw.get("tweets") or []
                for t in tweets[:3]:
                    if t.get("isReply"):
                        continue
                    print(f"  · {(t.get('text') or '').splitlines()[0][:100]}")
            except Exception as exc:
                print(f"  · 最近推文获取失败: {exc}")
            print()


if __name__ == "__main__":
    main()
