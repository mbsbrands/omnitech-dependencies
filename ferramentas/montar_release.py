#!/usr/bin/env python3
"""Monta a pasta da release (dist/v<versao>/) com todos os blocos do manifesto.json, conferidos.

Uso:
  python3 ferramentas/montar_release.py --origem-imagem CAMINHO/editor-imagens/html/blocos [--origem-fontes PASTA] [--cache PASTA]

De onde vem cada bloco:
  ort-js, ort-wasm, modelo-*   da pasta --origem-imagem (os blocos do editor-imagens);
  fonte-poppins-*              da pasta --origem-fontes (padrão: <origem-imagem>/../fonte/fontes);
  sqljs-js, sqljs-wasm         do pacote npm sql.js 1.14.2, baixado para o --cache e conferido;
  duckdb-js, duckdb-wasm       gerados por embalar_duckdb.py no --cache (precisa de Node e npm).

Confere o tamanho e o sha256 de cada bloco contra o manifesto, na ordem dele, e para no primeiro
que não bate. Monta numa pasta temporária ao lado e só no fim troca a dist/v<versao>/: se algo
falha, a pasta anterior fica como estava. Copia também o manifesto.json.

No fim, imprime o comando `gh release create` para quem publica rodar. Não executa nada no
GitHub. Só biblioteca padrão (e o embalar_duckdb.py, que chama o npm).
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
REPOSITORIO = "mbsbrands/omnitech-dependencies"
CACHE_PADRAO = os.path.join(os.path.expanduser("~"), ".cache", "omnitech-dependencies")

# Iguais aos de embutir_motor.py (omniteca-dados-html/scripts): não mudar sem mudar lá.
SQLJS = {
    "url": "https://registry.npmjs.org/sql.js/-/sql.js-1.14.2.tgz",
    "js": ("package/dist/sql-wasm-browser.js", "35e39a73b2e0bc1c2202a4cadb23bcf7a3a77071a39c270f014402968785b95f"),
    "wasm": ("package/dist/sql-wasm-browser.wasm", "38c14f6e379210bc942bdc4ebca44e7bfdb4318ecc1c72ca666a28fdce96670a"),
}
DO_EDITOR = ("ort-js", "ort-wasm", "modelo-fundo", "modelo-apagar", "modelo-melhorar")


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for parte in iter(lambda: f.read(1 << 20), b""):
            h.update(parte)
    return h.hexdigest()


def carregar_manifesto(caminho: Path = RAIZ / "manifesto.json") -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def conferir(bloco: dict, caminho: Path) -> None:
    """Para (SystemExit) se o arquivo falta ou não tem o tamanho e o sha256 do manifesto."""
    nome = bloco["nome"]
    if caminho is None or not Path(caminho).is_file():
        raise SystemExit(f"Bloco '{nome}': arquivo de origem não encontrado ({caminho}). Nada foi montado.")
    tamanho = Path(caminho).stat().st_size
    if tamanho != bloco["bytes"]:
        raise SystemExit(f"Bloco '{nome}': {tamanho:,} bytes, o manifesto pede {bloco['bytes']:,}. "
                         "Nada foi montado.")
    achado = sha256(caminho)
    if achado != bloco["sha256"]:
        raise SystemExit(f"Bloco '{nome}': sha256 {achado}, o manifesto pede {bloco['sha256']}. "
                         "Nada foi montado.")


def montar(manifesto: dict, fontes: dict, destino: Path, caminho_manifesto: Path) -> Path:
    """Confere e copia cada bloco (na ordem do manifesto) para `destino`, mais o manifesto.json."""
    destino = Path(destino)
    criou_dist = not destino.parent.exists()
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.parent / f".{destino.name}.parcial"
    if parcial.exists():
        shutil.rmtree(parcial)
    parcial.mkdir()
    try:
        for bloco in manifesto["blocos"]:
            origem = fontes.get(bloco["nome"])
            conferir(bloco, origem)
            shutil.copyfile(origem, parcial / bloco["arquivo"])
            conferir(bloco, parcial / bloco["arquivo"])
            print(f"ok  {bloco['nome']:24s} {bloco['arquivo']:40s} {bloco['bytes']:>12,} bytes")
        shutil.copyfile(caminho_manifesto, parcial / "manifesto.json")
    except BaseException:
        shutil.rmtree(parcial, ignore_errors=True)
        if criou_dist and not any(destino.parent.iterdir()):
            destino.parent.rmdir()  # só a pasta que esta chamada criou; uma --dist que já existia fica
        raise
    if destino.exists():
        shutil.rmtree(destino)
    parcial.rename(destino)
    return destino


def comando_gh(manifesto: dict, pasta: Path) -> str:
    """O comando para publicar a release. Só texto: quem publica roda depois de aprovar."""
    versao = manifesto["versao"]
    arquivos = [f"{pasta}/{b['arquivo']}" for b in manifesto["blocos"]] + [f"{pasta}/manifesto.json"]
    return (f"gh release create v{versao} --repo {REPOSITORIO} --title v{versao} "
            f"--notes \"Blocos v{versao} (ver manifesto.json e LICENSES/ no repositório)\" "
            + " ".join(arquivos))


def baixar_sqljs(cache: Path) -> dict:
    """Baixa o pacote do sql.js para o cache (se faltar) e extrai os dois blocos, conferindo o sha256."""
    cache = Path(cache)
    tgz = cache / "sql.js-1.14.2.tgz"
    if not tgz.exists():
        cache.mkdir(parents=True, exist_ok=True)
        parcial = tgz.with_suffix(".parcial")
        with urllib.request.urlopen(SQLJS["url"], timeout=120) as r, open(parcial, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        parcial.rename(tgz)
    pasta = cache / "sql.js-1.14.2"
    pasta.mkdir(parents=True, exist_ok=True)
    saida = {}
    with tarfile.open(tgz, "r:gz") as tar:
        for chave, nome in (("js", "sqljs-js"), ("wasm", "sqljs-wasm")):
            membro, esperado = SQLJS[chave]
            try:
                arquivo = tar.extractfile(membro)
            except KeyError:
                arquivo = None
            if arquivo is None:
                raise SystemExit(f"O pacote {tgz.name} no cache não tem o arquivo {membro}. "
                                 f"Apague {tgz} e rode de novo para baixá-lo outra vez. Nada foi montado.")
            dados = arquivo.read()
            if hashlib.sha256(dados).hexdigest() != esperado:
                raise SystemExit(f"{membro}: sha256 diferente do fixado. Nada foi montado.")
            alvo = pasta / Path(membro).name
            alvo.write_bytes(dados)
            saida[nome] = alvo
    return saida


def localizar_fontes(manifesto: dict, origem_imagem: Path, origem_fontes: Path, cache: Path) -> dict:
    """Caminho de origem de cada bloco do manifesto."""
    sys.path.insert(0, str(AQUI))
    import embalar_duckdb

    fontes = {}
    por_nome = {b["nome"]: b for b in manifesto["blocos"]}
    for nome in DO_EDITOR:
        fontes[nome] = Path(origem_imagem) / por_nome[nome]["arquivo"]
    for nome, b in por_nome.items():
        if nome.startswith("fonte-"):
            fontes[nome] = Path(origem_fontes) / b["arquivo"]
    fontes.update(baixar_sqljs(cache))
    js, wasm = embalar_duckdb.embalar(cache)
    fontes["duckdb-js"], fontes["duckdb-wasm"] = js, wasm
    return fontes


def main() -> None:
    p = argparse.ArgumentParser(description="Monta dist/v<versao>/ com todos os blocos, conferidos.")
    p.add_argument("--origem-imagem", required=True, help="pasta html/blocos do editor-imagens")
    p.add_argument("--origem-fontes", help="pasta com os .woff2 (padrão: <origem-imagem>/../fonte/fontes)")
    p.add_argument("--cache", default=CACHE_PADRAO, help="pasta para o sql.js e o DuckDB baixados")
    p.add_argument("--manifesto", default=str(RAIZ / "manifesto.json"))
    p.add_argument("--dist", default=str(RAIZ / "dist"))
    a = p.parse_args()
    manifesto = carregar_manifesto(a.manifesto)
    origem_imagem = Path(a.origem_imagem).expanduser()
    origem_fontes = Path(a.origem_fontes).expanduser() if a.origem_fontes else origem_imagem.parent / "fonte" / "fontes"
    fontes = localizar_fontes(manifesto, origem_imagem, origem_fontes, Path(a.cache).expanduser())
    destino = montar(manifesto, fontes, Path(a.dist) / f"v{manifesto['versao']}", Path(a.manifesto))
    total = sum(b["bytes"] for b in manifesto["blocos"])
    print(f"\nPronto: {len(manifesto['blocos'])} blocos ({total:,} bytes) e o manifesto em {destino}")
    print("\nPara publicar (só depois da aprovação, e nunca sobre uma versão já publicada):")
    try:
        relativo = destino.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        relativo = destino
    print("  " + comando_gh(manifesto, relativo))


if __name__ == "__main__":
    main()
