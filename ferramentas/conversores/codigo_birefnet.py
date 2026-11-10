"""Proveniência do código do BiRefNet que o converter_birefnet_lite.py usa (só biblioteca padrão).

Cópia de html/ferramentas/codigo_birefnet.py do editor-imagens (ver "Conversores" no README.md).
Os caminhos models/BiRefNet/ e editor/download_models.py abaixo são do repositório editor-imagens.

O código vem de uma cópia LOCAL em models/BiRefNet/ (fora do git, como todo models/), baixada pelo
editor Python (editor/download_models.py) do Hugging Face ZhengPeng7/BiRefNet no commit fixo abaixo.
Os git blob ids dos três arquivos batem com os do cache do Hugging Face nesse commit
(models/BiRefNet/.cache/huggingface/download/*.metadata), conferido em 09/11/2026.

Como models/ não é versionado, o sha256 de cada arquivo fica fixado aqui. O converter confere os
três antes de copiar e para se algum mudou. Nenhum código é baixado da rede na conversão.
"""
import hashlib
from pathlib import Path

HF_REPO = "ZhengPeng7/BiRefNet"
HF_REV = "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"  # o mesmo de editor/download_models.py

# sha256 dos arquivos de models/BiRefNet/ como estavam nesta máquina em 09/11/2026
SHA_CODIGO = {
    "birefnet.py": "208771ae626f653d64128fbf2d6ac9f8e645c5cc5e286258a73ec3322bbfe5ef",
    "BiRefNet_config.py": "e7b8c2a74f6cea6a59553d517f71d47f2c1d90e670a13416af17c25fe2f3dc52",
    "config.json": "c97ea21569daf66b205491a4635147dd3bc42c7c168b89d7d75b53f67ef548ae",
}

# A única mudança no código: o índice do backbone, de swin_v1_l (o BiRefNet completo) para
# swin_v1_t (o lite), em birefnet.py.
TROCA_BACKBONE = ("][6]", "][3]")
MUDANCA = "birefnet.py: índice do backbone '][6]' -> '][3]' (swin_v1_l -> swin_v1_t, a versão lite)"


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def conferir_codigo(pasta: Path) -> None:
    """Para (SystemExit) se algum dos três arquivos faltar ou não bater com o sha256 fixado."""
    erros = []
    for nome, esperado in SHA_CODIGO.items():
        arquivo = pasta / nome
        if not arquivo.is_file():
            erros.append(f"{nome}: não existe")
        elif (achado := _sha256(arquivo)) != esperado:
            erros.append(f"{nome}: sha256 {achado}, esperado {esperado}")
    if erros:
        raise SystemExit(
            f"O código do BiRefNet em {pasta} não é o conferido ({HF_REPO} commit {HF_REV}):\n  "
            + "\n  ".join(erros)
            + "\nNada foi copiado. Restaure models/BiRefNet/ com editor/download_models.py (commit fixo) "
              "ou revise o código e atualize SHA_CODIGO em ferramentas/conversores/codigo_birefnet.py.")


def trocar_backbone(codigo: str) -> str:
    antes, depois = TROCA_BACKBONE
    if codigo.count(antes) != 1:
        raise SystemExit(f"birefnet.py: esperava exatamente um '{antes}' (índice do backbone); o código mudou, revisar.")
    return codigo.replace(antes, depois)


def proveniencia() -> dict:
    """O que vai no item modelo-fundo do manifesto."""
    return {
        "repositorio": f"https://huggingface.co/{HF_REPO}",
        "commit": HF_REV,
        "copia_local": "models/BiRefNet/ do repositório editor-imagens (fora do git; baixada por editor/download_models.py)",
        "sha256": dict(SHA_CODIGO),
        "mudanca": MUDANCA,
    }
