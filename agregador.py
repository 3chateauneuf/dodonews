#!/usr/bin/env python3
"""
DodoNews - Agrégateur de nouvelles matinal.

Qué hace este script, paso a paso:
  1. Descarga los titulares de varias fuentes RSS (France, Île-de-France, Chili).
  2. Pide a Claude que elija las más importantes y las resuma de forma neutra.
  3. Inserta esos resúmenes en la plantilla 'template.html'.
  4. Guarda el resultado en 'output/index.html', listo para publicar.

El diseño de la página vive en template.html (HTML + CSS + JS legibles).
Este script NO genera diseño: solo rellena los datos. Así, si quieres cambiar
la apariencia, editas template.html sin tocar este código, y viceversa.
"""

import feedparser
import json
import os
import re
import urllib.request
from datetime import datetime
from anthropic import Anthropic


# Algunos serveurs refusent les requêtes sans navigateur (erreur 403).
# On se présente donc comme un navigateur classique.
NAVIGATEUR = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# FUENTES RSS
# Añade o quita URLs libremente. Cada región es una clave.
# ---------------------------------------------------------------------------
FEEDS = {
    "France": [
        "https://www.france24.com/fr/rss",
        "https://www.lemonde.fr/rss/une.xml",
    ],
    "Île-de-France": [
        "https://feeds.leparisien.fr/leparisien/rss/paris-75",
        "https://www.francebleu.fr/rss/paris/rubrique/infos.xml",
    ],
    "Chili": [
        # BioBio via FeedBurner (Google) : contourne le blocage du serveur direct.
        "https://feeds.feedburner.com/radiobiobio/NNeJ",
        # La Tercera, quotidien national de référence.
        "https://www.latercera.com/arc/outboundfeeds/rss/?outputType=xml",
          # El Dínamo — actualité nationale (WordPress /feed/, très fiable).
        "https://www.eldinamo.cl/feed/",
        # El Mostrador — média de référence, politique et affaires publiques.
        "https://www.elmostrador.cl/feed/",
    ],
}

# Cuántos titulares leer por fuente antes de pasárselos a Claude.
# Claude elegirá luego los mejores; pedimos de más para que tenga dónde elegir.
TITRES_PAR_FLUX = 8

# Modelo de Claude usado para resumir. Sonnet es rápido, barato y suficiente
# para sintetizar noticias. Cámbialo aquí si algún día quieres otro.
MODELE = "claude-sonnet-4-6"


def telecharger_flux(url):
    """Descarga un feed presentándose como navegador. Devuelve el feed parseado.

    Muchos servidores devuelven 403 si la petición no parece venir de un
    navegador. Por eso descargamos con urllib enviando un User-Agent, y luego
    se lo pasamos a feedparser ya descargado.
    """
    requete = urllib.request.Request(url, headers={"User-Agent": NAVIGATEUR})
    with urllib.request.urlopen(requete, timeout=15) as reponse:
        donnees = reponse.read()
    return feedparser.parse(donnees)


def extraire_titres():
    """Descarga los titulares de todas las fuentes y los agrupa por región.

    Imprime un diagnóstico claro por cada feed: cuántos titulares trajo, o
    exactamente qué error dio. Así, mirando el log de GitHub Actions, sabes
    de un vistazo qué fuente funciona y cuál hay que reemplazar.
    """
    resultat = {}
    for region, urls in FEEDS.items():
        resultat[region] = []
        print(f"\n  {region} :")
        for url in urls:
            try:
                flux = telecharger_flux(url)
                titres = flux.entries[:TITRES_PAR_FLUX]
                for entree in titres:
                    resultat[region].append({
                        "titre": entree.get("title", ""),
                        "lien": entree.get("link", "#"),
                        "source": flux.feed.get("title", "Source"),
                    })
                print(f"    ✓ {len(titres):2d} titres — {url}")
            except Exception as erreur:
                # Mostramos el tipo de error (ej. HTTP 403, timeout) y la URL,
                # para poder diagnosticar sin adivinar.
                print(f"    ✗ ÉCHEC ({type(erreur).__name__}) — {url}")
        print(f"    → total {region} : {len(resultat[region])} titres")
    return resultat


def resumer_avec_claude(titres):
    """Pide a Claude que seleccione y resuma las noticias de forma neutra."""
    client = Anthropic()

    consigne = (
        "Tu es le rédacteur de DodoNews, un résumé matinal minimaliste.\n"
        "À partir des titres fournis pour chaque région :\n"
        "  1. Choisis les nouvelles les plus importantes (jusqu'à 6 par région).\n"
        "  2. Rédige pour chacune un résumé NEUTRE et factuel de 30 mots maximum,\n"
        "     sans opinion, sans adjectif inutile.\n"
        "  3. Reformule le titre de façon claire (ne copie pas mot à mot).\n"
        "  4. Conserve le nom de la source et le lien d'origine.\n\n"
        "Titres du jour :\n"
        f"{json.dumps(titres, ensure_ascii=False, indent=2)}\n\n"
        "Réponds UNIQUEMENT avec ce JSON, sans aucun texte autour :\n"
        '{\n'
        '  "France": [\n'
        '    {"titre": "...", "resume": "...", "source": "...", "lien": "..."}\n'
        '  ],\n'
        '  "Île-de-France": [ ... ],\n'
        '  "Chili": [ ... ]\n'
        '}'
    )

    reponse = client.messages.create(
        model=MODELE,
        max_tokens=2500,
        messages=[{"role": "user", "content": consigne}],
    )

    texte = reponse.content[0].text

    # Claude debería devolver JSON puro, pero por seguridad extraemos el objeto
    # si viniera rodeado de texto.
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        trouve = re.search(r"\{.*\}", texte, re.DOTALL)
        if trouve:
            return json.loads(trouve.group())
        raise


def formater_donnees_js(donnees):
    """Convierte el diccionario de noticias en el objeto JavaScript NOUVELLES."""
    # json.dumps produce un objeto válido también en JavaScript.
    # ensure_ascii=False conserva los acentos; indent=2 lo deja legible.
    corps = json.dumps(donnees, ensure_ascii=False, indent=2)
    return "const NOUVELLES = " + corps + ";"


def construire_page(donnees, heure):
    """Lee template.html y sustituye los datos y la hora entre las marcas."""
    with open("template.html", encoding="utf-8") as f:
        modele = f.read()

    # Reemplazo del bloque de datos, delimitado por las marcas del template.
    bloc_donnees = formater_donnees_js(donnees)
    modele = re.sub(
        r"/\* DODONEWS_DATA_DEBUT \*/.*?/\* DODONEWS_DATA_FIN \*/",
        "/* DODONEWS_DATA_DEBUT */\n" + bloc_donnees + "\n/* DODONEWS_DATA_FIN */",
        modele,
        flags=re.DOTALL,
    )

    # Reemplazo de la hora de actualización.
    modele = re.sub(
        r"/\* DODONEWS_HEURE_DEBUT \*/.*?/\* DODONEWS_HEURE_FIN \*/",
        '/* DODONEWS_HEURE_DEBUT */\nconst HEURE_MAJ = "' + heure + '";\n/* DODONEWS_HEURE_FIN */',
        modele,
        flags=re.DOTALL,
    )

    return modele


def main():
    print("1/3  Récupération des titres…")
    titres = extraire_titres()

    print("2/3  Résumé par Claude…")
    donnees = resumer_avec_claude(titres)

    print("3/3  Génération de la page…")
    heure = datetime.now().strftime("%Hh%M")
    page = construire_page(donnees, heure)

    os.makedirs("output", exist_ok=True)
    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(page)

    print("✓  Terminé : output/index.html")


if __name__ == "__main__":
    main()
