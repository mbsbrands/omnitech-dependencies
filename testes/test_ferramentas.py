"""Regras das ferramentas de release (montar_release.py, verificar_release.py, embalar_duckdb.py)."""
import gzip
import hashlib
import http.client
import io
import tarfile
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "ferramentas"))

import embalar_duckdb  # noqa: E402
import montar_release  # noqa: E402
import verificar_release  # noqa: E402


def bloco(nome: str, dados: bytes) -> dict:
    return {"nome": nome, "arquivo": f"{nome}.bin", "versao": "1", "origem": "teste", "licenca": "MIT",
            "arquivo_licenca": "LICENSES/MIT.txt", "sha256": hashlib.sha256(dados).hexdigest(),
            "bytes": len(dados), "bytes_gzip": len(gzip.compress(dados, compresslevel=9, mtime=0)),
            "comando": "teste", "entrada": {}, "saida": {}, "nota": "teste", "usado_por": ["imagem"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        self.origem = self.pasta / "origem"
        self.origem.mkdir()
        self.dados = {"a": b"primeiro bloco", "b": b"segundo bloco" * 100, "c": b"\x00\x01\x02terceiro"}
        self.fontes = {}
        for nome, dados in self.dados.items():
            (self.origem / f"{nome}.bin").write_bytes(dados)
            self.fontes[nome] = self.origem / f"{nome}.bin"
        self.manifesto = {"versao": "9.9.9", "url_base": "https://exemplo.invalid/v9.9.9/",
                          "blocos": [bloco(n, d) for n, d in self.dados.items()]}
        self.caminho_manifesto = self.pasta / "manifesto.json"
        self.caminho_manifesto.write_text(json.dumps(self.manifesto), encoding="utf-8")
        self.destino = self.pasta / "dist" / "v9.9.9"

    def tearDown(self):
        self.tmp.cleanup()

    def montar(self):
        with redirect_stdout(io.StringIO()):
            return montar_release.montar(self.manifesto, self.fontes, self.destino, self.caminho_manifesto)


class TestMontar(Base):
    def test_pasta_completa_passa(self):
        """Com todos os blocos certos, a release sai completa (blocos e manifesto) e o verificador a aprova."""
        self.montar()
        nomes = sorted(p.name for p in self.destino.iterdir())
        self.assertEqual(nomes, ["a.bin", "b.bin", "c.bin", "manifesto.json"])
        self.assertEqual(verificar_release.verificar_pasta(self.manifesto, self.destino), [])

    def test_hash_errado_faz_parar(self):
        """Um bloco com sha256 diferente do manifesto faz o montador parar, dizendo qual, sem deixar dist/."""
        self.fontes["b"].write_bytes(b"segundo bloco" * 99 + b"segundo blocX")  # mesmo tamanho, outro hash
        with self.assertRaises(SystemExit) as erro:
            self.montar()
        self.assertIn("'b'", str(erro.exception.code))
        self.assertIn("sha256", str(erro.exception.code))
        self.assertFalse(self.destino.exists())
        self.assertEqual([p.name for p in self.destino.parent.glob("*")] if self.destino.parent.exists() else [], [])

    def test_para_no_primeiro_hash_diferente(self):
        """Com dois blocos errados, o montador para no primeiro, na ordem do manifesto."""
        self.fontes["a"].write_bytes(b"outro")
        self.fontes["c"].write_bytes(b"outro tambem")
        with self.assertRaises(SystemExit) as erro:
            self.montar()
        self.assertIn("'a'", str(erro.exception.code))
        self.assertNotIn("'c'", str(erro.exception.code))

    def test_tamanho_errado_faz_parar(self):
        """Um bloco com tamanho diferente do manifesto faz o montador parar."""
        self.fontes["c"].write_bytes(self.dados["c"] + b"!")
        with self.assertRaises(SystemExit):
            self.montar()
        self.assertFalse(self.destino.exists())

    def test_bloco_ausente_faz_parar(self):
        """Um bloco sem arquivo de origem faz o montador parar."""
        self.fontes["b"].unlink()
        with self.assertRaises(SystemExit) as erro:
            self.montar()
        self.assertIn("'b'", str(erro.exception.code))

    def test_falha_nao_estraga_release_anterior(self):
        """Se a montagem falha, uma dist/ montada antes fica como estava."""
        self.montar()
        self.fontes["a"].write_bytes(b"outro")
        with self.assertRaises(SystemExit):
            self.montar()
        self.assertEqual(verificar_release.verificar_pasta(self.manifesto, self.destino), [])

    def test_falha_nao_apaga_pasta_dist_que_ja_existia(self):
        """Se a montagem falha, a pasta --dist que já existia antes (vazia ou não) continua lá."""
        self.destino.parent.mkdir(parents=True)
        self.fontes["a"].write_bytes(b"outro")
        with self.assertRaises(SystemExit):
            self.montar()
        self.assertTrue(self.destino.parent.is_dir())
        (self.destino.parent / "outra.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.montar()
        self.assertTrue((self.destino.parent / "outra.txt").is_file())

    def test_tgz_sem_o_arquivo_para_com_mensagem(self):
        """Se o pacote do sql.js no cache não tem o arquivo esperado, o montador para dizendo qual arquivo falta."""
        cache = self.pasta / "cache"
        cache.mkdir()
        with tarfile.open(cache / "sql.js-1.14.2.tgz", "w:gz") as tar:
            info = tarfile.TarInfo("package/README.md")
            info.size = 2
            tar.addfile(info, io.BytesIO(b"oi"))
        with self.assertRaises(SystemExit) as erro:
            montar_release.baixar_sqljs(cache)
        self.assertIn("package/dist/sql-wasm-browser.js", str(erro.exception.code))
        self.assertIn("não", str(erro.exception.code))

    def test_comando_gh_so_impresso(self):
        """O comando gh release create sai com a tag da versão, o repositório e todos os arquivos da pasta."""
        cmd = montar_release.comando_gh(self.manifesto, self.destino)
        self.assertTrue(cmd.startswith("gh release create v9.9.9 "))
        self.assertIn("--repo mbsbrands/omnitech-dependencies", cmd)
        for nome in ("a.bin", "b.bin", "c.bin", "manifesto.json"):
            self.assertIn(nome, cmd)
        self.assertNotIn("subprocess", (RAIZ / "ferramentas" / "montar_release.py").read_text(encoding="utf-8")
                         .split("def comando_gh")[1].split("\ndef ")[0])


class TestVerificar(Base):
    def setUp(self):
        super().setUp()
        self.montar()

    def test_pasta_com_bloco_alterado_reprova(self):
        """Na pasta local, um bloco alterado ou ausente é reprovado pelo nome."""
        (self.destino / "a.bin").write_bytes(b"x" * len(self.dados["a"]))
        (self.destino / "c.bin").unlink()
        erros = verificar_release.verificar_pasta(self.manifesto, self.destino)
        self.assertEqual(len(erros), 2)
        self.assertTrue(any(e.startswith("a (") and "sha256" in e for e in erros))
        self.assertTrue(any(e.startswith("c (") for e in erros))

    def test_url_completa_passa(self):
        """Pela URL (aqui file://, sem rede), a release completa passa."""
        url = self.destino.as_uri() + "/"
        self.assertEqual(verificar_release.verificar_url(self.manifesto, url), [])

    def test_url_com_bloco_alterado_ou_fora_do_ar_reprova(self):
        """Pela URL, um bloco com outro hash ou que não baixa é reprovado."""
        (self.destino / "b.bin").write_bytes(b"y")
        (self.destino / "c.bin").unlink()
        erros = verificar_release.verificar_url(self.manifesto, self.destino.as_uri() + "/")
        self.assertEqual(len(erros), 2)

    def test_url_com_falha_http_lista_o_bloco(self):
        """Uma falha do protocolo HTTP (conexão cortada no meio) vira bloco reprovado, sem parar a verificação."""
        def falha(*_a, **_k):
            raise http.client.IncompleteRead(b"meio")
        with mock.patch.object(verificar_release.urllib.request, "urlopen", falha):
            erros = verificar_release.verificar_url(self.manifesto, "https://exemplo.invalid/v9.9.9/")
        self.assertEqual(len(erros), 3)
        self.assertTrue(all("não baixou" in e for e in erros))

    def test_manifesto_diferente_na_pasta_reprova(self):
        """Se o manifesto.json da pasta não é igual ao do repositório, a verificação reprova."""
        (self.destino / "manifesto.json").write_text("{}", encoding="utf-8")
        erros = verificar_release.verificar_pasta(self.manifesto, self.destino, self.caminho_manifesto)
        self.assertTrue(any("manifesto" in e for e in erros))


class TestHashesFixados(unittest.TestCase):
    def setUp(self):
        self.m = {b["nome"]: b for b in json.loads((RAIZ / "manifesto.json").read_text(encoding="utf-8"))["blocos"]}

    def test_sqljs_igual_ao_manifesto(self):
        """Os sha256 do SQL.js fixados no montador são os do manifesto (os mesmos do embutir_motor.py)."""
        self.assertEqual(montar_release.SQLJS["js"][1], self.m["sqljs-js"]["sha256"])
        self.assertEqual(montar_release.SQLJS["wasm"][1], self.m["sqljs-wasm"]["sha256"])
        self.assertEqual(montar_release.SQLJS["js"][1], "35e39a73b2e0bc1c2202a4cadb23bcf7a3a77071a39c270f014402968785b95f")
        self.assertEqual(montar_release.SQLJS["wasm"][1], "38c14f6e379210bc942bdc4ebca44e7bfdb4318ecc1c72ca666a28fdce96670a")

    def test_duckdb_igual_ao_embutir_motor(self):
        """O embalar_duckdb.py usa os mesmos pacotes e hashes do embutir_motor.py, e o wasm é o do manifesto."""
        d = embalar_duckdb.DUCKDB
        self.assertEqual(d["pacotes"], ["esbuild@0.25.0", "apache-arrow@17.0.0", "@duckdb/duckdb-wasm@1.32.0"])
        self.assertEqual(d["mjs"][1], "ad9fce671ad42dce96a9b2410efc44d6d8fc54f34f44450fe4ffbd9094759bbb")
        self.assertEqual(d["wasm"][1], "4c221bfa59c11f24dbd750e70c90b9252eca6eec5633936e6a2ec766e55fd879")
        self.assertEqual(d["wasm"][1], self.m["duckdb-wasm"]["sha256"])

    def test_conversores_com_os_hashes_de_origem(self):
        """Os conversores copiados do case mantêm os hashes de origem fixados que o manifesto cita."""
        conv = RAIZ / "ferramentas" / "conversores"
        birefnet = (conv / "converter_birefnet_lite.py").read_text(encoding="utf-8")
        codigo = (conv / "codigo_birefnet.py").read_text(encoding="utf-8")
        esrgan = (conv / "exportar_esrgan.py").read_text(encoding="utf-8")
        fundo, melhorar = self.m["modelo-fundo"], self.m["modelo-melhorar"]
        self.assertIn("4417d89795250e698c3cb0ae8df15743810065f646f48a694fdfa7ca052d0815", birefnet)
        self.assertIn("aa62cd87eafb9cc43056d08ef3615a14628b831d", birefnet)
        self.assertIn("4417d89795250e698c3cb0ae8df15743810065f646f48a694fdfa7ca052d0815", fundo["origem"])
        for sha in ("208771ae626f653d64128fbf2d6ac9f8e645c5cc5e286258a73ec3322bbfe5ef",
                    "e7b8c2a74f6cea6a59553d517f71d47f2c1d90e670a13416af17c25fe2f3dc52",
                    "c97ea21569daf66b205491a4635147dd3bc42c7c168b89d7d75b53f67ef548ae",
                    "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"):
            self.assertIn(sha, codigo)
        self.assertIn("8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292", esrgan)
        self.assertIn("8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292", melhorar["origem"])
        self.assertIn(melhorar["sha256"], esrgan)


if __name__ == "__main__":
    unittest.main()
