"""Gera o bloco do "Tirar fundo": BiRefNet_lite a 768 px, pronto para o ONNX Runtime Web.

    export EDITOR_IMAGENS=CAMINHO/editor-imagens   # checkout do case, com o .venv (torch, onnx, onnxruntime...)
    $EDITOR_IMAGENS/.venv/bin/python ferramentas/conversores/converter_birefnet_lite.py           # conversão inteira
    $EDITOR_IMAGENS/.venv/bin/python ferramentas/conversores/converter_birefnet_lite.py --medir   # só mede o bloco atual

Cópia de html/ferramentas/converter_birefnet_lite.py do editor-imagens (ver "Conversores" no README.md), com os
hashes de origem fixados sem mudança. Só os caminhos mudaram: todos os caminhos html/... e models/...
abaixo são do checkout do editor-imagens, e o bloco gerado vai para html/blocos/ de lá (depois o
montar_release.py deste repositório o copia e confere).

Passos (tudo o que é grande fica em html/blocos/fonte-bruta/, fora do git):
1. Baixa só os pesos (model.safetensors, dados, nunca código) de ZhengPeng7/BiRefNet_lite num
   commit fixo e confere o sha256 antes de usar.
2. Monta a pasta do modelo com uma cópia LOCAL do código do BiRefNet, com sha256 fixado
   (codigo_birefnet.py): birefnet.py, BiRefNet_config.py e config.json de models/BiRefNet/, que o
   editor Python baixou do Hugging Face (ZhengPeng7/BiRefNet, commit e2bf8e44...). Confere os três
   sha256 antes de copiar e para se algum mudou. Muda uma linha: o índice do backbone, de `][6]`
   para `][3]` (swin_v1_t, a versão lite). Esse código roda localmente (trust_remote_code sobre a
   pasta local, local_files_only); nenhum código é baixado nem executado da rede na conversão.
3. Quatro transformações, nenhuma muda o resultado de forma visível:
   a. convolução deformável reescrita com grid_sample + conv 1x1 (deform_amostragem.py), sem os
      GatherND que estouram a memória do ORT Web;
   b. exportação ONNX opset 17 a 768x768, já com a sigmoide, e simplificação BASIC do ORT;
   c. Concat com mais de 6 entradas vira árvore de Concats (limite de 10 storage buffers por
      shader do WebGPU no Chrome);
   d. pesos de Conv/MatMul/Gemm em int8 por canal (DequantizeLinear sobre a constante); a conta
      continua em float.
4. Mede: diferença contra o fp32 e IoU / IoU de borda nas 6 fotos de html/medicoes.md contra o
   BiRefNet completo a 1024 px (referências em html/testes/dados/gerados/, geradas por
   gerar_dados_borda.py; as que faltarem são geradas aqui). Aceite: borda média >= 0,91. Grava as
   medidas brutas em html/medicoes/<data>-birefnet-lite-768-qualidade-6-fotos.json.
5. Confere o teto com o tamanho exato do HTML que sairia (manifesto_blocos.conferir_teto, contra
   verificar.TETO_BYTES). Só então copia o resultado para html/blocos/birefnet_lite_768.onnx, tira
   o bloco anterior do fundo e atualiza o item "modelo-fundo" de html/blocos/manifesto.json, com a
   proveniência do código (repositório, commit, sha256 e a linha mudada).

Pré e pós-processamento iguais aos de fonte/trabalho/ia.js (ver preparar() e mascara() abaixo).
"""
import datetime
import hashlib
import importlib.util
import json
import shutil
import sys
import urllib.request
from pathlib import Path

import numpy as np
import onnx
from onnx import helper, numpy_helper
from PIL import Image

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from caminhos import RAIZ  # noqa: E402  checkout do editor-imagens (variável EDITOR_IMAGENS)

HTML = RAIZ / "html"
BLOCOS = HTML / "blocos"
BRUTA = BLOCOS / "fonte-bruta" / "birefnet-lite"
CODIGO_PYTHON = RAIZ / "models" / "BiRefNet"
GERADOS = HTML / "testes" / "dados" / "gerados"
PASTA_MEDIDAS = HTML / "medicoes"
from codigo_birefnet import (HF_REPO, HF_REV, MUDANCA, SHA_CODIGO, conferir_codigo,  # noqa: E402
                             proveniencia, trocar_backbone)
from manifesto_blocos import com_os_preservados, conferir_teto, mesclar  # noqa: E402

REPO = "ZhengPeng7/BiRefNet_lite"
REV = "aa62cd87eafb9cc43056d08ef3615a14628b831d"  # HfApi().model_info(REPO).sha em 09/11/2026
URL_PESOS = f"https://huggingface.co/{REPO}/resolve/{REV}/model.safetensors"
TEMPO_LIMITE_S = 60  # sem resposta por 60 s (conexão ou leitura), o download para
SHA_PESOS = "4417d89795250e698c3cb0ae8df15743810065f646f48a694fdfa7ca052d0815"

LADO = 768
ARQUIVO = f"birefnet_lite_{LADO}.onnx"
MAX_CONCAT = 6
MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DESVIO = np.array([0.229, 0.224, 0.225], dtype=np.float32)
FOTOS = ["caneca", "tenis-marrom-1", "mochila", "bule-amarelo", "oculos-retro", "frasco-perfume"]
ACEITE_BORDA = 0.91

COMANDO = ("python ferramentas/conversores/converter_birefnet_lite.py (com o .venv do editor-imagens): pesos model.safetensors (sha256 "
           f"{SHA_PESOS}) com a cópia local do código de {HF_REPO} (commit {HF_REV}; birefnet.py sha256 "
           f"{SHA_CODIGO['birefnet.py']}, conferido antes da cópia) e uma linha mudada ({MUDANCA}); "
           "convolução deformável por grid_sample + conv 1x1 (ferramentas/conversores/deform_amostragem.py); torch.onnx.export opset 17, "
           f"entrada fixa [1,3,{LADO},{LADO}], saída com sigmoide; ORT_ENABLE_BASIC; Concat em árvore de até "
           f"{MAX_CONCAT} entradas; pesos de Conv/MatMul/Gemm em int8 por canal (DequantizeLinear), conta em float")


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for parte in iter(lambda: f.read(1 << 20), b""):
            h.update(parte)
    return h.hexdigest()


# ---------------------------------------------------------------- 1 e 2: pesos e pasta do modelo

def baixar_pesos() -> Path:
    """Só o safetensors (dados), numa pasta própria; confere o sha256 antes de qualquer uso."""
    pasta = BRUTA / f"pesos-{REV[:12]}"
    alvo = pasta / "model.safetensors"
    if not alvo.exists():
        pasta.mkdir(parents=True, exist_ok=True)
        print(f"Baixando {URL_PESOS} ...", flush=True)
        parcial = alvo.with_suffix(".parcial")
        with urllib.request.urlopen(URL_PESOS, timeout=TEMPO_LIMITE_S) as resposta, open(parcial, "wb") as f:
            shutil.copyfileobj(resposta, f, 1 << 20)
        parcial.rename(alvo)
    if sha256(alvo) != SHA_PESOS:
        alvo.unlink()
        sys.exit("model.safetensors não confere com o sha256 esperado; apagado.")
    return alvo


def montar_pasta_modelo(pesos: Path) -> Path:
    """Pasta nova com a cópia local do código do BiRefNet (sha256 conferido, uma linha mudada) e os
    pesos do lite."""
    conferir_codigo(CODIGO_PYTHON)  # para antes de copiar se algum dos três mudou
    pasta = BRUTA / "modelo"
    if pasta.exists():
        shutil.rmtree(pasta)
    pasta.mkdir(parents=True)
    for nome in SHA_CODIGO:
        shutil.copyfile(CODIGO_PYTHON / nome, pasta / nome)
    codigo = (pasta / "birefnet.py").read_text(encoding="utf-8")
    (pasta / "birefnet.py").write_text(trocar_backbone(codigo), encoding="utf-8")
    shutil.copyfile(pesos, pasta / "model.safetensors")
    return pasta


# ---------------------------------------------------------------- 3a e 3b: troca e exportação

def carregar_deform():
    spec = importlib.util.spec_from_file_location("deform_amostragem", AQUI / "deform_amostragem.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def exportar(pasta_modelo: Path, destino: Path) -> float:
    import torch
    from transformers import AutoModelForImageSegmentation

    deform = carregar_deform()
    modelo = AutoModelForImageSegmentation.from_pretrained(
        pasta_modelo, trust_remote_code=True, local_files_only=True).float().eval()
    classe = type(next(m for m in modelo.modules() if type(m).__name__ == "DeformableConv2d"))
    torch.manual_seed(0)
    x = torch.randn(1, 3, LADO, LADO)
    with torch.inference_mode():
        antes = modelo(x)[-1].sigmoid()
    deform.trocar_forward(classe)
    with torch.inference_mode():
        depois = modelo(x)[-1].sigmoid()
    dif = float((antes - depois).abs().max())
    print(f"troca da convolução deformável: dif. máx na saída {dif:.2e}", flush=True)

    class ComSigmoide(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, x):
            return self.m(x)[-1].sigmoid()

    destino.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(ComSigmoide(modelo), torch.zeros(1, 3, LADO, LADO), str(destino),
                      input_names=["input_image"], output_names=["output_image"], opset_version=17,
                      dynamo=False, do_constant_folding=True)
    return dif


def simplificar_basic(entrada: Path, saida: Path) -> None:
    import onnxruntime as ort

    opcoes = ort.SessionOptions()
    opcoes.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    opcoes.optimized_model_filepath = str(saida)
    ort.InferenceSession(str(entrada), opcoes, providers=["CPUExecutionProvider"])


# ---------------------------------------------------------------- 3c: Concat em árvore

def concat_em_arvore(m: onnx.ModelProto, n: int = MAX_CONCAT) -> int:
    """Concat é associativo no mesmo eixo: a árvore dá o mesmo resultado, com até n entradas por nó."""
    novos, trocados = [], 0
    for no in m.graph.node:
        if no.op_type != "Concat" or len(no.input) <= n:
            novos.append(no)
            continue
        eixo = next(a for a in no.attribute if a.name == "axis").i
        nivel, k = list(no.input), 0
        while len(nivel) > n:
            prox = []
            for i in range(0, len(nivel), n):
                grupo = nivel[i:i + n]
                if len(grupo) == 1:
                    prox.append(grupo[0])
                    continue
                nome = f"{no.name}_arvore_{k}"
                k += 1
                novos.append(helper.make_node("Concat", grupo, [nome + "_saida"], name=nome, axis=eixo))
                prox.append(nome + "_saida")
            nivel = prox
        novos.append(helper.make_node("Concat", nivel, list(no.output), name=no.name, axis=eixo))
        trocados += 1
    del m.graph.node[:]
    m.graph.node.extend(novos)
    return trocados


# ---------------------------------------------------------------- 3d: pesos em int8

def pesos_int8(m: onnx.ModelProto) -> int:
    """Pesos de Conv/MatMul/Gemm em int8 por canal de saída; o ORT dobra o DequantizeLinear ao abrir."""
    inits = {i.name: i for i in m.graph.initializer}
    eixos = {}
    for no in m.graph.node:
        if no.op_type in ("Conv", "MatMul", "Gemm") and len(no.input) > 1:
            trans_b = any(a.name == "transB" and a.i == 1 for a in no.attribute)
            eixos[no.input[1]] = 0 if (no.op_type == "Conv" or trans_b) else 1  # MatMul [entra, sai]: eixo 1
    novos_inits, novos_nos = [], []
    for nome, eixo in eixos.items():
        if nome not in inits:
            continue
        w = numpy_helper.to_array(inits[nome]).astype(np.float32)
        if w.ndim not in (2, 4) or w.size < 1024:
            continue
        outros = tuple(i for i in range(w.ndim) if i != eixo)
        maxabs = np.abs(w).max(axis=outros)
        escala = np.where(maxabs > 0, maxabs / 127.0, 1.0).astype(np.float32)
        forma = [1] * w.ndim
        forma[eixo] = -1
        q = np.clip(np.round(w / escala.reshape(forma)), -127, 127).astype(np.int8)
        m.graph.initializer.remove(inits[nome])
        novos_inits += [numpy_helper.from_array(q, nome + "_q"), numpy_helper.from_array(escala, nome + "_s"),
                        numpy_helper.from_array(np.zeros_like(escala, dtype=np.int8), nome + "_z")]
        novos_nos.append(helper.make_node("DequantizeLinear", [nome + "_q", nome + "_s", nome + "_z"], [nome],
                                          axis=eixo, name=nome + "_deq"))
    m.graph.initializer.extend(novos_inits)
    nos = list(m.graph.node)
    del m.graph.node[:]
    m.graph.node.extend(novos_nos + nos)
    if m.opset_import[0].version < 13:
        m.opset_import[0].version = 13
    return len(novos_nos)


# ---------------------------------------------------------------- 4: bloco e manifesto

def entrada_manifesto(bloco: Path) -> dict:
    import gzip

    dados = bloco.read_bytes()
    return {
        "nome": "modelo-fundo",
        "arquivo": bloco.name,
        "origem": f"{URL_PESOS} (pesos MIT, sha256 {SHA_PESOS}), com o código de https://huggingface.co/{HF_REPO} "
                  f"(commit {HF_REV}, cópia local em models/BiRefNet/ do editor-imagens com sha256 fixado; {MUDANCA}), "
                  "convertido para ONNX por nós",
        "codigo": proveniencia(),
        "versao": f"BiRefNet_lite (commit {REV}), {LADO} px, ONNX opset 17, pesos int8 por canal e conta em float",
        "licenca": "MIT",
        "sha256": hashlib.sha256(dados).hexdigest(),
        "bytes": len(dados),
        "bytes_gzip": len(gzip.compress(dados, compresslevel=9, mtime=0)),
        "comando": COMANDO,
        "entrada": {
            "altura": LADO, "largura": LADO, "layout": "NCHW", "tipo": "float32",
            "media": [0.485, 0.456, 0.406], "desvio": [0.229, 0.224, 0.225],
            "descricao": f"'input_image' [1,3,{LADO},{LADO}] RGB. Redimensionar a foto para {LADO}x{LADO} com "
                         "interpolação bilinear (sem manter proporção), dividir por 255 e aplicar "
                         "(x - media) / desvio por canal.",
        },
        "saida": {
            "forma": f"'output_image' [1,1,{LADO},{LADO}] float32",
            "significado": "Probabilidade de primeiro plano em 0..1 (já passou pela sigmoide). Ampliar para o "
                           "tamanho da foto (bilinear) e usar como alfa.",
        },
    }


def gravar_bloco(origem: Path) -> dict:
    """Confere o teto com o HTML que sairia, copia o bloco e grava o item modelo-fundo; os outros
    itens e arquivos ficam como estão."""
    destino = BLOCOS / ARQUIVO
    entrada = entrada_manifesto(origem)
    entrada["arquivo"] = destino.name
    atuais = json.loads((BLOCOS / "manifesto.json").read_text(encoding="utf-8"))
    outros = {e["nome"] for e in atuais if e["nome"] != "modelo-fundo"}
    conferir_teto(com_os_preservados(BLOCOS, [entrada]))  # para antes de copiar qualquer coisa
    if origem.resolve() != destino.resolve():
        shutil.copyfile(origem, destino)
    entradas = mesclar(BLOCOS, [entrada], preservar=outros)
    return next(e for e in entradas if e["nome"] == "modelo-fundo")


# ---------------------------------------------------------------- 5: medição

def preparar(foto: Image.Image) -> dict:
    """Igual ao ia.js: bilinear para LADO x LADO, /255, (x - média) / desvio, NCHW."""
    x = (np.asarray(foto.resize((LADO, LADO), Image.BILINEAR), dtype=np.float32) / 255 - MEDIA) / DESVIO
    return {"input_image": np.ascontiguousarray(x.transpose(2, 0, 1))[None]}


def mascara(saida: np.ndarray, tamanho: tuple[int, int]) -> np.ndarray:
    """Igual ao ia.js (antes do refino da borda): saída já em 0..1, bilinear até a foto, 0..255."""
    p = Image.fromarray(saida[0, 0].astype(np.float32), mode="F").resize(tamanho, Image.BILINEAR)
    return np.round(np.asarray(p).clip(0, 1) * 255).astype(np.uint8)


def referencia(nome: str, foto: Image.Image) -> np.ndarray:
    from referencias_ia import gravar_bruto, ler_bruto

    caminho = GERADOS / f"{nome}-ref.u8.gz"
    if not caminho.exists():
        from preparar_blocos import mascara_referencia

        gravar_bruto(caminho, np.round(mascara_referencia(foto) * 255).astype(np.uint8))
    return ler_bruto(caminho)[:, :, 0]


def medir(fp32: Path, final: Path) -> dict:
    import onnxruntime as ort

    from preparar_blocos import comparar

    s32 = ort.InferenceSession(str(fp32), providers=["CPUExecutionProvider"])
    s8 = ort.InferenceSession(str(final), providers=["CPUExecutionProvider"])
    linhas, dif_fp32 = {}, 0.0
    for nome in FOTOS:
        foto = Image.open(RAIZ / "exemplos" / f"{nome}.jpg").convert("RGB")
        x = preparar(foto)
        o8 = s8.run(None, x)[0]
        dif_fp32 = max(dif_fp32, float(np.abs(o8 - s32.run(None, x)[0]).max()))
        r = comparar(mascara(o8, foto.size) / 255, referencia(nome, foto) / 255)
        linhas[nome] = r
        print(f"  {nome:16s} IoU {r['iou']:.3f}  borda {r['iou_borda']:.3f}  dif. borda {r['dif_borda']:.3f}",
              flush=True)
    media = {k: float(np.mean([r[k] for r in linhas.values()])) for k in ("iou", "iou_borda", "dif_borda")}
    print(f"  {'média':16s} IoU {media['iou']:.3f}  borda {media['iou_borda']:.3f}  dif. borda {media['dif_borda']:.3f}")
    print(f"diferença máx. int8 x fp32 na saída (6 fotos): {dif_fp32:.4f}")
    return {"fotos": linhas, "media": media, "dif_fp32": dif_fp32}


def gravar_medidas(medidas: dict, fp32: Path, final: Path, modo: str, extra: dict | None = None) -> Path:
    """Grava as medidas brutas (sem arredondar) em html/medicoes/<data>-birefnet-lite-768-qualidade-6-fotos.json."""
    hoje = datetime.date.today().isoformat()
    destino = PASTA_MEDIDAS / f"{hoje}-birefnet-lite-{LADO}-qualidade-6-fotos.json"
    dados = {
        "ferramenta": f"ferramentas/conversores/converter_birefnet_lite.py (omnitech-dependencies){' --medir' if modo == 'medir' else ''}",
        "data": hoje,
        "o_que": f"BiRefNet_lite {LADO} px (int8, ORT CPU no Python) contra o BiRefNet completo a 1024 px "
                 "(html/testes/dados/gerados/<foto>-ref.u8.gz), sem refinarBorda; pré e pós iguais aos do ia.js. "
                 "iou: IoU da máscara binária (0,5); iou_borda: IoU na faixa de 8 px em volta da borda da "
                 "referência; dif_borda: diferença média do alfa (0..1) nessa faixa (preparar_blocos.comparar). "
                 "dif_int8_fp32: maior diferença por pixel na saída entre o bloco int8 e o fp32, nas 6 fotos.",
        "bloco": {"arquivo": final.name, "sha256": sha256(final)},
        "fp32": {"arquivo": fp32.name, "sha256": sha256(fp32)},
        "fotos": medidas["fotos"],
        "media": medidas["media"],
        "dif_int8_fp32": medidas["dif_fp32"],
        "aceite_borda_media": ACEITE_BORDA,
        **(extra or {}),
    }
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("medidas gravadas em", destino.relative_to(RAIZ))
    return destino


def so_medir() -> None:
    """Mede o bloco atual de html/blocos/ (sha256 do manifesto) contra o fp32 da última conversão."""
    conferir_codigo(CODIGO_PYTHON)
    fp32 = BRUTA / "conv" / f"lite{LADO}_fp32.onnx"
    if not fp32.exists():
        sys.exit(f"Falta {fp32.relative_to(RAIZ)}: rode a conversão inteira (sem --medir).")
    final = BLOCOS / ARQUIVO
    item = next(e for e in json.loads((BLOCOS / "manifesto.json").read_text(encoding="utf-8"))
                if e["nome"] == "modelo-fundo")
    if sha256(final) != item["sha256"]:
        sys.exit(f"{final.relative_to(RAIZ)} não confere com o manifesto.")
    gravar_medidas(medir(fp32, final), fp32, final, "medir")


def main() -> None:
    if sys.argv[1:] == ["--medir"]:
        so_medir()
        return
    conv = BRUTA / "conv"
    fp32, basic, final = conv / f"lite{LADO}_fp32.onnx", conv / f"lite{LADO}_basic.onnx", conv / ARQUIVO
    pesos = baixar_pesos()
    print("pesos conferidos:", pesos)
    pasta = montar_pasta_modelo(pesos)
    dif_troca = exportar(pasta, fp32)
    simplificar_basic(fp32, basic)
    m = onnx.load(str(basic))
    print("Concats em árvore:", concat_em_arvore(m))
    print("pesos em int8:", pesos_int8(m))
    onnx.checker.check_model(m)
    onnx.save(m, str(final))
    basic.unlink()
    print(f"{final.name}: {final.stat().st_size:,} bytes")
    medidas = medir(fp32, final)
    gravar_medidas(medidas, fp32, final, "conversao", {"dif_troca_deformavel_pytorch": dif_troca})
    if medidas["media"]["iou_borda"] < ACEITE_BORDA:
        sys.exit(f"IoU de borda médio {medidas['media']['iou_borda']:.3f} abaixo do aceite {ACEITE_BORDA}")
    e = gravar_bloco(final)
    print(f"bloco gravado: html/blocos/{e['arquivo']} ({e['bytes']:,} bytes, gzip {e['bytes_gzip']:,}, "
          f"sha256 {e['sha256']})")


if __name__ == "__main__":
    main()
