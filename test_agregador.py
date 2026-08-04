#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas de agregador.py. No toca la red ni la API: el cliente Claude está
simulado, y los feeds se sirven desde bytes locales.

    python3 test_agregador.py
"""

import json
import sys
import types
from pathlib import Path

import anthropic

import agregador as ag

ag.time.sleep = lambda *_: None          # nada de esperas reales en los tests

OK, FALLOS = 0, []


def check(nombre, condicion, detalle=""):
    global OK
    if condicion:
        OK += 1
        print(f"  ✓ {nombre}")
    else:
        FALLOS.append(nombre)
        print(f"  ✗ {nombre} {detalle}")


# --------------------------------------------------------------------------
# Dobles de la API
# --------------------------------------------------------------------------

def bloque_texto(payload):
    return types.SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))


def bloque_tool(payload):
    return types.SimpleNamespace(type="tool_use", name="publier_nouvelles", input=payload)


def respuesta(bloques, stop_reason="end_turn"):
    return types.SimpleNamespace(content=bloques, stop_reason=stop_reason)


class ClienteFalso:
    """Devuelve/lanza lo que le pongas en `guion`, un elemento por llamada."""

    def __init__(self, guion, soporta_output_config=True):
        self.guion = list(guion)
        self.soporta_output_config = soporta_output_config
        self.llamadas = []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.llamadas.append(kwargs)
        if "output_config" in kwargs and not self.soporta_output_config:
            raise TypeError(
                "Messages.create() got an unexpected keyword argument 'output_config'"
            )
        siguiente = self.guion.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


PAYLOAD_OK = {
    "France": [{
        "titre": "Réforme des retraites : nouveau vote",
        "resume": "L'Assemblée examine un amendement sur l'âge de départ.",
        "source": "Le Monde",
        "lien": "https://www.lemonde.fr/a1",
    }],
    "Île-de-France": [{
        "titre": "RER B : travaux ce week-end",
        "resume": "Interruption entre Gare du Nord et Denfert samedi.",
        "source": "Le Parisien",
        "lien": "https://www.leparisien.fr/b1",
    }],
    "Chili": [{
        "titre": "Sismo de magnitud 5,2 en Valparaíso",
        "resume": "Sans dégâts signalés selon l'ONEMI.",
        "source": "Emol",
        "lien": "https://www.emol.com/c1",
    }],
}

ORIGINALES = {
    "France": [{"titre": "Réforme des retraites : nouveau vote", "source": "Le Monde",
                "lien": "https://www.lemonde.fr/a1", "extrait": "brut"}],
    "Île-de-France": [{"titre": "RER B : travaux ce week-end", "source": "Le Parisien",
                       "lien": "https://www.leparisien.fr/b1", "extrait": "brut"}],
    "Chili": [{"titre": "Sismo de magnitud 5,2 en Valparaíso", "source": "Emol",
               "lien": "https://www.emol.com/c1", "extrait": "brut"}],
}

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>Titre un</title><link>https://ejemplo.fr/1</link>
<description>&lt;p&gt;Un <b>résumé</b> avec du HTML.&lt;/p&gt;</description></item>
<item><title>Titre deux</title><link>https://ejemplo.fr/2</link>
<description>Deuxième</description></item>
</channel></rss>""".encode("utf-8")


# --------------------------------------------------------------------------
# 1. Feeds
# --------------------------------------------------------------------------

def test_feeds():
    print("\n[1] Lectura de feeds")
    original = ag.descargar

    ag.descargar = lambda url, timeout=20: RSS
    articulos = ag.leer_feed("Test", "https://ejemplo.fr/rss")
    check("parsea 2 entradas", len(articulos) == 2, articulos)
    check("campos correctos",
          articulos[0]["titre"] == "Titre un"
          and articulos[0]["lien"] == "https://ejemplo.fr/1"
          and articulos[0]["source"] == "Test")
    check("limpia el HTML del extracto",
          "<" not in articulos[0]["extrait"] and "&" not in articulos[0]["extrait"]
          and "résumé" in articulos[0]["extrait"],
          articulos[0]["extrait"])

    def explota(url, timeout=20):
        raise ag.urllib.error.URLError("host inalcanzable")

    ag.descargar = explota
    check("un feed caído devuelve [] sin lanzar", ag.leer_feed("Roto", "https://x") == [])

    ag.descargar = lambda url, timeout=20: b"esto no es xml"
    check("basura no rompe el parseo", ag.leer_feed("Basura", "https://x") == [])

    ag.descargar = original


# --------------------------------------------------------------------------
# 2. Camino feliz
# --------------------------------------------------------------------------

def test_camino_feliz():
    print("\n[2] Camino feliz (output_config)")
    cliente = ClienteFalso([respuesta([bloque_texto(PAYLOAD_OK)])])
    datos = ag.resumir(ORIGINALES, cliente=cliente)

    check("una sola llamada", len(cliente.llamadas) == 1)
    kwargs = cliente.llamadas[0]
    check("usa output_config", "output_config" in kwargs)
    check("no manda tools", "tools" not in kwargs)
    check("modelo correcto", kwargs["model"] == "claude-sonnet-4-6")
    esq = kwargs["output_config"]["format"]["schema"]
    check("esquema con las 3 regiones", esq["required"] == ag.REGIONES)
    check("campos obligatorios en cada noticia",
          esq["properties"]["France"]["items"]["required"] == list(ag.CAMPOS))
    check("devuelve las 3 regiones", set(datos) == set(ag.REGIONES))
    check("noticia intacta", datos["Chili"][0]["source"] == "Emol")


# --------------------------------------------------------------------------
# 3. Reintentos
# --------------------------------------------------------------------------

def test_reintentos():
    print("\n[3] Reintentos")

    err_conexion = anthropic.APIConnectionError(request=types.SimpleNamespace())
    cliente = ClienteFalso([err_conexion, respuesta([bloque_texto(PAYLOAD_OK)])])
    datos = ag.resumir(ORIGINALES, cliente=cliente)
    check("se recupera de un error de conexión", len(datos["France"]) == 1)
    check("ha llamado 2 veces", len(cliente.llamadas) == 2)

    cliente = ClienteFalso([
        respuesta([bloque_texto(PAYLOAD_OK)], stop_reason="max_tokens"),
        respuesta([bloque_texto(PAYLOAD_OK)]),
    ])
    ag.resumir(ORIGINALES, cliente=cliente)
    check("sube max_tokens tras truncamiento",
          cliente.llamadas[1]["max_tokens"] > cliente.llamadas[0]["max_tokens"],
          [c["max_tokens"] for c in cliente.llamadas])

    # El fallo histórico: JSON roto en el texto. Con output_config no debería
    # ocurrir, pero si ocurriera se reintenta en vez de reventar el script.
    roto = types.SimpleNamespace(type="text", text='{"France": [{"titre": "a" "resume": "b"}]}')
    cliente = ClienteFalso([respuesta([roto]), respuesta([bloque_texto(PAYLOAD_OK)])])
    datos = ag.resumir(ORIGINALES, cliente=cliente)
    check("JSONDecodeError se reintenta, no se propaga", len(datos["Chili"]) == 1)

    cliente = ClienteFalso([err_conexion, err_conexion, err_conexion])
    try:
        ag.resumir(ORIGINALES, cliente=cliente)
        check("agota los intentos y lanza ErrorAgregador", False)
    except ag.ErrorAgregador:
        check("agota los intentos y lanza ErrorAgregador", True)
        check("exactamente 3 intentos", len(cliente.llamadas) == 3)


# --------------------------------------------------------------------------
# 4. Respaldo tool use
# --------------------------------------------------------------------------

def test_respaldo_tools():
    print("\n[4] Respaldo con tool use")
    cliente = ClienteFalso([respuesta([bloque_tool(PAYLOAD_OK)])],
                           soporta_output_config=False)
    datos = ag.resumir(ORIGINALES, cliente=cliente)
    check("cae a tool use con SDK viejo", len(cliente.llamadas) == 2)
    check("segunda llamada con tools", "tools" in cliente.llamadas[1])
    check("tool_choice forzado",
          cliente.llamadas[1]["tool_choice"] == {"type": "tool", "name": "publier_nouvelles"})
    check("strict activado", cliente.llamadas[1]["tools"][0]["strict"] is True)
    check("lee el bloque tool_use", datos["France"][0]["source"] == "Le Monde")


# --------------------------------------------------------------------------
# 5. Validación
# --------------------------------------------------------------------------

def test_validacion():
    print("\n[5] Validación / normalización")
    sucio = {
        "France": [
            {"titre": "Bien", "resume": "ok", "source": "Le Monde",
             "lien": "https://www.lemonde.fr/a1"},
            {"titre": "Sin resumen", "resume": "", "source": "X", "lien": "https://x.fr"},
            {"titre": "Enlace malo", "resume": "ok", "source": "X", "lien": "javascript:alert(1)"},
            "esto no es un objeto",
        ],
        "Île-de-France": [
            {"titre": "RER B : travaux ce week-end", "resume": "ok", "source": "Le Parisien",
             "lien": "https://inventado.example/xyz"},   # enlace alucinado
        ],
        # falta "Chili"
        "Marte": [{"titre": "z", "resume": "z", "source": "z", "lien": "https://z"}],
    }
    limpio = ag.validar(sucio, ORIGINALES)
    check("las 3 regiones siempre presentes", set(limpio) == set(ag.REGIONES))
    check("región ausente → lista vacía", limpio["Chili"] == [])
    check("región inventada descartada", "Marte" not in limpio)
    check("descarta entradas incompletas o no-objeto", len(limpio["France"]) == 1, limpio["France"])
    check("descarta esquemas de enlace raros",
          all(n["lien"].startswith("http") for n in limpio["France"]))
    check("repara el enlace alucinado por título",
          limpio["Île-de-France"][0]["lien"] == "https://www.leparisien.fr/b1",
          limpio["Île-de-France"][0]["lien"])

    try:
        ag.validar({"France": [], "Île-de-France": [], "Chili": []}, ORIGINALES)
        check("respuesta vacía → ErrorAgregador", False)
    except ag.ErrorAgregador:
        check("respuesta vacía → ErrorAgregador", True)

    try:
        ag.validar(["lista"], ORIGINALES)
        check("tipo raíz erróneo → ErrorAgregador", False)
    except ag.ErrorAgregador:
        check("tipo raíz erróneo → ErrorAgregador", True)

    degradado = ag.sin_ia(ORIGINALES)
    check("modo degradado produce las 3 regiones",
          all(len(degradado[r]) == 1 for r in ag.REGIONES))


# --------------------------------------------------------------------------
# 6. Inyección en la plantilla
# --------------------------------------------------------------------------

PLANTILLA_TEST = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>DodoNews</title></head>
<body><div id="app"></div>
<script>
/* DODONEWS_DATA_DEBUT */
const NOUVELLES = {};
/* DODONEWS_DATA_FIN */
render(NOUVELLES);
</script>
</body></html>
"""


def test_inyeccion(tmp: Path):
    print("\n[6] Inyección en template.html")
    plantilla = tmp / "template.html"
    salida = tmp / "index.html"
    plantilla.write_text(PLANTILLA_TEST, encoding="utf-8")

    peligroso = json.loads(json.dumps(PAYLOAD_OK))
    peligroso["France"][0]["resume"] = "Fin de la balise </script><script>alert(1)</script>"
    peligroso["Chili"][0]["titre"] = "Acentos: ñ é î — Valparaíso"

    html = ag.inyectar(peligroso, plantilla, salida)
    check("escribe index.html", salida.exists())
    check("conserva el resto de la plantilla", "render(NOUVELLES);" in html and "<div id=\"app\">" in html)
    check("marcas conservadas", ag.MARCA_INICIO in html and ag.MARCA_FIN in html)
    check("añade la fecha de actualización", "MISE_A_JOUR" in html)
    check("no hay </script> suelto en los datos",
          html.count("</script>") == 1, html.count("</script>"))
    check("acentos sin escapar (ensure_ascii=False)", "Valparaíso" in html)

    # El JSON incrustado se puede volver a parsear.
    cuerpo = html.split(ag.MARCA_INICIO)[1].split(ag.MARCA_FIN)[0]
    crudo = cuerpo.split("const NOUVELLES =", 1)[1].rsplit(";", 1)[0]
    crudo = crudo.rsplit("const MISE_A_JOUR", 1)[0].rstrip().rstrip(";")
    vuelta = json.loads(crudo.replace("<\\/", "</"))
    check("el JSON incrustado se reparsea", set(vuelta) == set(ag.REGIONES))
    check("contenido idéntico al de entrada",
          vuelta["France"][0]["titre"] == peligroso["France"][0]["titre"])

    # Idempotencia: reinyectar sobre la salida anterior.
    segunda = ag.inyectar(PAYLOAD_OK, salida, salida)
    check("reinyectable sobre su propia salida",
          segunda.count(ag.MARCA_INICIO) == 1 and "alert(1)" not in segunda)

    sin_marcas = tmp / "malo.html"
    sin_marcas.write_text("<html>sin marcas</html>", encoding="utf-8")
    try:
        ag.inyectar(PAYLOAD_OK, sin_marcas, tmp / "out2.html")
        check("plantilla sin marcas → error claro", False)
    except ag.ErrorAgregador:
        check("plantilla sin marcas → error claro", True)


# --------------------------------------------------------------------------
# 7. main() de extremo a extremo
# --------------------------------------------------------------------------

def test_main(tmp: Path):
    print("\n[7] main() completo")
    plantilla = tmp / "template.html"
    salida = tmp / "index_e2e.html"
    plantilla.write_text(PLANTILLA_TEST, encoding="utf-8")

    ag.PLANTILLA, ag.SALIDA = plantilla, salida
    ag.descargar = lambda url, timeout=20: RSS
    ag.FEEDS = {r: [(f"Fuente {r}", "https://ejemplo/rss")] for r in ag.REGIONES}

    payload = {r: [{"titre": "Titre un", "resume": "Résumé court.",
                    "source": f"Fuente {r}", "lien": "https://ejemplo.fr/1"}]
               for r in ag.REGIONES}
    cliente = ClienteFalso([respuesta([bloque_texto(payload)])])
    ag.anthropic.Anthropic = lambda *a, **k: cliente

    codigo = ag.main()
    check("main() devuelve 0", codigo == 0)
    check("index.html generado", salida.exists() and "Résumé court." in salida.read_text(encoding="utf-8"))

    # Ahora con la API caída del todo → modo degradado, sin excepción.
    err = anthropic.APIConnectionError(request=types.SimpleNamespace())
    ag.anthropic.Anthropic = lambda *a, **k: ClienteFalso([err, err, err])
    codigo = ag.main()
    contenido = salida.read_text(encoding="utf-8")
    check("modo degradado: main() sigue devolviendo 0", codigo == 0)
    check("modo degradado publica los titulares crudos",
          "Titre un" in contenido and "Résumé court." not in contenido)

    # Sin ningún feed vivo → no toca index.html y sale con 1.
    antes = salida.read_text(encoding="utf-8")
    ag.descargar = lambda url, timeout=20: b""
    codigo = ag.main()
    check("sin feeds: código de salida 1", codigo == 1)
    check("sin feeds: no sobrescribe index.html",
          salida.read_text(encoding="utf-8") == antes)


# --------------------------------------------------------------------------

def main():
    tmp = Path("/tmp/dodonews_test")
    tmp.mkdir(exist_ok=True)
    test_feeds()
    test_camino_feliz()
    test_reintentos()
    test_respaldo_tools()
    test_validacion()
    test_inyeccion(tmp)
    test_main(tmp)

    print(f"\n{'=' * 52}")
    if FALLOS:
        print(f"{OK} OK · {len(FALLOS)} FALLOS: {FALLOS}")
        return 1
    print(f"TODO VERDE: {OK} comprobaciones")
    return 0


if __name__ == "__main__":
    sys.exit(main())
