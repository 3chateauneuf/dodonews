#!/usr/bin/env python3
import feedparser
import json
import os
from datetime import datetime
from anthropic import Anthropic

FEEDS = {
    "France": [
        "https://www.france24.com/fr/flux-rss-complet.xml",
        "https://www.lemonde.fr/rss/une.xml",
    ],
    "Île-de-France": [
        "https://www.francebleu.fr/rss/ile-de-france/actualite.xml",
    ],
    "Chili": [
        "https://www.biobiochile.cl/rss.xml",
        "https://www.t13.cl/rss",
    ]
}

def extract_news():
    noticias = {}
    for region, urls in FEEDS.items():
        noticias[region] = []
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    noticias[region].append({
                        "title": entry.get('title', 'Sans titre'),
                        "link": entry.get('link', '#'),
                    })
            except:
                pass
    return noticias

def process_with_claude(noticias):
    client = Anthropic()
    noticias_texto = json.dumps(noticias, ensure_ascii=False, indent=2)
    
    prompt = f"""Tu es un résumeur de nouvelles. Sélectionne 2-3 nouvelles par région, résume chacune en max 30 mots.

Nouvelles:
{noticias_texto}

Réponds UNIQUEMENT en JSON:
{{
  "France": [
    {{"titre": "...", "résumé": "..."}},
  ],
  "Île-de-France": [...],
  "Chili": [...]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    try:
        return json.loads(response.content[0].text)
    except:
        import re
        match = re.search(r'\{.*\}', response.content[0].text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}

def generate_html(noticias):
    maintenant = datetime.now()
    jour = maintenant.strftime("%d %B %Y")
    
    sections = ""
    for region, items in noticias.items():
        if not items:
            continue
        sections += f"<h2>{region}</h2>\n"
        for item in items:
            sections += f"<p><strong>{item.get('titre', '')}</strong><br>{item.get('résumé', '')}</p>\n"
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DodoNews</title>
    <style>
        body {{ font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        h1 {{ font-size: 2.5em; font-weight: 300; }}
        h2 {{ border-bottom: 1px solid #ddd; margin-top: 30px; }}
        p {{ line-height: 1.6; color: #555; }}
    </style>
</head>
<body>
    <h1>DodoNews</h1>
    <p style="color: #999;">{jour}</p>
    {sections}
</body>
</html>"""
    return html

def main():
    print("Extraction...")
    noticias = extract_news()
    print("Traitement...")
    noticias_procesadas = process_with_claude(noticias)
    print("Génération...")
    html = generate_html(noticias_procesadas)
    os.makedirs("output", exist_ok=True)
    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Terminé!")

if __name__ == "__main__":
    main()
