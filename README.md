# omnitech-dependencies

Blocos prontos para as ferramentas de arquivo único da Omniteca: motores, modelos de IA e fontes que
vão dentro de um HTML que funciona offline.

## Para que serve

Uma ferramenta de arquivo único (um `.html` que abre sem internet) precisa levar dentro tudo o que usa:
o motor que roda os modelos, os próprios modelos, o motor SQL, as fontes. Esses arquivos são grandes
e iguais para todas as ferramentas. Aqui eles ficam num lugar só, numa versão fixa, cada um com o
seu sha256, a sua origem e a sua licença.

O git guarda só a descrição dos blocos (`manifesto.json`), as licenças e as ferramentas. Os arquivos
grandes vão como anexos de uma *release* do GitHub.

## Os blocos da v1.0.0

| Bloco | Arquivo | Para quê | Licença |
|---|---|---|---|
| `ort-js` | `ort.webgpu.bundle.min.mjs` | ONNX Runtime Web 1.30.0 (roda os modelos) | MIT |
| `ort-wasm` | `ort-wasm-simd-threaded.asyncify.wasm` | ONNX Runtime Web 1.30.0 (o motor em WebAssembly) | MIT |
| `modelo-fundo` | `birefnet_lite_768.onnx` | Tirar fundo (BiRefNet_lite a 768 px) | MIT |
| `modelo-apagar` | `migan_pipeline_v2.onnx` | Apagar com pincel (MI-GAN) | MIT |
| `modelo-melhorar` | `realesr-general-x4v3.onnx` | Melhorar, ampliando 4x (Real-ESRGAN) | BSD-3-Clause |
| `sqljs-js` | `sql-wasm-browser.js` | SQL.js 1.14.2 (SQLite 3.49.1) | MIT |
| `sqljs-wasm` | `sql-wasm-browser.wasm` | SQL.js 1.14.2 (o motor em WebAssembly) | MIT |
| `duckdb-js` | `duckdb-blocking-bundle.js` | DuckDB-Wasm 1.32.0 sem Worker, com Apache Arrow 17.0.0 | MIT (com partes Apache-2.0 e 0BSD) |
| `duckdb-wasm` | `duckdb-eh.wasm` | DuckDB 1.4.3 em WebAssembly | MIT |
| `fonte-poppins-regular` | `Poppins-Regular.woff2` | Fonte da marca, peso 400 | OFL-1.1 |
| `fonte-poppins-semibold` | `Poppins-SemiBold.woff2` | Fonte da marca, peso 600 | OFL-1.1 |

Os detalhes de cada bloco (sha256, tamanho, tamanho em gzip, origem exata, comando que o gerou, entrada
e saída dos modelos) estão no `manifesto.json`. Os textos das licenças, com o aviso de copyright de
cada projeto de origem, estão em `LICENSES/`. Os avisos de terceiros que vêm dentro dos binários estão
em `LICENSES/terceiros-onnxruntime.txt` e `LICENSES/terceiros-duckdb-wasm.txt`.

## Como uma skill usa

1. Lê o `manifesto.json` (a skill leva uma cópia dele, da versão que usa).
2. Baixa só os blocos de que precisa, de `url_base` + `arquivo`. Exemplo:
   `https://github.com/mbsbrands/omnitech-dependencies/releases/download/v1.0.0/birefnet_lite_768.onnx`.
3. Confere o sha256 de cada bloco antes de usar. Se não bater, ou se a *release* não responder, para
   e diz o que fazer: anexar os blocos no chat ou usar uma cópia local.
4. Embute os blocos no HTML. A página final não pede nada à rede.

Sem acesso ao GitHub, a skill aceita uma pasta local com os mesmos arquivos. A conferência pelo
sha256 é a mesma.

## Por que é público

Uma *release* é uma versão fechada do repositório no GitHub, com arquivos anexados que qualquer um
baixa por um endereço fixo.

- O Claude no navegador (Claude Web) não consegue fazer login para baixar de um repositório privado.
  Por isso os blocos precisam estar num repositório público.
- O assistente (Claude) baixa os blocos direto da *release*, sem login nem token.
- Nada aqui é segredo: são bibliotecas e modelos abertos, com a licença de cada um.
- O repositório não leva dado da empresa, dado de cliente, segredo nem nome de pessoa (fora dos avisos
  de copyright de terceiros, que as licenças exigem, em `LICENSES/`).

## Regras

- Uma versão publicada nunca é sobrescrita. Qualquer mudança em qualquer bloco vira uma versão nova
  (`v1.0.1`, `v1.1.0`...), com outro `url_base`.
- Cada sha256 vem da fonte que gerou o bloco e é conferido antes de publicar e depois de publicar.
- Arquivos grandes não entram no git (`.gitignore`): só na *release*.

## Como publicar uma versão

Precisa de Python 3, Node 20 ou mais novo (para o DuckDB) e de um checkout do `editor-imagens` com os
blocos de imagem em `html/blocos/`.

```sh
# 1. testes
python3 -m unittest discover -s testes

# 2. monta dist/v1.0.0/ com os 11 blocos e o manifesto, conferindo cada sha256
python3 ferramentas/montar_release.py --origem-imagem CAMINHO/editor-imagens/html/blocos

# 3. confere a pasta montada
python3 ferramentas/verificar_release.py --pasta dist/v1.0.0
```

O montador para no primeiro bloco que não bate e não deixa a `dist/` pela metade. No fim, ele
imprime o comando `gh release create`, mas não o executa. A publicação (push e *release*) é feita
por quem tem a aprovação, e só depois dela:

```sh
git push origin main
gh release create v1.0.0 --repo mbsbrands/omnitech-dependencies ...   # o comando impresso pelo montador
python3 ferramentas/verificar_release.py   # baixa cada bloco da release publicada e confere o sha256
```

Opções do montador:

- `--origem-fontes PASTA`: onde estão os `.woff2` (padrão: `<origem-imagem>/../fonte/fontes`).
- `--cache PASTA`: onde o sql.js e o DuckDB são baixados e montados (padrão: `~/.cache/omnitech-dependencies`).

## Ferramentas

- `ferramentas/montar_release.py`: monta a `dist/v<versao>/`. Pega os blocos de imagem do
  `editor-imagens`, baixa o pacote npm do sql.js 1.14.2 e gera os blocos do DuckDB.
- `ferramentas/verificar_release.py`: confere a *release* publicada (`--url-base`, padrão do
  manifesto) ou uma pasta local (`--pasta`). Sai com erro e diz qual bloco falhou.
- `ferramentas/embalar_duckdb.py`: gera `duckdb-blocking-bundle.js` e `duckdb-eh.wasm`. Usa os mesmos
  pacotes, os mesmos hashes e o mesmo comando do esbuild do `embutir_motor.py` da skill
  `omniteca-dados-html`. Gerado duas vezes, do zero, sai com o mesmo sha256.

Essas três usam só a biblioteca padrão do Python. A exceção é o `embalar_duckdb.py`, que chama o npm.

## Conversores

`ferramentas/conversores/` guarda como os modelos foram gerados. São cópias das ferramentas do
`editor-imagens` (o case), com os hashes de origem fixados sem mudança: pesos, commits e código do
BiRefNet. Só mudaram os caminhos.

Eles **só rodam com o ambiente Python do editor-imagens** (o `.venv` de lá, com torch, onnx,
onnxruntime, transformers e spandrel). Também usam arquivos de lá: `models/BiRefNet/`,
`exemplos/*.jpg`, `html/montar.py`, `html/verificar.py`, `html/ferramentas/preparar_blocos.py` e
`referencias_ia.py`. Antes de rodar, aponte para o checkout:

```sh
export EDITOR_IMAGENS=CAMINHO/editor-imagens
$EDITOR_IMAGENS/.venv/bin/python ferramentas/conversores/converter_birefnet_lite.py
$EDITOR_IMAGENS/.venv/bin/python ferramentas/conversores/exportar_esrgan.py
$EDITOR_IMAGENS/.venv/bin/python ferramentas/conversores/deform_amostragem.py   # teste da convolução
```

Os blocos gerados vão para `html/blocos/` do editor-imagens. Depois, o `montar_release.py` os copia
e confere contra este `manifesto.json`.

O `exportar_esrgan.py` repete o sha256 da v1.0.0 só com as mesmas versões de torch (2.15.0) e
spandrel (0.4.2). Com outras, o resultado vira uma versão nova.

Origem de cada arquivo: a cópia é do `editor-imagens` no commit `721d875`. O sha256 abaixo é o do
arquivo original, antes da troca dos caminhos.

| Arquivo aqui | Original no editor-imagens | sha256 do original |
|---|---|---|
| `converter_birefnet_lite.py` | `html/ferramentas/converter_birefnet_lite.py` | `68404e5f6a2f205660659692be8d682a49c0c5c0bc5097da5cb9351687172ade` |
| `codigo_birefnet.py` | `html/ferramentas/codigo_birefnet.py` | `456922e0a28d59de0685729a06025e2a8b87c01d6521df0cfb2a43559978d271` |
| `deform_amostragem.py` | `html/ferramentas/deform_amostragem.py` | `d1f9d23dbee568d53f3d3b73d7262169cc69b48f0ca3833348834633ce84b0e7` |
| `manifesto_blocos.py` | `html/ferramentas/manifesto_blocos.py` | `db017c5ef80b6c3205ba62ed635077ff2cf60ac3566d4f8a6e7e8afc257d3b79` |
| `exportar_esrgan.py` | trecho de `html/ferramentas/preparar_blocos.py` (`baixar`, `exportar_esrgan`, `CMD_ESRGAN`) | `7ae383315da53cea70b73e8db2860a278d5008cf6b0fa6eb012791a393ac4854` |
| `caminhos.py` | novo: lê `EDITOR_IMAGENS` | — |

Hashes de origem fixados nos conversores:

- pesos do BiRefNet_lite: `ZhengPeng7/BiRefNet_lite`, commit `aa62cd87eafb9cc43056d08ef3615a14628b831d`, `model.safetensors` sha256 `4417d89795250e698c3cb0ae8df15743810065f646f48a694fdfa7ca052d0815`;
- código do BiRefNet: `ZhengPeng7/BiRefNet`, commit `e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4`, com o sha256 de `birefnet.py`, `BiRefNet_config.py` e `config.json` em `codigo_birefnet.py`;
- Real-ESRGAN: `realesr-general-x4v3.pth` da v0.2.5.0, sha256 `8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292`;
- MI-GAN: baixado sem conversão, `andraniksargsyan/migan`, commit `406830d0fa60666da0071c342ad2fbc8f30c5c64`;
- ONNX Runtime Web: pacote npm `onnxruntime-web@1.30.0`, arquivos de `dist/` sem mudança.

## Testes

```sh
python3 -m unittest discover -s testes
```

- `testes/test_manifesto.py` confere o manifesto:
  - todos os campos, sha256 de 64 hexadecimais e licença conhecida, com o arquivo dela;
  - nomes sem repetição e `url_base` com a versão;
  - nenhum caminho local e nenhum nome de quem roda os testes.
- `testes/test_ferramentas.py` confere as ferramentas:
  - hash errado faz o montador parar;
  - pasta completa passa;
  - o verificador reprova bloco alterado ou fora do ar;
  - os hashes fixados nas ferramentas são os do manifesto.
