#!/usr/bin/env python3
"""Gera os dois blocos do DuckDB (duckdb-js e duckdb-wasm) do mesmo jeito que o embutir_motor.py
da skill omniteca-dados-html: mesmos pacotes, mesmos hashes conferidos, mesmo comando do esbuild.

Uso:
  python3 ferramentas/embalar_duckdb.py [--cache PASTA]

Precisa de Node e npm. Instala os pacotes do npm (registry.npmjs.org) numa pasta de rascunho
dentro do cache, confere o SHA-256 do .mjs de entrada e do .wasm, e empacota a biblioteca com o
esbuild num IIFE com o global `duckdbBlocking`. Imprime o caminho, o tamanho e o sha256 dos dois
arquivos; quem confere com o manifesto é o montar_release.py.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Iguais aos de embutir_motor.py (omniteca-dados-html/scripts): não mudar sem mudar lá.
DUCKDB = {
    'pacotes': ['esbuild@0.25.0', 'apache-arrow@17.0.0', '@duckdb/duckdb-wasm@1.32.0'],
    'mjs': ('node_modules/@duckdb/duckdb-wasm/dist/duckdb-browser-blocking.mjs', 'ad9fce671ad42dce96a9b2410efc44d6d8fc54f34f44450fe4ffbd9094759bbb'),
    'wasm': ('node_modules/@duckdb/duckdb-wasm/dist/duckdb-eh.wasm', '4c221bfa59c11f24dbd750e70c90b9252eca6eec5633936e6a2ec766e55fd879'),
}
BUNDLE = 'duckdb-blocking-bundle.js'
CACHE_PADRAO = os.path.join(os.path.expanduser('~'), '.cache', 'omnitech-dependencies')


def conferir(nome, dados, esperado):
    soma = hashlib.sha256(dados).hexdigest()
    if soma != esperado:
        sys.exit(f'SHA-256 diferente do esperado para {nome}: {soma}. Nada foi gerado.')
    return dados


def embalar(cache) -> tuple[Path, Path]:
    """Devolve (bundle .js, .wasm) dentro de <cache>/duckdb-1.32.0, gerando o que faltar."""
    pasta = os.path.join(str(cache), 'duckdb-1.32.0')
    pacote = os.path.join(pasta, DUCKDB['wasm'][0])
    if not os.path.exists(pacote):
        os.makedirs(pasta, exist_ok=True)
        if not shutil.which('npm'):
            sys.exit('O DuckDB precisa de Node e npm para empacotar a biblioteca. Instale o Node 20 ou mais novo.')
        with open(os.path.join(pasta, 'package.json'), 'w') as f:
            f.write('{"name":"embutir-duckdb","private":true}')
        subprocess.run(['npm', 'install', '--no-audit', '--no-fund', '--save-exact', *DUCKDB['pacotes']],
                       cwd=pasta, check=True, stdout=subprocess.DEVNULL)
    with open(os.path.join(pasta, DUCKDB['mjs'][0]), 'rb') as f:
        conferir('duckdb-browser-blocking.mjs', f.read(), DUCKDB['mjs'][1])
    with open(pacote, 'rb') as f:
        conferir('duckdb-eh.wasm', f.read(), DUCKDB['wasm'][1])
    entrada, saida = os.path.join(pasta, 'entrada.mjs'), os.path.join(pasta, BUNDLE)
    with open(entrada, 'w') as f:
        f.write("export { createDuckDB, VoidLogger, BROWSER_RUNTIME } from './" + DUCKDB['mjs'][0] + "';\n")
    subprocess.run([os.path.join(pasta, 'node_modules', '.bin', 'esbuild'), entrada, '--bundle', '--format=iife',
                    '--global-name=duckdbBlocking', '--minify', '--target=es2020', '--legal-comments=eof',
                    '--outfile=' + saida, '--log-level=warning'], cwd=pasta, check=True)
    with open(saida, 'rb') as f:
        js = f.read()
    for perigo in (b'</script', b'<!--'):
        if perigo in js:
            sys.exit(f'A biblioteca contém {perigo!r} e quebraria o HTML. Nada foi gerado.')
    return Path(saida), Path(pacote)


def main():
    p = argparse.ArgumentParser(description='Gera os blocos duckdb-js e duckdb-wasm.')
    p.add_argument('--cache', default=CACHE_PADRAO)
    a = p.parse_args()
    for caminho in embalar(a.cache):
        dados = caminho.read_bytes()
        print(f'{caminho.name}: {len(dados):,} bytes, sha256 {hashlib.sha256(dados).hexdigest()}')


if __name__ == '__main__':
    main()
