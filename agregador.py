#!/usr/bin/env python3
"""
DodoNews - Agrégateur de nouvelles minimaliste
Résumés courts et simples pour lire le matin après le dodo
"""

import feedparser
import json
import os
from datetime import datetime
from anthropic import Anthropic

# ============================================
# CONFIGURATION DES FLUX RSS
# ============================================

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

client = Anthropic()

def extract_news():
    """Extrait les dernières nouvelles des flux RSS"""
    noticias = {}
    
    for region, urls in FEEDS.items():
        noticias[region] = []
        
        for url in urls:
            try:
                feed = feedparser.parse(url)
                
                # Prend les 5 derniers articles
                for entry in feed.entries[:5]:
                    noticias[region].append({
                        "title": entry.get('title', 'Sans titre'),
                        "link": entry.get('link', '#'),
                        "source": feed.feed.get('title', 'Source inconnue'),
                    })
            except Exception as e:
                print(f"  ⚠️  Erreur {region}: {e}")
    
    return noticias

def process_with_claude(noticias):
    """Traite les nouvelles avec Claude pour générer des résumés courts"""
    
    noticias_texto = json.dumps(noticias, ensure_ascii=False, indent=2)
    
    prompt = f"""Tu es un résumeur de nouvelles pour DodoNews - un agrégateur minimaliste.

RÈGLES STRICTES:
1. Sélectionne SEULEMENT les 2-3 nouvelles les PLUS IMPORTANTES de chaque région
2. Chaque résumé = MAXIMUM 30 mots (très court!)
3. Ton: Directe, conversationnel, sans jargon
4. Format: "Titre: Résumé court"
5. Pas de catégories, pas de labels, juste les faits

EXEMPLE:
"Élections : Les électeurs votent demain pour choisir leur maire."

Nouvelles du jour:
{noticias_texto}

Réponds UNIQUEMENT en JSON valide:
{{
  "France": [
    {{"titre": "...", "résumé": "...court résumé...", "lien": "..."}},
  ],
  "Île-de-France": [...],
  "Chili": [...]
}}
"""

    print("✍️  Claude traite les nouvelles...")
    
    response = client.messages.create(
        model="claude-opus-4-1-20250805",
        max_tokens=1500,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    response_text = response.content[0].text
    
    try:
        noticias_procesadas = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            noticias_procesadas = json.loads(json_match.group())
        else:
            return None
    
    return noticias_procesadas

def generate_html(noticias_procesadas):
    """Génère le HTML minimaliste pour DodoNews"""
    
    maintenant = datetime.now()
    heure = maintenant.strftime("%H:%M")
    jour = maintenant.strftime("%A %d %B %Y").replace("Monday", "lundi").replace("Tuesday", "mardi").replace("Wednesday", "mercredi").replace("Thursday", "jeudi").replace("Friday", "vendredi").replace("Saturday", "samedi").replace("Sunday", "dimanche").replace("January", "janvier").replace("February", "février").replace("March", "mars").replace("April", "avril").replace("May", "mai").replace("June", "juin").replace("July", "juillet").replace("August", "août").replace("September", "septembre").replace("October", "octobre").replace("November", "novembre").replace("December", "décembre")
    
    sections_html = ""
    
    for region, noticias in noticias_procesadas.items():
        if not noticias:
            continue
        
        sections_html += f'<section>\n<h2>{region}</h2>\n'
        
        for noticia in noticias:
            titre = noticia.get('titre', 'Sans titre')
            resume = noticia.get('résumé', '')
            lien = noticia.get('lien', '#')
            
            sections_html += f'''<article>
<a href="{lien}" target="_blank">
<strong>{titre}</strong>
<p>{resume}</p>
</a>
</article>
'''
        
        sections_html += '</section>\n'
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="DodoNews - Résumés du matin en quelques mots">
    <title>DodoNews - {jour}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #fafafa;
            color: #222;
            line-height: 1.5;
            padding: 20px;
        }}
        
        .container {{
            max-width: 600px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 40px;
            padding: 30px 0;
        }}
        
        h1 {{
            font-size: 2.8em;
            font-weight: 300;
            letter-spacing: -1px;
            margin-bottom: 5px;
        }}
        
        .subheader {{
            color: #666;
            font-size: 0.95em;
            margin: 10px 0 5px;
        }}
        
        .hora {{
            color: #999;
            font-size: 0.9em;
            font-weight: 500;
        }}
        
        section {{
            margin-bottom: 50px;
        }}
        
        h2 {{
            font-size: 1.3em;
            font-weight: 600;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }}
        
        article {{
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #eee;
        }}
        
        article:last-child {{
            border-bottom: none;
        }}
        
        article a {{
            text-decoration: none;
            color: inherit;
            display: block;
            transition: opacity 0.2s;
        }}
        
        article a:hover {{
            opacity: 0.7;
        }}
        
        article strong {{
            display: block;
            margin-bottom: 6px;
            font-size: 1.05em;
            font-weight: 600;
        }}
        
        article p {{
            color: #555;
            font-size: 0.95em;
            line-height: 1.6;
        }}
        
        footer {{
            margin-top: 60px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #999;
            font-size: 0.85em;
        }}
        
        @media (max-width: 500px) {{
            h1 {{
                font-size: 2em;
            }}
            
            h2 {{
                font-size: 1.1em;
            }}
            
            body {{
                padding: 15px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>DodoNews</h1>
            <p class="subheader">Les infos du matin en quelques mots</p>
            <p class="hora">{jour} • {heure}</p>
        </header>

{sections_html}

        <footer>
            <p>Parce que tu n'as pas le temps le matin</p>
        </footer>
    </div>
</body>
</html>
"""
    
    return html

def main():
    print("\n" + "="*50)
    print("🌅 DodoNews - Nouvelles du matin")
    print("="*50 + "\n")
    
    if not os.getenv('ANTHROPIC_API_KEY'):
        print("❌ ANTHROPIC_API_KEY non configurée")
        return
    
    print("1️⃣  Extraction des nouvelles...")
    noticias = extract_news()
    total = sum(len(n) for n in noticias.values())
    print(f"   ✅ {total} nouvelles extraites\n")
    
    print("2️⃣  Traitement avec Claude...")
    noticias_procesadas = process_with_claude(noticias)
    
    if not noticias_procesadas:
        print("❌ Erreur de traitement")
        return
    
    print("   ✅ Nouvelles traitées\n")
    
    print("3️⃣  Génération du HTML...")
    html = generate_html(noticias_procesadas)
    
    os.makedirs("output", exist_ok=True)
    
    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    with open("output/noticias.json", "w", encoding="utf-8") as f:
        json.dump(noticias_procesadas, f, ensure_ascii=False, indent=2)
    
    print("   ✅ Fichiers générés\n")
    print("="*50)
    print("✨ C'est prêt!")
    print("="*50 + "\n")
    
    for region, noticias in noticias_procesadas.items():
        print(f"📍 {region}: {len(noticias)} infos")
    
    print(f"\n📂 Ouvrez: output/index.html")
    print()

if __name__ == "__main__":
    main()
