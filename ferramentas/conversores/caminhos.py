"""Onde fica o checkout do editor-imagens (o case), de onde os conversores leem e para onde gravam.

Os conversores rodam só com o ambiente Python do editor-imagens (torch, onnx, onnxruntime,
transformers, spandrel, numpy, Pillow) e usam arquivos de lá: models/BiRefNet/, exemplos/*.jpg,
html/montar.py, html/verificar.py, html/ferramentas/preparar_blocos.py e referencias_ia.py.

    export EDITOR_IMAGENS=CAMINHO/editor-imagens
"""
import os
import sys
from pathlib import Path


def raiz_editor() -> Path:
    valor = os.environ.get("EDITOR_IMAGENS")
    if not valor:
        raise SystemExit("Defina EDITOR_IMAGENS com a pasta do checkout do editor-imagens "
                         "(ex.: export EDITOR_IMAGENS=CAMINHO/editor-imagens).")
    raiz = Path(valor).expanduser().resolve()
    if not (raiz / "html" / "ferramentas").is_dir():
        raise SystemExit(f"{raiz} não parece o editor-imagens: falta html/ferramentas/.")
    return raiz


RAIZ = raiz_editor()
# Ferramentas do case que os conversores usam e não foram copiadas (medição): ficam depois desta pasta.
_CASE = str(RAIZ / "html" / "ferramentas")
if _CASE not in sys.path:
    sys.path.append(_CASE)
