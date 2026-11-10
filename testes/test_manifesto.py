"""Regras do manifesto.json da release (só biblioteca padrão)."""
import getpass
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MANIFESTO = RAIZ / "manifesto.json"

CAMPOS = ("nome", "arquivo", "versao", "origem", "licenca", "arquivo_licenca", "sha256", "bytes",
          "bytes_gzip", "comando", "entrada", "saida", "nota", "usado_por")
LICENCAS = {"MIT", "Apache-2.0", "BSD-3-Clause", "OFL-1.1"}
NOMES = {"ort-js", "ort-wasm", "modelo-fundo", "modelo-apagar", "modelo-melhorar", "sqljs-js", "sqljs-wasm",
         "duckdb-js", "duckdb-wasm", "fonte-poppins-regular", "fonte-poppins-semibold"}
URL_BASE = "https://github.com/mbsbrands/omnitech-dependencies/releases/download/v1.0.0/"


def nomes_proibidos() -> set[str]:
    """Nomes de quem roda os testes, lidos da máquina e do git (nunca escritos no repositório)."""
    nomes = set()
    try:
        nomes.add(getpass.getuser())
    except Exception:
        pass
    for chave in ("user.name", "user.email"):
        try:
            valor = subprocess.run(["git", "config", chave], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
        except OSError:
            valor = ""
        if valor:
            nomes.add(valor)
            nomes.add(valor.split("@")[0])
            nomes.update(p for p in re.split(r"[\s.@_-]+", valor.split("@")[0]) if len(p) >= 4)
    nomes.add(os.path.expanduser("~"))
    return {n for n in nomes if n and len(n) >= 4}


class TestManifesto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = MANIFESTO.read_text(encoding="utf-8")
        cls.m = json.loads(cls.texto)

    def test_campos_completos(self):
        """Todo bloco tem todos os campos, com sha256 de 64 hexadecimais e tamanhos inteiros positivos."""
        for b in self.m["blocos"]:
            with self.subTest(bloco=b.get("nome")):
                self.assertEqual(set(CAMPOS) - set(b), set(), "campos que faltam")
                self.assertRegex(b["sha256"], r"^[0-9a-f]{64}$")
                for k in ("bytes", "bytes_gzip"):
                    self.assertIsInstance(b[k], int)
                    self.assertGreater(b[k], 0)
                self.assertIsInstance(b["entrada"], dict)
                self.assertIsInstance(b["saida"], dict)
                self.assertTrue(b["usado_por"])
                self.assertLessEqual(set(b["usado_por"]), {"imagem", "dados"})
                for k in ("nome", "arquivo", "versao", "origem", "comando", "nota"):
                    self.assertTrue(isinstance(b[k], str) and b[k].strip(), k)

    def test_licenca_conhecida_com_arquivo(self):
        """A licença é uma de MIT, Apache-2.0, BSD-3-Clause ou OFL-1.1, e o arquivo dela existe em LICENSES/."""
        for b in self.m["blocos"]:
            with self.subTest(bloco=b["nome"]):
                self.assertIn(b["licenca"], LICENCAS)
                self.assertTrue(b["arquivo_licenca"].startswith("LICENSES/"))
                self.assertTrue((RAIZ / b["arquivo_licenca"]).is_file(), b["arquivo_licenca"])

    def test_licencas_embutidas_com_arquivo(self):
        """Cada licença embutida num bloco (licencas_embutidas) tem o seu arquivo em LICENSES/; o duckdb-js declara Apache-2.0 e 0BSD."""
        por_nome = {b["nome"]: b for b in self.m["blocos"]}
        self.assertEqual(por_nome["duckdb-js"].get("licencas_embutidas"), ["Apache-2.0", "0BSD"])
        for b in self.m["blocos"]:
            for licenca in b.get("licencas_embutidas", []):
                with self.subTest(bloco=b["nome"], licenca=licenca):
                    self.assertTrue((RAIZ / "LICENSES" / f"{licenca}.txt").is_file())

    def test_nomes_e_arquivos_sem_repeticao(self):
        """Os nomes de bloco não se repetem, são os 11 combinados, e cada um tem arquivo próprio."""
        nomes = [b["nome"] for b in self.m["blocos"]]
        self.assertEqual(len(nomes), len(set(nomes)))
        self.assertEqual(set(nomes), NOMES)
        arquivos = [b["arquivo"] for b in self.m["blocos"]]
        self.assertEqual(len(arquivos), len(set(arquivos)))
        for a in arquivos:
            self.assertNotIn("/", a)
            self.assertNotEqual(a, "manifesto.json")

    def test_url_base_com_a_versao(self):
        """A url_base termina em /v<versao>/ e aponta para as releases deste repositório."""
        self.assertRegex(self.m["versao"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(self.m["url_base"].endswith(f"/v{self.m['versao']}/"))
        self.assertEqual(self.m["url_base"], URL_BASE)

    def test_sem_nome_de_pessoa_nem_caminho_local(self):
        """O manifesto não contém nome de pessoa (de quem roda, lido do git e da máquina) nem caminho local."""
        for proibido in ("/" + "Users" + "/", "/home/", "C:\\", "~/"):
            self.assertNotIn(proibido, self.texto)
        baixo = self.texto.lower()
        for nome in nomes_proibidos():
            self.assertNotIn(nome.lower(), baixo)


class TestRepositorio(unittest.TestCase):
    def test_nenhum_arquivo_com_caminho_local(self):
        """Nenhum arquivo do repositório (fora de dist/ e .git/) traz caminho local de máquina (a pasta de usuários do macOS)."""
        marca = "/" + "Users" + "/"
        for p in RAIZ.rglob("*"):
            partes = p.relative_to(RAIZ).parts
            if not p.is_file() or partes[0] in (".git", "dist") or "__pycache__" in partes:
                continue
            with self.subTest(arquivo=str(p.relative_to(RAIZ))):
                self.assertNotIn(marca, p.read_text(encoding="utf-8", errors="replace"))

    def test_nenhum_arquivo_com_nome_de_quem_roda(self):
        """Fora de LICENSES/ (avisos de copyright de terceiros), nenhum arquivo traz o nome de quem roda."""
        nomes = [n.lower() for n in nomes_proibidos()]
        for p in RAIZ.rglob("*"):
            partes = p.relative_to(RAIZ).parts
            if not p.is_file() or partes[0] in (".git", "dist", "LICENSES") or "__pycache__" in partes:
                continue
            texto = p.read_text(encoding="utf-8", errors="replace").lower()
            for nome in nomes:
                with self.subTest(arquivo=str(p.relative_to(RAIZ))):
                    self.assertNotIn(nome, texto)


if __name__ == "__main__":
    unittest.main()
