"""Gera o bloco do "Melhorar": Real-ESRGAN general x4v3 exportado para ONNX.

    export EDITOR_IMAGENS=CAMINHO/editor-imagens   # checkout do case, com o .venv (torch, spandrel, onnxruntime)
    $EDITOR_IMAGENS/.venv/bin/python ferramentas/conversores/exportar_esrgan.py

A exportação é a de html/ferramentas/preparar_blocos.py do editor-imagens (ver "Conversores" no README.md), separada
do resto daquele script (que também baixa o ORT e o MI-GAN e grava o manifesto do case):
1. baixa os pesos realesr-general-x4v3.pth da release v0.2.5.0 do Real-ESRGAN e confere o sha256;
2. exporta para ONNX opset 17 com altura e largura dinâmicas (torch.onnx.export, dynamo=False);
3. confere contra o PyTorch num recorte quadrado e num retangular de exemplos/caneca.jpg
   (diferença máxima abaixo de 1e-3);
4. imprime tamanho e sha256 e compara com o sha256 do bloco modelo-melhorar da v1.0.0.

Tudo fica em html/blocos/fonte-bruta/ do editor-imagens (fora do git), como no script original.
O sha256 só se repete com as mesmas versões (torch 2.15.0, spandrel 0.4.2): com outras, o arquivo
pode mudar e vira uma versão nova dos blocos, nunca a v1.0.0.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from caminhos import RAIZ  # noqa: E402  checkout do editor-imagens (variável EDITOR_IMAGENS)

BRUTA = RAIZ / "html" / "blocos" / "fonte-bruta"
BAIXADOS = BRUTA / "dl"
CONVERTIDOS = BRUTA / "conv"

PESOS = "realesr-general-x4v3.pth"
URL_PESOS = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"
SHA_PESOS = "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292"
# sha256 do bloco modelo-melhorar da v1.0.0 (manifesto.json), gerado com torch 2.15.0 e spandrel 0.4.2
SHA_BLOCO_V1 = "19ddb5fbc6ef878d7d5ebb1e353af3027b69ac3e6f75d004afecb0c0b1387147"

CMD_ESRGAN = (
    "spandrel.ModelLoader().load_from_file('realesr-general-x4v3.pth').model; "
    "torch.onnx.export(m, x[1,3,64,64], opset_version=17, dynamo=False, input_names=['input'], "
    "output_names=['output'], dynamic_axes={input:{2:'altura',3:'largura'}, output:{2:'altura4',3:'largura4'}}) "
    "(torch 2.15.0, spandrel 0.4.2; ver ferramentas/conversores/exportar_esrgan.py, vindo de preparar_blocos.py do editor-imagens)"
)


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for parte in iter(lambda: f.read(1 << 20), b""):
            h.update(parte)
    return h.hexdigest()


def baixar() -> Path:
    BAIXADOS.mkdir(parents=True, exist_ok=True)
    alvo = BAIXADOS / PESOS
    if not alvo.exists():
        print(f"Baixando {PESOS}...", flush=True)
        urllib.request.urlretrieve(URL_PESOS, alvo)
    if sha256(alvo) != SHA_PESOS:
        alvo.unlink()
        sys.exit(f"{PESOS} não confere com o sha256 esperado; apagado.")
    return alvo


def exportar_esrgan(pesos: Path) -> Path:
    import onnxruntime as ort
    import spandrel
    import torch

    saida = CONVERTIDOS / "realesr-general-x4v3.onnx"
    CONVERTIDOS.mkdir(parents=True, exist_ok=True)
    modelo = spandrel.ModelLoader().load_from_file(pesos).model.eval().float()
    if not saida.exists():
        torch.onnx.export(
            modelo, (torch.rand(1, 3, 64, 64),), str(saida), opset_version=17, dynamo=False,
            input_names=["input"], output_names=["output"],
            dynamic_axes={"input": {2: "altura", 3: "largura"}, "output": {2: "altura4", 3: "largura4"}},
        )
    # confere contra o PyTorch num recorte quadrado e num retangular (eixos realmente dinâmicos)
    sess = ort.InferenceSession(str(saida), providers=["CPUExecutionProvider"])
    foto = np.asarray(Image.open(RAIZ / "exemplos" / "caneca.jpg").convert("RGB"), dtype=np.float32) / 255
    difs = {}
    for h, w in ((64, 64), (48, 80)):
        x = np.ascontiguousarray(foto[500:500 + h, 800:800 + w].transpose(2, 0, 1))[None]
        with torch.inference_mode():
            ref = modelo(torch.from_numpy(x)).numpy()
        out = sess.run(None, {"input": x})[0]
        assert out.shape == (1, 3, 4 * h, 4 * w), out.shape
        difs[f"{h}x{w}"] = float(np.abs(out - ref).max())
    print("Real-ESRGAN ONNX x PyTorch (máx. diferença absoluta):", difs, flush=True)
    assert max(difs.values()) < 1e-3, difs
    return saida


def main() -> None:
    saida = exportar_esrgan(baixar())
    soma = sha256(saida)
    print(f"{saida.name}: {saida.stat().st_size:,} bytes, sha256 {soma}")
    if soma == SHA_BLOCO_V1:
        print("Igual ao bloco modelo-melhorar da v1.0.0.")
    else:
        print("Diferente do bloco modelo-melhorar da v1.0.0 (outra versão do torch ou do spandrel?). "
              "Não substitua um bloco publicado: isto seria uma versão nova.")


if __name__ == "__main__":
    main()
