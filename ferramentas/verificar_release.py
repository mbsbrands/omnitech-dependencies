#!/usr/bin/env python3
"""Confere uma release: cada bloco do manifesto.json tem o tamanho e o sha256 esperados.

Uso:
  python3 ferramentas/verificar_release.py                    # baixa da release publicada (url_base do manifesto)
  python3 ferramentas/verificar_release.py --url-base URL     # baixa de outra URL (termina em /)
  python3 ferramentas/verificar_release.py --pasta dist/v1.0.0  # confere uma pasta local

Também confere o manifesto.json da release, quando ele está lá: tem de ser igual ao do repositório.
Sai com código 1 e diz qual bloco falhou. Só biblioteca padrão.
"""
import argparse
import hashlib
import http.client
import sys
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from montar_release import RAIZ, carregar_manifesto  # noqa: E402

TEMPO_LIMITE_S = 60


def _medir(fluxo) -> tuple[int, str]:
    h, n = hashlib.sha256(), 0
    for parte in iter(lambda: fluxo.read(1 << 20), b""):
        h.update(parte)
        n += len(parte)
    return n, h.hexdigest()


def _comparar(bloco: dict, n: int, soma: str) -> str | None:
    if n != bloco["bytes"]:
        return f"{bloco['nome']} ({bloco['arquivo']}): {n:,} bytes, esperado {bloco['bytes']:,} (sha256 {soma})"
    if soma != bloco["sha256"]:
        return f"{bloco['nome']} ({bloco['arquivo']}): sha256 {soma}, esperado {bloco['sha256']}"
    return None


def verificar_pasta(manifesto: dict, pasta: Path, caminho_manifesto: Path | None = None) -> list[str]:
    """Lista de erros (vazia se tudo confere) para os blocos numa pasta local."""
    erros = []
    for bloco in manifesto["blocos"]:
        arquivo = Path(pasta) / bloco["arquivo"]
        if not arquivo.is_file():
            erros.append(f"{bloco['nome']} ({bloco['arquivo']}): não está na pasta")
            continue
        with open(arquivo, "rb") as f:
            erro = _comparar(bloco, *_medir(f))
        if erro:
            erros.append(erro)
        else:
            print(f"ok  {bloco['nome']}")
    if caminho_manifesto is not None:
        copia = Path(pasta) / "manifesto.json"
        if not copia.is_file() or copia.read_bytes() != Path(caminho_manifesto).read_bytes():
            erros.append("manifesto.json da pasta falta ou é diferente do manifesto do repositório")
    return erros


def verificar_url(manifesto: dict, url_base: str, caminho_manifesto: Path | None = None) -> list[str]:
    """Lista de erros (vazia se tudo confere) baixando cada bloco de url_base + arquivo."""
    if not url_base.endswith("/"):
        url_base += "/"
    erros = []
    for bloco in manifesto["blocos"]:
        url = url_base + bloco["arquivo"]
        try:
            with urllib.request.urlopen(url, timeout=TEMPO_LIMITE_S) as resposta:
                erro = _comparar(bloco, *_medir(resposta))
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            erro = f"{bloco['nome']} ({url}): não baixou ({type(e).__name__}: {e})"
        if erro:
            erros.append(erro)
        else:
            print(f"ok  {bloco['nome']}")
    if caminho_manifesto is not None:
        try:
            with urllib.request.urlopen(url_base + "manifesto.json", timeout=TEMPO_LIMITE_S) as resposta:
                igual = resposta.read() == Path(caminho_manifesto).read_bytes()
        except (urllib.error.URLError, http.client.HTTPException, OSError):
            igual = False
        if not igual:
            erros.append("manifesto.json da release falta ou é diferente do manifesto do repositório")
    return erros


def main() -> None:
    p = argparse.ArgumentParser(description="Confere os blocos de uma release contra o manifesto.json.")
    p.add_argument("--url-base", help="URL da release (padrão: url_base do manifesto)")
    p.add_argument("--pasta", help="pasta local com os blocos (em vez de baixar)")
    p.add_argument("--manifesto", default=str(RAIZ / "manifesto.json"))
    a = p.parse_args()
    manifesto = carregar_manifesto(a.manifesto)
    if a.pasta:
        onde = a.pasta
        erros = verificar_pasta(manifesto, Path(a.pasta), Path(a.manifesto))
    else:
        onde = a.url_base or manifesto["url_base"]
        erros = verificar_url(manifesto, onde, Path(a.manifesto))
    if erros:
        print(f"\nA release em {onde} NÃO confere ({len(erros)} problema(s)):")
        for e in erros:
            print("  - " + e)
        sys.exit(1)
    print(f"\nTudo confere: {len(manifesto['blocos'])} blocos e o manifesto em {onde}.")


if __name__ == "__main__":
    main()
