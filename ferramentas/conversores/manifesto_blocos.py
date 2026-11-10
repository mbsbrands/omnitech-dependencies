"""Grava html/blocos/manifesto.json sem perder os blocos que outra ferramenta gera (só biblioteca padrão).

Cópia de html/ferramentas/manifesto_blocos.py do editor-imagens (ver "Conversores" no README.md): grava no manifesto
do editor-imagens (o do case), não no manifesto.json deste repositório.

Cada bloco tem um gerador:
- ort-js, ort-wasm, modelo-apagar, modelo-melhorar: preparar_blocos.py;
- modelo-fundo: converter_birefnet_lite.py.
Um gerador grava os seus itens e preserva os outros: o item e o arquivo ficam como estão.

Antes de copiar qualquer bloco, cada gerador confere o teto (conferir_teto) com o tamanho EXATO do
HTML que montar.py vai gerar: a página sem blocos, montada de verdade numa pasta temporária, mais a
tag de cada bloco no mesmo formato de montar.bloco_html (gzip em base64). Sem margem estimada: um
ORT um pouco maior só reprova se o HTML montado de fato passar do teto de verificar.py.
"""
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

from caminhos import RAIZ  # checkout do editor-imagens (variável EDITOR_IMAGENS)

HTML = RAIZ / "html"

GERADOR = {
    "ort-js": "preparar_blocos.py (do editor-imagens)",
    "ort-wasm": "preparar_blocos.py (do editor-imagens)",
    "modelo-apagar": "preparar_blocos.py (do editor-imagens)",
    "modelo-melhorar": "preparar_blocos.py (do editor-imagens)",
    "modelo-fundo": "converter_birefnet_lite.py",
}


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for parte in iter(lambda: f.read(1 << 20), b""):
            h.update(parte)
    return h.hexdigest()


def mesclar(pasta: Path, novos: list[dict], preservar: set[str]) -> list[dict]:
    """Junta os itens `novos` aos itens `preservar` do manifesto atual, apaga os arquivos que
    sobraram em `pasta` e grava o manifesto. Para (SystemExit) se um item preservado faltar ou
    não bater com o arquivo: nesse caso, rode antes o gerador dele (GERADOR)."""
    caminho = pasta / "manifesto.json"
    antigos = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else []
    por_nome = {e["nome"]: e for e in antigos}
    for nome in preservar:
        e = por_nome.get(nome)
        arquivo = pasta / e["arquivo"] if e else None
        if not e or not arquivo.exists() or _sha256(arquivo) != e["sha256"]:
            raise SystemExit(f"O bloco '{nome}' falta ou não confere com o manifesto. "
                             f"Gere-o antes com ferramentas/conversores/{GERADOR.get(nome, '?')}.")
    final = {e["nome"]: e for e in novos}
    for nome in preservar:
        final[nome] = por_nome[nome]
    ordem = [e["nome"] for e in antigos if e["nome"] in final] + [n for n in final if n not in por_nome]
    entradas = [final[n] for n in ordem]
    usados = {e["arquivo"] for e in entradas} | {"manifesto.json"}
    for p in pasta.iterdir():
        if p.is_file() and p.name not in usados and p.name != ".DS_Store":
            p.unlink()
    caminho.write_text(json.dumps(entradas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entradas


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(nome, HTML / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def tamanho_tag(entrada: dict) -> int:
    """Bytes da tag <script> de um bloco no HTML, igual a montar.bloco_html (sem gzipar de novo)."""
    abre = (f'<script type="application/octet-stream" id="bloco-{entrada["nome"]}" '
            f'data-sha256="{entrada["sha256"]}" data-bytes="{entrada["bytes"]}" data-gzip="1">')
    return len(abre.encode("ascii")) + 4 * ((entrada["bytes_gzip"] + 2) // 3) + len("</script>")


def tamanho_html(entradas: list[dict], fonte: Path = HTML / "fonte") -> int:
    """Tamanho exato, em bytes, do HTML que montar.py gera com estes blocos (na ordem dada)."""
    montar = _carregar("montar")
    with tempfile.TemporaryDirectory() as tmp:
        vazio = Path(tmp) / "blocos"
        vazio.mkdir()
        (vazio / "manifesto.json").write_text("[]", encoding="utf-8")
        pagina = montar.montar(fonte, vazio, Path(tmp) / "saida", "0.0.0").stat().st_size
    tags = [tamanho_tag(e) for e in entradas]
    return pagina + sum(tags) + max(len(tags) - 1, 0)  # as tags são unidas com "\n"


def conferir_teto(entradas: list[dict], fonte: Path = HTML / "fonte") -> int:
    """Para (SystemExit) se o HTML com estes blocos passar do teto de verificar.py; devolve o tamanho."""
    teto = _carregar("verificar").TETO_BYTES
    total = tamanho_html(entradas, fonte)
    print(f"HTML montado com estes blocos: {total:,} bytes (teto {teto:,}, de verificar.py)")
    if total > teto:
        raise SystemExit(f"O HTML ficaria com {total:,} bytes, acima do teto de {teto:,} bytes (verificar.py). "
                         "Nada foi copiado nem gravado.")
    return total


def com_os_preservados(pasta: Path, novos: list[dict]) -> list[dict]:
    """Os itens que o manifesto terá depois de mesclar(pasta, novos, ...), na mesma ordem."""
    caminho = pasta / "manifesto.json"
    antigos = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else []
    por_nome = {e["nome"]: e for e in novos}
    ordem = [e["nome"] for e in antigos] + [n for n in por_nome if n not in {e["nome"] for e in antigos}]
    antigos_por_nome = {e["nome"]: e for e in antigos}
    return [por_nome.get(n, antigos_por_nome.get(n)) for n in ordem]
