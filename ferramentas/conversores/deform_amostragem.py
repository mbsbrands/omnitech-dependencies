"""Convolução deformável (com máscara) reescrita com grid_sample + convolução 1x1.

`torchvision.ops.deform_conv2d` vira, no ONNX, dezenas de GatherND que estouram a memória do
ONNX Runtime Web. Esta versão faz as 9 amostras bilineares com `grid_sample` e junta tudo numa
convolução 1x1: o resultado é o mesmo (diferença na ordem de 1e-6) e exporta para o opset 17.

Usada por converter_birefnet_lite.py (trocar_forward no DeformableConv2d do birefnet.py).
Teste de equivalência contra o torchvision:

    EDITOR_IMAGENS=CAMINHO/editor-imagens CAMINHO/editor-imagens/.venv/bin/python ferramentas/conversores/deform_amostragem.py

Cópia sem mudança de lógica de html/ferramentas/deform_amostragem.py do editor-imagens (ver "Conversores" no README.md).
"""
import torch
import torch.nn.functional as F


def deform_por_amostragem(x, offset, mask, weight, bias, stride, padding):
    n, c, h, w = x.shape
    o, ci, kh, kw = [int(v) for v in weight.shape]
    sh, sw = stride if isinstance(stride, tuple) else (stride, stride)
    ph, pw = padding if isinstance(padding, tuple) else (padding, padding)
    ho, wo = offset.shape[2], offset.shape[3]
    ys = torch.arange(ho, dtype=x.dtype, device=x.device) * sh - ph
    xs = torch.arange(wo, dtype=x.dtype, device=x.device) * sw - pw
    base_y = ys.view(1, ho, 1).expand(1, ho, wo)
    base_x = xs.view(1, 1, wo).expand(1, ho, wo)
    amostras = []
    for i in range(kh):
        for j in range(kw):
            k = i * kw + j
            py = base_y + i + offset[:, 2 * k]  # torchvision: deslocamento em pares (dy, dx)
            px = base_x + j + offset[:, 2 * k + 1]
            gx = 2 * px / max(w - 1, 1) - 1  # align_corners=True: -1 e 1 nos centros dos pixels dos cantos
            gy = 2 * py / max(h - 1, 1) - 1
            grade = torch.stack([gx, gy], dim=-1)
            a = F.grid_sample(x, grade, mode="bilinear", padding_mode="zeros", align_corners=True)
            amostras.append(a * mask[:, k:k + 1])
    # lote 1 (o modelo exportado tem entrada fixa [1,3,L,L]); ordem: canal, depois posição do núcleo
    pilha = torch.stack(amostras, dim=2).reshape(1, ci * kh * kw, ho, wo)
    peso = weight.reshape(o, ci * kh * kw, 1, 1)
    return F.conv2d(pilha, peso, bias)


def trocar_forward(classe):
    """Troca o forward do DeformableConv2d do birefnet.py pela versão por amostragem."""

    def forward(self, x):
        offset = self.offset_conv(x)
        modulador = 2.0 * torch.sigmoid(self.modulator_conv(x))
        return deform_por_amostragem(x, offset, modulador, self.regular_conv.weight, self.regular_conv.bias,
                                     self.stride, self.padding)

    classe.forward = forward


def testar_equivalencia() -> float:
    """Maior diferença relativa contra torchvision.ops.deform_conv2d em dois casos aleatórios."""
    from torchvision.ops import deform_conv2d

    torch.manual_seed(0)
    pior = 0.0
    for c, o, h, w in [(8, 5, 17, 23), (64, 64, 32, 32)]:
        x = torch.randn(1, c, h, w)
        off = torch.randn(1, 18, h, w) * 3
        m = torch.rand(1, 9, h, w) * 2
        wt = torch.randn(o, c, 3, 3)
        b = torch.randn(o)
        a = deform_conv2d(x, off, wt, b, padding=1, mask=m)
        d = deform_por_amostragem(x, off, m, wt, b, 1, 1)
        dif, escala = float((a - d).abs().max()), float(a.abs().max())
        print(f"  {c}->{o} canais, {h}x{w}: dif. máx {dif:.2e} (escala {escala:.1f})")
        pior = max(pior, dif / escala)
    return pior


if __name__ == "__main__":
    rel = testar_equivalencia()
    print(f"dif. relativa máx {rel:.2e}")
    assert rel < 1e-5, "a convolução por amostragem não bate com o torchvision"
    print("OK")
