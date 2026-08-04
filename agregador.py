#!/usr/bin/env python3
import feedparser
import json
import os
import re
from datetime import datetime
from anthropic import Anthropic

FEEDS = {
    "France": [
        "https://www.france24.com/fr/rss",
        "https://www.lemonde.fr/rss/une.xml",
    ],
    "Île-de-France": [
        "https://www.francebleu.fr/rss/paris/rubrique/infos.xml",
    ],
    "Chili": [
        "https://www.biobiochile.cl/rss.xml",
        "https://www.t13.cl/rss",
    ],
}

MOIS = {1:"janvier",2:"février",3:"mars",4:"avril",5:"mai",6:"juin",
        7:"juillet",8:"août",9:"septembre",10:"octobre",11:"novembre",12:"décembre"}


def extract_news():
    out = {}
    for region, urls in FEEDS.items():
        out[region] = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for e in feed.entries[:6]:
                    out[region].append({
                        "title": e.get("title", ""),
                        "link": e.get("link", "#"),
                    })
            except Exception as err:
                print(f"  feed KO {url}: {err}")
        print(f"  {region}: {len(out[region])} titres")
    return out


def process_with_claude(noticias):
    client = Anthropic()
    prompt = (
        "Tu es le rédacteur de DodoNews, un résumé matinal minimaliste.\n"
        "Pour chaque région, choisis les 3 nouvelles les plus importantes.\n"
        "Résume chacune en 30 mots maximum, ton direct, sans jargon.\n"
        "Garde le lien d'origine.\n\n"
        f"{json.dumps(noticias, ensure_ascii=False, indent=2)}\n\n"
        "Réponds UNIQUEMENT avec ce JSON, sans texte autour:\n"
        '{"France":[{"titre":"...","resume":"...","lien":"..."}],'
        '"Île-de-France":[...],"Chili":[...]}'
    )

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    texte = resp.content[0].text
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texte, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


def generate_html(data):
    now = datetime.now()
    jour = f"{now.day} {MOIS[now.month]} {now.year}"

    corps = ""
    for region, items in data.items():
        if not items:
            continue
        corps += f"    <h2>{region}</h2>\n"
        for it in items:
            titre = it.get("titre", "")
            resume = it.get("resume", "")
            lien = it.get("lien", "#")
            corps += (
                f'    <article><a href="{lien}" target="_blank">'
                f"<strong>{titre}</strong><p>{resume}</p></a></article>\n"
            )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DodoNews</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
max-width:600px;margin:0 auto;padding:24px;color:#222;line-height:1.5}}
h1{{font-size:2.6em;font-weight:300;letter-spacing:-1px;margin:0}}
.sub{{color:#888;font-size:.9em;margin:4px 0 40px}}
h2{{font-size:1.2em;margin:40px 0 16px;padding-bottom:8px;border-bottom:1px solid #ddd}}
article{{margin-bottom:18px}}
article a{{text-decoration:none;color:inherit;display:block}}
article a:hover{{opacity:.6}}
article strong{{display:block;margin-bottom:4px}}
article p{{margin:0;color:#555;font-size:.95em}}
footer{{margin-top:60px;color:#aaa;font-size:.85em;text-align:center}}
</style>
</head>
<body>
    <h1>DodoNews</h1>
    <p class="sub">{jour}</p>
{corps}
    <footer>Parce que tu n'as pas le temps le matin</footer>
</body>
</html>"""


def main():
    print("Extraction...")
    noticias = extract_news()

    print("Traitement Claude...")
    data = process_with_claude(noticias)

    print("Génération HTML...")
    os.makedirs("output", exist_ok=True)
    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(generate_html(data))

    print("OK -> output/index.html")


if __name__ == "__main__":
    main()
