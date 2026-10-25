# Lista M3U da Innova TV para o SS IPTV (auto-atualizavel)

Projeto pronto para o GitHub que gera uma lista `playlists/innova.m3u` a partir da
plataforma **MOTV/MW da Innova** (`portal.innova.tv.br` / `sms.innova.tv.br`), com
atualizacao automatica a cada **6 horas**.

Segue exatamente as suas regras:

- **Nao apaga canal que funciona.** So remove um canal depois de **3 atualizacoes
  seguidas** sem funcionar (regra das 3 falhas, guardada em `estado_canais.json`).
- **Canais separados por categoria** (`group-title`).
- **Unifica categorias por caixa:** `Noticias`, `NOTICIAS`, `noticias` viram uma so.
- **Unifica sinonimos:** ex. `noticias` + `News` -> **Noticias**;
  `Desenhos` + `kids` + `infantil` + `crianca` -> **Infantil**;
  `cinema` + `filmes` -> **Filmes** (mapa editavel, veja abaixo).
- **Dedup por link m3u:** canais com o mesmo link ficam com **apenas um**.
- **Logos** (`tvg-logo`) quando a fonte fornece, para ficar bonito no SS IPTV.
- **Seed de canais conhecidos** (CNBC, HALLO Movies, TV Pampa, Rede QDM, etc.)
  para garantir base minima mesmo se a API falhar fora do Brasil.
- **Headers fieis ao portal** (`Content-Type: text/plain`, Origin/Referer corretos).

> So usa a biblioteca padrao do Python (sem `pip install`).

---

## Como colocar no ar (passo a passo)

1. Crie um repositorio **privado** no GitHub e suba estes arquivos
   (ou use `git init` / `git push`).
2. Em **Settings -> Secrets and variables -> Actions**, crie os segredos abaixo
   (opcionais, mas recomendados para pegar o catalogo completo):
   - `INNOVA_DEVICE_ID` - o device do seu navegador ja logado (veja "Capturar").
   - `INNOVA_LOGIN` - e-mail da sua conta Innova.
   - `INNOVA_SENHA` - senha da sua conta Innova.
3. Em **Settings -> Actions -> General -> Workflow permissions**, marque
   **Read and write permissions**.
4. Pronto: o fluxo `.github/workflows/update.yml` roda a cada 6 horas
   (e pode ser disparado na mao em **Actions -> Run workflow**).

A URL da lista para colar no SS IPTV fica assim (repo privado -> use o link `raw`
com token, ou deixe so a pasta `playlists` publica):

```
https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/playlists/innova.m3u
```

---

## IMPORTANTE: gere a primeira vez no Brasil

O GitHub Actions roda em servidores **fora do Brasil (IP dos EUA)**. A API/streams
da Innova costumam ser **bloqueados por regiao** fora do Brasil, e so liberam o
catalogo completo a partir de um **IP brasileiro com a conta logada**.

Por isso:

- **Rode `rodar_no_brasil.bat` no seu PC (no Brasil)** para gerar a lista completa
  e faca o `git push`. Depois deixe o Actions apenas **atualizar** de 6 em 6 h.
- Se o Actions rodar nos EUA e nao conseguir o catalogo, o projeto **preserva a
  lista e o estado anteriores** (nao apaga nada) e nao conta como falha de canal.
  Assim os 3 "nao-funcionou" dos EUA nunca zeram a sua lista.
- Ha tambem uma **protecao extra**: se menos de 25% dos streams responderem,
  considera geo-block e **nao penaliza** nenhum canal.

### Capturar o catalogo do seu navegador (plano B, 100% garantido)

Se o login automatico nao pegar tudo, capture a resposta da propria API:

1. Abra `https://portal.innova.tv.br/` **logado**, pressione **F12 -> aba Network**.
2. Navegue ate a area de **canais ao vivo**. Procure a chamada
   `sms.innova.tv.br/api/Devices/Motv/getData`.
3. Clique nela -> **Response** -> **Copy** (copie o JSON inteiro).
4. Salve como `catalogo.json` na pasta do projeto e rode:
   - no `.bat`, descomente a linha `set INNOVA_CATALOGO=%~dp0catalogo.json`.
   O gerador le o arquivo e monta a lista sem depender de login/regiao.

> O `INNOVA_DEVICE_ID` pode ser pego no mesmo F12 (corpo da chamada `getData`,
> campo `device_id`) ou no `Application -> Local Storage` do portal. Trate device_id,
> login e senha como **segredos**.

### Confirmacao do portal (getPortal)

A API responde (exemplo real):

```json
{
  "motv_portals_id": 1,
  "motv_portals_name": "Innova",
  "motv_portals_url": "https://portal.innova.tv.br/",
  "motv_portals_motv_vendors_id": 1,
  "motv_portals_sections_v2": ["notifications","homepage","live","recordings","apps","my_list","catchup","vod","downloads","radio"],
  ...
}
```

O script usa `motvPortalsId: 1` e headers identicos aos do navegador
(`Content-Type: text/plain;charset=UTF-8`, Origin/Referer do portal).

---

## Tamanho MEDIO dos botoes no SS IPTV

O tamanho dos botoes/blocos (pequeno/medio/grande) **nao vem da lista M3U** - e um
ajuste do proprio aplicativo. No SS IPTV:

- Abra a lista -> **Menu/Configuracoes da playlist** -> opcao de **tamanho dos
  blocos/tiles** -> selecione **Medio**.

A lista ja entrega `group-title` (categorias) e `tvg-logo` (logos) para a tela
ficar organizada e bonita nesse tamanho.

> Dica: depois de atualizar a lista, **remova e adicione a playlist de novo** no
> SS IPTV para limpar o cache e carregar as mudancas.

---

## Editar categorias / sinonimos / seed

Abra `gerar_innova.py` e edite:

- **`SINONIMOS`** no topo: cada entrada e `"nome_normalizado": "Nome Exibido"`.
- **`SEED_CANAIS`**: lista de canais conhecidos que sempre entram (CNBC, HALLO Movies,
  TV Pampa, Rede QDM...). Acrescente quantos quiser no mesmo formato.

---

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `gerar_innova.py` | Gera a lista (API MOTV ou `catalogo.json`), aplica todas as regras |
| `playlists/innova.m3u` | A lista final (colar no SS IPTV) |
| `estado_canais.json` | Memoria das 3 falhas (nao apagar) |
| `.github/workflows/update.yml` | Atualizacao automatica a cada 6 h |
| `rodar_no_brasil.bat` | Gerar no seu PC no Brasil |

---

## Rodar no PC manualmente

```bat
python gerar_innova.py
```

Ou dois cliques em **`rodar_no_brasil.bat`**.

Variaveis uteis:

```bat
set INNOVA_DEBUG=1
set VALIDAR_STREAMS=0
set USAR_SEED=1
python gerar_innova.py
```
