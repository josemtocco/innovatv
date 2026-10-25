#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de lista M3U da Innova TV (plataforma MOTV/MW) para o SS IPTV.

- Somente biblioteca padrao do Python (sem pip).
- Regenera o catalogo a cada execucao a partir da API MOTV.
- Regra das 3 falhas: so remove um canal depois de 3 atualizacoes seguidas sem funcionar.
- Categorias unificadas: maiusculas/minusculas iguais viram uma so; nomes similares/sinonimos
  (ex.: noticias/News; Desenhos/kids/infantil/crianca; cinema/filmes) viram uma categoria unica.
- Canais com o MESMO link m3u sao deduplicados (mantem apenas um).
- group-title + tvg-logo para visual bonito no SS IPTV.
- Lista de seed com canais conhecidos (fallback quando a API nao devolve streams).
- Headers fieis ao portal (Origin/Referer/Content-Type text/plain).

Fontes:
  - https://sms.innova.tv.br/api/Devices/Motv/getPortal
  - https://sms.innova.tv.br/api/Devices/Motv/getData  (device_id)

Uso:
  python gerar_innova.py

Variaveis de ambiente (todas opcionais):
  INNOVA_DEVICE_ID  -> device_id ja pareado/logado (capturado do seu navegador no Brasil)
  INNOVA_LOGIN      -> login/e-mail da sua conta Innova (tentativa de login automatico)
  INNOVA_SENHA      -> senha da conta Innova
  INNOVA_CATALOGO   -> caminho de um JSON salvo (resposta do getData capturada no F12). Se existir,
                       usa esse arquivo em vez de chamar a API (garante funcionar mesmo com login/regiao)
  INNOVA_DEBUG      -> "1" para log detalhado (dump de amostras do JSON)
  VALIDAR_STREAMS   -> "1" (padrao) valida os links; "0" nao valida (mantem tudo)
  USAR_SEED         -> "1" (padrao) inclui a lista de seed de canais conhecidos
"""
import json
import os
import re
import ssl
import sys
import time
import uuid
import unicodedata
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# --------------------------------------------------------------------------- #
# Configuracao
# --------------------------------------------------------------------------- #
API_BASE       = "https://sms.innova.tv.br/api"
PORTAL_URL     = "https://portal.innova.tv.br"
MOTV_PORTAL_ID = 1          # motv_portals_id (confirmado no getPortal)
MOTV_VENDOR_ID = 1          # motv_portals_motv_vendors_id
LANG           = "por"

AQUI        = os.path.dirname(os.path.abspath(__file__))
SAIDA_M3U   = os.path.join(AQUI, "playlists", "innova.m3u")
ESTADO_JSON = os.path.join(AQUI, "estado_canais.json")

MAX_FALHAS      = 3     # regra das 3 falhas
TIMEOUT         = 14
WORKERS         = 16
DEBUG           = os.environ.get("INNOVA_DEBUG", "") == "1"
VALIDAR         = os.environ.get("VALIDAR_STREAMS", "1") != "0"
USAR_SEED       = os.environ.get("USAR_SEED", "1") != "0"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) "
      "Gecko/20100101 Firefox/158.0")

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def log(msg):
    print(msg, flush=True)


def dbg(msg):
    if DEBUG:
        print("[debug] " + msg, flush=True)


# --------------------------------------------------------------------------- #
# Seed de canais conhecidos (fallback / complemento)
# Confirmados via grade publica + links enviados pelo usuario
# --------------------------------------------------------------------------- #
SEED_CANAIS = [
    {
        "name": "Rede Brasil",
        "url": "https://redebrasil.nuvemplay.live/hls/stream.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/19/channels-6a74d5e688f69.png",
        "category": "Canais Abertos",
    },
    {
        "name": "Rede NGT TV",
        "url": "https://isaocorp.cloudecast.com/ngt/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/9/channels-6a28d373bc8b0.png",
        "category": "Canais Abertos",
    },
    {
        "name": "Rede QDM",
        "url": "https://stmv1.transmissaodigital.com/redeqdm/redeqdm/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/1/channels-6a74e516c1368.png",
        "category": "Canais Abertos",
    },
    {
        "name": "Rede TV Paraná",
        "url": "https://tv01.zas.media:1936/redetvparana/redetvparana/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/25/46/channels-6a8e0a668a779.png",
        "category": "Canais Abertos",
    },
    {
        "name": "TV Clube Brasil",
        "url": "https://isaocorp.cloudecast.com/recon/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/10/05/22/channels-6ac3d13d5a41c.png",
        "category": "Canais Abertos",
    },
    {
        "name": "TV Compasso",
        "url": "https://cdn.live.br1.jmvstream.com/webtv/wgyzoiun/playlist/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/19/channels-6a74dc88ce7fc.png",
        "category": "Canais Abertos",
    },
    {
        "name": "TV Florida",
        "url": "https://live01.innovatv.tv.br/TV_Florida/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/21/channels-6a74d492394f2.png",
        "category": "Canais Abertos",
    },
    {
        "name": "TV Folha do Campo",
        "url": "https://stmv1.transmissaodigital.com/folha-do-campo/folha-do-campo/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/37/channels-6a28d67be6b2d.png",
        "category": "Canais Abertos",
    },
    {
        "name": "TV Marataízes",
        "url": "https://edge.innova.tv.br/s-mini01/channels/live/tv-marataizes3801rj1pk0-52-59/tv-marataizes-52-59-cbcs.mpd",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/09/29/7/channels-6abbb6b31a007.png",
        "category": "Canais Abertos",
    },
    {
        "name": "TV Meio Norte",
        "url": "https://maystreaming.cloudecast.com/redemeio/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/09/22/3/channels-6ab2c1c5df675.png",
        "category": "Canais Abertos",
    },
    {
        "name": "TV Pampa",
        "url": "https://video04.logicahost.com.br/tvpampa/tvpampa/playlist.m3u8",
        "logo": "",
        "category": "Canais Abertos",
    },
    {
        "name": "TV Planalto",
        "url": "https://pop.uniquetv.com.br/hls/tvplanaltonorte.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/07/14/45/channels-6a55a7e21bc11.png",
        "category": "Canais Abertos",
    },
    {
        "name": "Tenda TV",
        "url": "https://tv02.zas.media:1936/tendatv/tendatv/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/25/26/channels-6a8e0a674507b.png",
        "category": "Canais Abertos",
    },
    {
        "name": "HALLO! DOC.",
        "url": "https://live01.innovatv.tv.br/Hallo_Doc/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/13/channels-6a28df4592b35.png",
        "category": "Documentarios",
    },
    {
        "name": "Nsports",
        "url": "https://live01.innovatv.tv.br/Nsports_1080/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/17/channels-6a28dcd94a1ca.png",
        "category": "Esportes",
    },
    {
        "name": "Play TV Horse",
        "url": "https://cdn-5.nxplay.com.br/PLAYHORSE_TV/index.m3u8?token=8SswUs_jKAOwDeZWaPqIKg&expires=1814468979",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/36/channels-6a28d2d4c97e9.png",
        "category": "Esportes",
    },
    {
        "name": "TV da Pesca",
        "url": "https://isaocorp.cloudecast.com/tvdapesca/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/40/channels-6a28d57f4e468.png",
        "category": "Esportes",
    },
    {
        "name": "AWTV",
        "url": "https://awtv.nuvemplay.live/hls/stream.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/07/13/30/channels-6a55a5f7579fc.png",
        "category": "Filmes",
    },
    {
        "name": "HALLO! Classic",
        "url": "https://live01.innovatv.tv.br/Hallo_Classic/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/37/channels-6a28cacfdcd24.png",
        "category": "Filmes",
    },
    {
        "name": "HALLO! Movies",
        "url": "https://live01.innovatv.tv.br/Hallo_Movies/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/18/channels-6a28cd2ba70a6.png",
        "category": "Filmes",
    },
    {
        "name": "HALLO! Movies 2",
        "url": "https://live01.innovatv.tv.br/Hallo_Movies2/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/40/channels-6a28db99d91a6.png",
        "category": "Filmes",
    },
    {
        "name": "Os Detetives",
        "url": "https://video11.logicahost.com.br/detetives/detetives/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/34/channels-6a74d7228d1fe.png",
        "category": "Filmes",
    },
    {
        "name": "DumDum",
        "url": "https://live01.innovatv.tv.br/DumDum_720/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/11/channels-6a28c40fda318.png",
        "category": "Infantil",
    },
    {
        "name": "HALLO! Anime",
        "url": "https://live01.innovatv.tv.br/Hallo_Anime/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/15/channels-6a28c715526e3.png",
        "category": "Infantil",
    },
    {
        "name": "Kids Mais",
        "url": "https://stmv1.transmissaodigital.com/tvkidmais/tvkidmais/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/15/channels-6a74e4432806e.png",
        "category": "Infantil",
    },
    {
        "name": "FM TV",
        "url": "https://video08.logicahost.com.br/fmtvbr/fmtvbr/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/10/channels-6a74d8a9267bc.png",
        "category": "Musica",
    },
    {
        "name": "HALLO! Music",
        "url": "https://live01.innovatv.tv.br/Hallo_Music/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/8/channels-6a28ce35c5eda.png",
        "category": "Musica",
    },
    {
        "name": "BM&C News",
        "url": "https://live01.innovatv.tv.br/Bmc_720/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/15/channels-6a28c1e199e92.png",
        "category": "Noticias",
    },
    {
        "name": "Canal UOL",
        "url": "https://live01.innovatv.tv.br/Uol_720/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/07/13/28/channels-6a55a60a0c0d2.png",
        "category": "Noticias",
    },
    {
        "name": "Oeste TV",
        "url": "https://live01.innovatv.tv.br/OesteTV_720/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/39/channels-6a28d11c408de.png",
        "category": "Noticias",
    },
    {
        "name": "Republic",
        "url": "https://flu.playgo.tv.br/republic/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/23/channels-6a28d4c7ba0da.png",
        "category": "Noticias",
    },
    {
        "name": "Times Brasil CNBC",
        "url": "https://live01.innovatv.tv.br/Cnbc_720/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/07/14/27/channels-6a55a784d8abe.png",
        "category": "Noticias",
    },
    {
        "name": "TV Judaica",
        "url": "https://streaming.tvjudaica.com/main.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/21/channels-6a28de878c085.png",
        "category": "Religioso",
    },
    {
        "name": "HALLO! Series",
        "url": "https://live01.innovatv.tv.br/Hallo_Series/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/8/channels-6a28cf291186c.png",
        "category": "Series",
    },
    {
        "name": "Séries Classic",
        "url": "https://video10.logicahost.com.br/serieclassic/serieclassic/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/07/14/1/channels-6a55a70d5dd8d.png",
        "category": "Series",
    },
    {
        "name": "Assim é Portugal",
        "url": "https://video04.logicahost.com.br/assimeportugal/assimeportugal/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/43/channels-6a74e6733a552.png",
        "category": "Variedades",
    },
    {
        "name": "Blits TV",
        "url": "https://stmv1.transmissaodigital.com/blitstv/blitstv/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/45/channels-6a28e237f2d02.png",
        "category": "Variedades",
    },
    {
        "name": "HALLO! Brasil",
        "url": "https://live01.innovatv.tv.br/Hallo_Brasil/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/09/3/channels-6a28c90f895d9.png",
        "category": "Variedades",
    },
    {
        "name": "Masper TV",
        "url": "https://tv02.zas.media:1936/masper/masper/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/07/14/28/channels-6a55a669ee744.png",
        "category": "Variedades",
    },
    {
        "name": "Pet Lovers TV",
        "url": "https://video04.logicahost.com.br/petloverstv/petloverstv/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/08/06/41/channels-6a74eafbb49e3.png",
        "category": "Variedades",
    },
    {
        "name": "TV Sonata",
        "url": "https://video04.logicahost.com.br/isonata/isonata/playlist.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/06/10/42/channels-6a28d7f7bbfa8.png",
        "category": "Variedades",
    },
    {
        "name": "U Channel",
        "url": "https://flu.playgo.tv.br/uchannel/index.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/10/21/27/channels-6ad906648ac01.png",
        "category": "Variedades",
    },
    {
        "name": "Unique TV",
        "url": "https://pop.uniquetv.com.br/hls/uniquetv.m3u8",
        "logo": "https://mw.innova.tv.br/assets/channels/2026/07/14/24/channels-6a55aad890941.png",
        "category": "Variedades",
    },
]


# --------------------------------------------------------------------------- #
# HTTP (headers fieis ao portal)
# --------------------------------------------------------------------------- #
def api_post(metodo, corpo):
    """POST em /api/Devices/Motv/<metodo> com corpo JSON.
    Content-Type: text/plain;charset=UTF-8 (como o portal real envia).
    A API SMS da MOTV espera o payload envolvido em {"data": {...}}.
    Retorna (status, response).
    """
    url = API_BASE + "/Devices/Motv/" + metodo
    envelope = {"data": corpo} if not (isinstance(corpo, dict) and "data" in corpo) else corpo
    data = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "text/plain;charset=UTF-8")
    req.add_header("Accept", "*/*")
    req.add_header("Accept-Language", "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7")
    req.add_header("Origin", PORTAL_URL)
    req.add_header("Referer", PORTAL_URL + "/")
    req.add_header("User-Agent", UA)
    req.add_header("DNT", "1")
    req.add_header("Sec-Fetch-Dest", "empty")
    req.add_header("Sec-Fetch-Mode", "cors")
    req.add_header("Sec-Fetch-Site", "same-site")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        dbg("HTTPError %s: %s" % (e.code, raw[:300]))
    except Exception as e:
        log("  [erro] POST %s falhou: %s" % (metodo, e))
        return None, None
    try:
        j = json.loads(raw)
    except Exception:
        dbg("resposta nao-JSON de %s: %s" % (metodo, raw[:200]))
        return None, raw
    return j.get("status"), j.get("response")


def obter_catalogo_da_api():
    """Fluxo MOTV: getPortal -> (login opcional) -> getData(device_id).
    Retorna o objeto 'response' do getData (arvore JSON) ou None.
    """
    global MOTV_VENDOR_ID
    device_id = os.environ.get("INNOVA_DEVICE_ID", "").strip()
    if not device_id:
        device_id = str(uuid.uuid4())
        log("  device_id gerado: %s" % device_id)
        log("  (dica: defina INNOVA_DEVICE_ID com o device do seu navegador logado p/ pegar o catalogo completo)")

    # getPortal confirma portal Innova (motv_portals_id=1)
    st, resp = api_post("getPortal", {"motvPortalsId": MOTV_PORTAL_ID})
    if st == 1 and isinstance(resp, dict):
        nome = resp.get("motv_portals_name", "")
        log("  getPortal OK: %s (id=%s, vendor=%s)" % (
            nome,
            resp.get("motv_portals_id"),
            resp.get("motv_portals_motv_vendors_id"),
        ))
        if resp.get("motv_portals_motv_vendors_id"):
            MOTV_VENDOR_ID = int(resp["motv_portals_motv_vendors_id"])
    else:
        log("  getPortal status=%s response=%s" % (st, str(resp)[:120]))

    login = os.environ.get("INNOVA_LOGIN", "").strip()
    senha = os.environ.get("INNOVA_SENHA", "").strip()
    base = {
        "device_id": device_id,
        "motv_portals_id": MOTV_PORTAL_ID,
        "motv_vendors_id": MOTV_VENDOR_ID,
        "language": LANG,
    }
    if login and senha:
        base["login"] = login
        base["password"] = senha
        log("  tentando getData com login da conta...")

    st, resp = api_post("getData", base)
    if st == 1 and resp:
        log("  getData OK.")
        if DEBUG and isinstance(resp, dict):
            dbg("chaves top-level getData: %s" % list(resp.keys())[:30])
        return resp
    log("  getData status=%s response=%s" % (st, str(resp)[:160]))
    return None


# --------------------------------------------------------------------------- #
# Categorias: unificacao por caixa + sinonimos
# --------------------------------------------------------------------------- #
SINONIMOS = {
    # Noticias
    "noticias": "Noticias", "news": "Noticias", "jornalismo": "Noticias",
    "noticia": "Noticias", "informacao": "Noticias", "info": "Noticias",
    # Infantil
    "desenhos": "Infantil", "desenho": "Infantil", "kids": "Infantil",
    "infantil": "Infantil", "crianca": "Infantil", "criancas": "Infantil",
    "cartoon": "Infantil", "animacao": "Infantil", "anime": "Infantil",
    # Filmes
    "cinema": "Filmes", "filmes": "Filmes", "filme": "Filmes",
    "movies": "Filmes", "movie": "Filmes", "hallo": "Filmes",
    # Series
    "series": "Series", "serie": "Series", "tv shows": "Series",
    "shows": "Series",
    # Esportes
    "esportes": "Esportes", "esporte": "Esportes", "sports": "Esportes",
    "sport": "Esportes", "futebol": "Esportes", "nsports": "Esportes",
    # Documentarios
    "documentarios": "Documentarios", "documentario": "Documentarios",
    "documentaries": "Documentarios", "docs": "Documentarios",
    # Musica
    "musica": "Musica", "music": "Musica", "musicas": "Musica",
    # Variedades
    "variedades": "Variedades", "entretenimento": "Variedades",
    "entertainment": "Variedades", "variety": "Variedades",
    # Abertos / Nacionais / Regionais
    "abertos": "Canais Abertos", "aberto": "Canais Abertos",
    "nacionais": "Canais Abertos", "tv aberta": "Canais Abertos",
    "regionais": "Canais Abertos", "regional": "Canais Abertos",
    # Religioso
    "religioso": "Religioso", "religiosos": "Religioso",
    "religiao": "Religioso", "gospel": "Religioso",
    # Adulto
    "adulto": "Adulto", "adultos": "Adulto", "adult": "Adulto",
    # Radio
    "radio": "Radio", "radios": "Radio", "musica ao vivo": "Radio",
}


def _norm(s):
    """minusculo, sem acento, sem espacos extras."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def categoria_canonica(nome):
    """Resolve a categoria final (unifica caixa + sinonimos)."""
    n = _norm(nome)
    if not n:
        return "Geral"
    if n in SINONIMOS:
        return SINONIMOS[n]
    for palavra in n.replace("/", " ").replace("-", " ").split():
        if palavra in SINONIMOS:
            return SINONIMOS[palavra]
    return " ".join(w.capitalize() for w in n.split())


# --------------------------------------------------------------------------- #
# Extracao recursiva de canais da arvore JSON do getData
# --------------------------------------------------------------------------- #
STREAM_RE = re.compile(
    r"https?://[^\s\"'<>]+\.(?:m3u8|m3u)(?:\?[^\s\"'<>]*)?",
    re.I,
)

# Chaves comuns em plataformas MOTV / middleware
NAME_KEYS = (
    "name", "title", "label", "channels_name", "channel_name",
    "channels_title", "displayname", "display_name", "nome",
    "channels_epg_name", "epg_name", "stream_name",
)
LOGO_KEYS = (
    "logo", "image", "cover", "icon", "thumbnail", "poster",
    "channels_logo", "channels_image", "picture", "img",
    "logo_url", "image_url", "channels_image_url",
)
CAT_KEYS = (
    "category", "categoria", "genre", "genres", "group",
    "group_title", "group-title", "channel_category",
    "channels_category", "section", "grupo", "categories",
    "channels_categories_name", "category_name",
)
URL_KEYS = (
    "url", "stream", "stream_url", "src", "source", "link",
    "playback_url", "manifest", "channels_url", "m3u8", "hls",
    "stream_source", "hls_url", "live_url", "play_url",
    "channels_stream_url", "url_hls",
)


def _primeiro_valor(d, chaves):
    chaves_l = {c.lower() for c in chaves}
    for k, v in d.items():
        if k.lower() in chaves_l and isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _achar_stream(d):
    # 1) campos tipicos de url
    for k, v in d.items():
        if isinstance(v, str) and k.lower() in {u.lower() for u in URL_KEYS}:
            m = STREAM_RE.search(v)
            if m:
                return m.group(0)
    # 2) qualquer string que pareca um .m3u8 / .m3u
    for v in d.values():
        if isinstance(v, str):
            m = STREAM_RE.search(v)
            if m:
                return m.group(0)
    return ""


def extrair_canais(no, categoria_herdada=""):
    """Percorre a arvore e devolve lista de dicts: name, url, logo, category."""
    achados = []

    if isinstance(no, dict):
        cat_propria = _primeiro_valor(no, CAT_KEYS)
        # categories pode ser lista
        if not cat_propria:
            for k, v in no.items():
                if k.lower() in ("categories", "genres", "groups") and isinstance(v, list) and v:
                    if isinstance(v[0], str):
                        cat_propria = v[0]
                    elif isinstance(v[0], dict):
                        cat_propria = _primeiro_valor(v[0], NAME_KEYS) or _primeiro_valor(v[0], CAT_KEYS)

        nome = _primeiro_valor(no, NAME_KEYS)
        url = _achar_stream(no)
        logo = _primeiro_valor(no, LOGO_KEYS)

        if url:
            achados.append({
                "name": nome or "Canal",
                "url": url,
                "logo": logo,
                "category": cat_propria or categoria_herdada or "Geral",
            })

        # se este dict e um "grupo" (tem nome e filhos), herda o nome como categoria
        cat_para_filhos = cat_propria or categoria_herdada
        tem_lista = any(isinstance(v, (list, dict)) for v in no.values())
        if nome and tem_lista and not url:
            cat_para_filhos = nome

        for v in no.values():
            if isinstance(v, (list, dict)):
                achados.extend(extrair_canais(v, cat_para_filhos))

    elif isinstance(no, list):
        for item in no:
            achados.extend(extrair_canais(item, categoria_herdada))

    return achados


# --------------------------------------------------------------------------- #
# Dedup por link m3u (mantem apenas um canal por URL)
# --------------------------------------------------------------------------- #
def deduplicar(canais):
    vistos = {}
    for c in canais:
        chave = c["url"].split("?")[0].strip().lower()
        if chave in vistos:
            # preferir o que tem logo / nome melhor
            ant = vistos[chave]
            if (not ant.get("logo")) and c.get("logo"):
                vistos[chave] = c
            continue
        c["category"] = categoria_canonica(c["category"])
        vistos[chave] = c
    return list(vistos.values())


# --------------------------------------------------------------------------- #
# Validacao de stream (liveness)
# --------------------------------------------------------------------------- #
def stream_ok(url):
    """Verifica se o link responde como HLS valido.
    Usa headers proximos aos do portal para reduzir bloqueios.
    """
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", UA)
        req.add_header("Referer", PORTAL_URL + "/")
        req.add_header("Origin", PORTAL_URL)
        req.add_header("Accept", "*/*")
        req.add_header("Accept-Language", "pt-BR,pt;q=0.9,en;q=0.7")
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx) as r:
            if r.status >= 400:
                return False
            head = r.read(4096).decode("utf-8", "replace")
            return (
                "#EXTM3U" in head
                or "#EXT-X" in head
                or ".ts" in head
                or ".m3u8" in head
                or "application/vnd.apple.mpegurl" in (r.headers.get("Content-Type") or "")
            )
    except Exception:
        return False


def validar_todos(canais):
    """Retorna dict url->bool. Guarda geo-block: se quase tudo falhar, nao penaliza."""
    resultado = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(stream_ok, c["url"]): c["url"] for c in canais}
        for f in as_completed(futs):
            resultado[futs[f]] = f.result()
    return resultado


# --------------------------------------------------------------------------- #
# Estado + regra das 3 falhas
# --------------------------------------------------------------------------- #
def carregar_estado():
    if os.path.exists(ESTADO_JSON):
        try:
            with open(ESTADO_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def salvar_estado(estado):
    with open(ESTADO_JSON, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def reconciliar(catalogo, estado, status_map):
    """Aplica: manter ativos, remover apos 3 falhas, adicionar novos.
    Retorna (lista_final, novo_estado).
    """
    novo = {}
    final = []
    agora = int(time.time())
    catalogo_por_url = {c["url"]: c for c in catalogo}

    # 1) canais do catalogo atual
    for url, c in catalogo_por_url.items():
        anterior = estado.get(url, {})
        falhas = anterior.get("falhas", 0)
        ok = status_map.get(url, True) if VALIDAR else True
        if ok:
            falhas = 0
        else:
            falhas += 1
        reg = {
            "name": c["name"],
            "logo": c.get("logo", ""),
            "category": c["category"],
            "falhas": falhas,
            "visto_em": agora,
        }
        novo[url] = reg
        if falhas < MAX_FALHAS:
            final.append({**c, "falhas": falhas})
        else:
            log("  [removido] %s (%d falhas seguidas)" % (c["name"], falhas))

    # 2) canais que estavam na lista antiga mas sumiram do catalogo nesta rodada
    for url, anterior in estado.items():
        if url in novo:
            continue
        falhas = anterior.get("falhas", 0) + 1
        anterior = {**anterior, "falhas": falhas, "visto_em": anterior.get("visto_em", agora)}
        if falhas < MAX_FALHAS:
            novo[url] = anterior
            final.append({
                "name": anterior.get("name", "Canal"),
                "url": url,
                "logo": anterior.get("logo", ""),
                "category": anterior.get("category", "Geral"),
                "falhas": falhas,
            })
        else:
            log("  [removido] %s (sumiu do catalogo por %d rodadas)"
                % (anterior.get("name", "Canal"), falhas))

    return final, novo


# --------------------------------------------------------------------------- #
# M3U
# --------------------------------------------------------------------------- #
def escrever_m3u(canais):
    canais = sorted(canais, key=lambda c: (c["category"].lower(), c["name"].lower()))
    linhas = ["#EXTM3U"]
    for c in canais:
        logo = c.get("logo", "") or ""
        nome = c["name"]
        cat = c["category"]
        safe_nome = nome.replace('"', "'")
        safe_cat = cat.replace('"', "'")
        attrs = 'tvg-name="%s" group-title="%s"' % (safe_nome, safe_cat)
        if logo:
            attrs = 'tvg-logo="%s" ' % logo.replace('"', "") + attrs
        linhas.append("#EXTINF:-1 %s,%s" % (attrs, nome))
        linhas.append(c["url"])
    os.makedirs(os.path.dirname(SAIDA_M3U), exist_ok=True)
    with open(SAIDA_M3U, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    return len(canais)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    log("=" * 64)
    log("Gerador de M3U - Innova TV (MOTV) para SS IPTV")
    log("=" * 64)

    estado = carregar_estado()
    log("Estado anterior: %d canais memorizados." % len(estado))

    # 1) obter arvore de dados (arquivo capturado tem prioridade)
    arvore = None
    cat_file = os.environ.get("INNOVA_CATALOGO", "").strip()
    if cat_file and os.path.exists(cat_file):
        log("Lendo catalogo do arquivo capturado: %s" % cat_file)
        with open(cat_file, "r", encoding="utf-8") as f:
            arvore = json.load(f)
        if isinstance(arvore, dict) and "response" in arvore:
            arvore = arvore["response"]
    else:
        log("Consultando a API MOTV...")
        arvore = obter_catalogo_da_api()

    # 2) extrair canais
    catalogo = []
    if arvore is not None:
        brutos = extrair_canais(arvore)
        log("Canais encontrados na fonte (com stream .m3u8): %d" % len(brutos))
        catalogo = deduplicar(brutos)
        log("Apos deduplicar por link m3u: %d" % len(catalogo))
    else:
        log("[aviso] Nao foi possivel obter o catalogo (login/regiao?). "
            "Preservando a lista anterior.")

    # 2b) incorporar seed de canais conhecidos (complementa / garante base minima)
    if USAR_SEED:
        seed = [dict(c) for c in SEED_CANAIS]
        for c in seed:
            c["category"] = categoria_canonica(c["category"])
        antes = len(catalogo)
        catalogo = deduplicar(catalogo + seed)
        if len(catalogo) > antes:
            log("Seed: +%d canais conhecidos incorporados (total %d)."
                % (len(catalogo) - antes, len(catalogo)))

    # Guarda anti-queda-geral: catalogo vazio mas havia estado -> nao apaga nada
    if not catalogo and estado:
        log("[protecao] Catalogo vazio nesta rodada; mantendo lista e estado atuais.")
        final = [{
            "name": v.get("name", "Canal"),
            "url": u,
            "logo": v.get("logo", ""),
            "category": v.get("category", "Geral"),
        } for u, v in estado.items() if v.get("falhas", 0) < MAX_FALHAS]
        n = escrever_m3u(final)
        log("Lista mantida com %d canais. Nada foi removido." % n)
        return

    # 3) validar streams (liveness) com guarda de geo-block
    status_map = {}
    if VALIDAR and catalogo:
        log("Validando %d streams..." % len(catalogo))
        status_map = validar_todos(catalogo)
        ok = sum(1 for v in status_map.values() if v)
        log("Streams online: %d / %d" % (ok, len(catalogo)))
        if catalogo and ok == 0:
            log("[protecao] Nenhum stream respondeu (provavel geo-block US / rede). "
                "Nao vou penalizar ninguem nesta rodada.")
            status_map = {c["url"]: True for c in catalogo}
        elif catalogo and ok < max(1, len(catalogo) // 4):
            log("[protecao] Poucos streams online (%d/%d). Provavel bloqueio de regiao. "
                "Nao vou penalizar canais nesta rodada." % (ok, len(catalogo)))
            status_map = {c["url"]: True for c in catalogo}

    # 4) reconciliar (regra das 3 falhas)
    final, novo_estado = reconciliar(catalogo, estado, status_map)
    salvar_estado(novo_estado)

    # 5) escrever M3U
    n = escrever_m3u(final)

    # resumo de categorias
    cats = {}
    for c in final:
        cats[c["category"]] = cats.get(c["category"], 0) + 1
    log("-" * 64)
    log("Lista gerada: %s" % SAIDA_M3U)
    log("Total de canais: %d  |  Categorias: %d" % (n, len(cats)))
    for k in sorted(cats):
        log("   - %-24s %d" % (k, cats[k]))
    log("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
