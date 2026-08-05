#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DodoNews — agregador de noticias.

Flujo:
  1. Descarga los feeds RSS (urllib + User-Agent de navegador, feedparser).
  2. Pide a Claude que resuma los titulares usando *structured outputs*:
     la API garantiza JSON válido conforme al esquema, así que ya no hay
     json.loads() sobre texto libre y por tanto no hay JSONDecodeError.
  3. Inyecta el resultado en template.html entre las marcas DODONEWS_DATA_*.

Vía principal : output_config.format (JSON outputs nativos, GA para Claude 4.5+).
Vía de respaldo: tool use forzado con strict=True (por si el runner tiene un
                 SDK anthropic antiguo que no conoce output_config).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import feedparser

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------

MODELO = "claude-sonnet-4-6"
MAX_TOKENS = 8000

REGIONES = ["France", "Île-de-France", "Chili"]

# Sustituye esta tabla por la tuya si tus URLs son otras: el resto del script
# no depende de los feeds concretos, solo de las claves de REGIONES.
FEEDS = {
    "France": [
        ("Le Monde", "https://www.lemonde.fr/rss/une.xml"),
        ("France Info", "https://www.francetvinfo.fr/titres.rss"),
    ],
    "Île-de-France": [
        ("Le Parisien", "https://feeds.leparisien.fr/leparisien/rss/paris-75"),
        ("France Info IDF", "https://www.francetvinfo.fr/france/ile-de-france.rss"),
    ],
    "Chili": [
        ("La Tercera", "https://www.latercera.com/arc/outboundfeeds/rss/?outputType=xml"),
        ("La Nación", "https://www.lanacion.cl/feed/"),
    ],
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 20

MAX_POR_FEED = 15          # titulares que se leen de cada feed
MAX_POR_REGION = 20        # titulares que se mandan al modelo por región
NOTICIAS_DESEADAS = 10     # noticias por región (= botón máximo de la plantilla)

MAX_INTENTOS = 3
ESPERA_BASE = 2.0          # segundos; backoff exponencial 2, 4, 8...

PLANTILLA = Path(os.environ.get("DODONEWS_TEMPLATE", "template.html"))
SALIDA = Path(os.environ.get("DODONEWS_OUTPUT", "index.html"))
MARCA_INICIO = "/* DODONEWS_DATA_DEBUT */"
MARCA_FIN = "/* DODONEWS_DATA_FIN */"
MARCA_HORA_INICIO = "/* DODONEWS_HEURE_DEBUT */"
MARCA_HORA_FIN = "/* DODONEWS_HEURE_FIN */"
ZONA = "Europe/Paris"

CAMPOS = ("titre", "resume", "source", "lien")


class ErrorAgregador(Exception):
    """Fallo recuperable: dispara un reintento."""


# --------------------------------------------------------------------------
# 1. Feeds RSS
# --------------------------------------------------------------------------

def descargar(url: str, timeout: int = TIMEOUT) -> bytes:
    """Descarga cruda con User-Agent de navegador (muchos feeds bloquean urllib)."""
    peticion = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
        return respuesta.read()


def leer_feed(fuente: str, url: str) -> list[dict]:
    """Devuelve los artículos de un feed. Imprime diagnóstico ✓/✗ y nunca lanza."""
    try:
        datos = descargar(url)
        analizado = feedparser.parse(datos)
        entradas = analizado.entries[:MAX_POR_FEED]
        if not entradas:
            print(f"  ✗ {fuente}: 0 entradas ({url})")
            return []
        articulos = [
            {
                "titre": (e.get("title") or "").strip(),
                "lien": (e.get("link") or "").strip(),
                "source": fuente,
                "extrait": _limpiar(e.get("summary") or e.get("description") or "")[:400],
            }
            for e in entradas
        ]
        articulos = [a for a in articulos if a["titre"] and a["lien"]]
        print(f"  ✓ {fuente}: {len(articulos)} entradas")
        return articulos
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        print(f"  ✗ {fuente}: {type(exc).__name__}: {exc}")
        return []


def _limpiar(bruto: str) -> str:
    """Quita entidades y etiquetas HTML (los resúmenes RSS suelen traer ambas)."""
    texto = unescape(unescape(bruto))   # los feeds a veces escapan dos veces
    fuera, dentro = [], False
    for caracter in texto:
        if caracter == "<":
            dentro = True
        elif caracter == ">":
            dentro = False
        elif not dentro:
            fuera.append(caracter)
    return " ".join("".join(fuera).split())


def recolectar() -> dict[str, list[dict]]:
    """Recorre todos los feeds y agrupa por región.

    Distingue dos situaciones:
      - un feed cae pero la región sobrevive gracias a otro → solo AVISO;
      - todos los feeds de una región caen → la región queda vacía y
        `main` lo tratará como error (salida en rojo).
    """
    resultado: dict[str, list[dict]] = {}
    for region in REGIONES:
        print(f"[{region}]")
        articulos: list[dict] = []
        vistos: set[str] = set()
        feeds = FEEDS.get(region, [])
        caidos = 0
        for fuente, url in feeds:
            leidos = leer_feed(fuente, url)
            if not leidos:
                caidos += 1          # leer_feed ya imprimió el ✗ detallado
            for articulo in leidos:
                if articulo["lien"] not in vistos:
                    vistos.add(articulo["lien"])
                    articulos.append(articulo)
        resultado[region] = articulos[:MAX_POR_REGION]

        # Aviso no bloqueante: la región tiene contenido pese a algún feed muerto.
        if caidos and articulos:
            print(f"  ⚠ AVERTISSEMENT : {caidos}/{len(feeds)} flux muet(s) pour "
                  f"« {region} », mais la région tient avec {len(resultado[region])} titres.")
        print(f"  → {len(resultado[region])} titulares retenidos\n")
    return resultado


# --------------------------------------------------------------------------
# 2. Resumen con Claude (structured outputs)
# --------------------------------------------------------------------------

def esquema() -> dict:
    """Esquema JSON de la salida: {región: [{titre, resume, source, lien}]}."""
    noticia = {
        "type": "object",
        "properties": {
            "titre": {"type": "string", "description": "Titre court en français."},
            "resume": {"type": "string", "description": "Résumé d'une ou deux phrases, en français."},
            "source": {"type": "string", "description": "Nom du média, repris tel quel."},
            "lien": {"type": "string", "description": "URL de l'article, copiée telle quelle."},
        },
        "required": list(CAMPOS),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {region: {"type": "array", "items": noticia} for region in REGIONES},
        "required": REGIONES,
        "additionalProperties": False,
    }


SISTEMA = (
    "Tu es le rédacteur en chef de DodoNews, une revue de presse quotidienne. "
    "Tu reçois des titres bruts de flux RSS et tu produis une sélection courte, "
    "claire et factuelle, rédigée en français. Pas d'opinion, pas d'invention : "
    "tout doit provenir des titres fournis. Recopie les URL exactement."
)


def _prompt(articulos: dict[str, list[dict]]) -> str:
    partes = [
        f"Date du jour : {datetime.now(timezone.utc).strftime('%d/%m/%Y')}",
        "",
        f"Sélectionne jusqu'à {NOTICIAS_DESEADAS} nouvelles par région, les plus "
        "importantes, sans doublon. Résume chacune en une ou deux phrases.",
        "",
    ]
    for region in REGIONES:
        partes.append(f"=== {region} ===")
        lista = articulos.get(region, [])
        if not lista:
            partes.append("(aucun titre disponible : renvoie une liste vide)")
        for articulo in lista:
            partes.append(f"- {articulo['titre']}")
            partes.append(f"  source: {articulo['source']}")
            partes.append(f"  lien: {articulo['lien']}")
            if articulo.get("extrait"):
                partes.append(f"  extrait: {articulo['extrait']}")
        partes.append("")
    return "\n".join(partes)


def _bloque_json(respuesta) -> dict:
    """Saca el objeto JSON de la respuesta, venga por output_config o por tool use."""
    motivo = getattr(respuesta, "stop_reason", None)
    if motivo == "max_tokens":
        raise ErrorAgregador("respuesta truncada (max_tokens)")
    if motivo == "refusal":
        raise ErrorAgregador("el modelo ha rechazado la petición (refusal)")

    for bloque in respuesta.content:
        if getattr(bloque, "type", None) == "tool_use":
            return dict(bloque.input)          # ya es un dict, no hay que parsear
    for bloque in respuesta.content:
        if getattr(bloque, "type", None) == "text":
            # Con output_config el texto es JSON válido por construcción.
            return json.loads(bloque.text)
    raise ErrorAgregador("respuesta sin bloque de texto ni tool_use")


def _llamar(cliente, prompt: str, max_tokens: int, usar_tools: bool):
    """Una sola llamada a la API. usar_tools=True → vía de respaldo."""
    comun = dict(
        model=MODELO,
        max_tokens=max_tokens,
        system=SISTEMA,
        messages=[{"role": "user", "content": prompt}],
    )
    if usar_tools:
        return cliente.messages.create(
            **comun,
            tools=[{
                "name": "publier_nouvelles",
                "description": "Publie la sélection de nouvelles de DodoNews.",
                "strict": True,
                "input_schema": esquema(),
            }],
            tool_choice={"type": "tool", "name": "publier_nouvelles"},
        )
    return cliente.messages.create(
        **comun,
        output_config={"format": {"type": "json_schema", "schema": esquema()}},
    )


def resumir(articulos: dict[str, list[dict]], cliente=None) -> dict[str, list[dict]]:
    """Llama a Claude con reintentos. Lanza ErrorAgregador si agota los intentos."""
    cliente = cliente or anthropic.Anthropic()
    prompt = _prompt(articulos)
    usar_tools = False
    max_tokens = MAX_TOKENS
    ultimo: Exception | None = None

    for intento in range(1, MAX_INTENTOS + 1):
        via = "tool use" if usar_tools else "output_config"
        print(f"→ Claude ({via}), intento {intento}/{MAX_INTENTOS}...")
        try:
            respuesta = _llamar(cliente, prompt, max_tokens, usar_tools)
            datos = validar(_bloque_json(respuesta), articulos)
            total = sum(len(v) for v in datos.values())
            print(f"  ✓ {total} noticias recibidas")
            return datos

        except TypeError as exc:
            # SDK viejo: no conoce output_config → pasamos a tool use.
            if "output_config" in str(exc) and not usar_tools:
                print("  ! SDK sin output_config, cambio a tool use")
                usar_tools = True
                continue
            ultimo = exc

        except anthropic.BadRequestError as exc:
            if "output_config" in str(exc) and not usar_tools:
                print("  ! API rechaza output_config, cambio a tool use")
                usar_tools = True
                continue
            ultimo = exc

        except ErrorAgregador as exc:
            ultimo = exc
            if "truncada" in str(exc):
                max_tokens = min(max_tokens * 2, 16000)
                print(f"  ! {exc} → reintento con max_tokens={max_tokens}")
            else:
                print(f"  ! {exc}")

        except (anthropic.APIConnectionError, anthropic.RateLimitError,
                anthropic.InternalServerError, json.JSONDecodeError) as exc:
            ultimo = exc
            print(f"  ! {type(exc).__name__}: {exc}")

        if intento < MAX_INTENTOS:
            espera = ESPERA_BASE * (2 ** (intento - 1))
            print(f"  … espero {espera:.0f}s")
            time.sleep(espera)

    raise ErrorAgregador(f"Claude ha fallado tras {MAX_INTENTOS} intentos: {ultimo}")


# --------------------------------------------------------------------------
# 3. Validación / normalización
# --------------------------------------------------------------------------

def validar(datos, originales: dict[str, list[dict]] | None = None) -> dict[str, list[dict]]:
    """
    Cinturón y tirantes: el esquema ya garantiza la forma, pero esto protege
    contra la vía de respaldo, contra un refusal parcial y contra enlaces
    inventados. Devuelve siempre las 3 regiones.
    """
    if not isinstance(datos, dict):
        raise ErrorAgregador(f"se esperaba un objeto, llegó {type(datos).__name__}")

    enlaces = {}
    if originales:
        for lista in originales.values():
            for articulo in lista:
                enlaces[articulo["titre"].lower()] = articulo["lien"]
    conocidos = set(enlaces.values())

    limpio: dict[str, list[dict]] = {}
    for region in REGIONES:
        lista = datos.get(region) or []
        if not isinstance(lista, list):
            lista = []
        noticias = []
        for elemento in lista:
            if not isinstance(elemento, dict):
                continue
            noticia = {campo: str(elemento.get(campo, "") or "").strip() for campo in CAMPOS}
            if not noticia["titre"] or not noticia["resume"]:
                continue
            if conocidos and noticia["lien"] not in conocidos:
                # enlace reescrito o inventado: intento recuperar el original
                noticia["lien"] = enlaces.get(noticia["titre"].lower(), noticia["lien"])
            if not noticia["lien"].startswith(("http://", "https://")):
                continue
            noticias.append(noticia)
        limpio[region] = noticias[:NOTICIAS_DESEADAS]

    if not any(limpio.values()):
        raise ErrorAgregador("ninguna noticia utilizable en la respuesta")
    return limpio


def sin_ia(articulos: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Modo degradado: publica los titulares crudos si la API no responde."""
    return {
        region: [
            {
                "titre": a["titre"],
                "resume": a.get("extrait", "")[:220] or "(résumé indisponible)",
                "source": a["source"],
                "lien": a["lien"],
            }
            for a in articulos.get(region, [])[:NOTICIAS_DESEADAS]
        ]
        for region in REGIONES
    }


# --------------------------------------------------------------------------
# 4. Inyección en template.html
# --------------------------------------------------------------------------

def serializar(datos: dict) -> str:
    """JSON listo para vivir dentro de una etiqueta <script>."""
    bruto = json.dumps(datos, ensure_ascii=False, indent=2)
    return (
        bruto.replace("</", "<\\/")          # no cerrar el <script> por accidente
        .replace("\u2028", "\\u2028")        # separadores de línea que rompen JS
        .replace("\u2029", "\\u2029")
    )


def _reemplazar(html: str, inicio: str, fin: str, contenido: str, obligatorio: bool) -> str:
    """Sustituye lo que hay entre dos marcas, conservándolas (idempotente)."""
    i = html.find(inicio)
    f = html.find(fin)
    if i == -1 or f == -1 or f < i:
        if obligatorio:
            raise ErrorAgregador(f"marcas {inicio} / {fin} no encontradas en la plantilla")
        print(f"  ! marcas {inicio} ausentes, bloque omitido")
        return html
    return html[:i] + f"{inicio}\n{contenido}\n{fin}" + html[f + len(fin):]


def hora_local() -> str:
    """Hora de generación en formato francés (7h12), en hora de París."""
    try:
        ahora = datetime.now(ZoneInfo(ZONA))
    except Exception:                      # runner sin tzdata
        ahora = datetime.now(timezone.utc)
    return f"{ahora.hour}h{ahora.minute:02d}"


def inyectar(datos: dict, plantilla=None, salida=None) -> str:
    """Rellena los dos bloques marcados de la plantilla y escribe la salida."""
    plantilla = Path(plantilla) if plantilla else PLANTILLA
    salida = Path(salida) if salida else SALIDA
    html = plantilla.read_text(encoding="utf-8")

    html = _reemplazar(
        html, MARCA_INICIO, MARCA_FIN,
        f"const NOUVELLES = {serializar(datos)};",
        obligatorio=True,
    )
    html = _reemplazar(
        html, MARCA_HORA_INICIO, MARCA_HORA_FIN,
        f'const HEURE_MAJ = "{hora_local()}";',
        obligatorio=False,
    )

    salida.write_text(html, encoding="utf-8")
    return html


# --------------------------------------------------------------------------
# 5. main
# --------------------------------------------------------------------------

def main() -> int:
    print("DodoNews — recolección de feeds\n")
    articulos = recolectar()
    if not any(articulos.values()):
        print("✗ Ningún feed ha devuelto nada. Aborto sin tocar index.html.")
        return 1

    try:
        noticias = resumir(articulos)
    except ErrorAgregador as exc:
        print(f"✗ {exc}")
        print("⚠ Modo degradado: publico los titulares sin resumir.")
        noticias = validar(sin_ia(articulos), articulos)

    inyectar(noticias)
    total = sum(len(v) for v in noticias.values())
    print(f"\n✓ {SALIDA} generado con {total} noticias.")
    for region in REGIONES:
        print(f"    {region}: {len(noticias.get(region, []))}")

    # Guardia anti-fallo-silencioso: una región vacía = todos sus feeds cayeron.
    # Publicamos lo que hay, pero salimos en ROJO (código 1) para que la corrida
    # de GitHub Actions se ponga en rojo y el fallo no pase desapercibido.
    vacias = [r for r in REGIONES if not noticias.get(r)]
    if vacias:
        print(f"\n✗ ERREUR : région(s) sans aucune nouvelle : {', '.join(vacias)}.")
        print("  Tous les flux de ces régions sont probablement morts "
              "(voir les ✗ ci-dessus). Sortie en erreur pour alerter Actions.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
