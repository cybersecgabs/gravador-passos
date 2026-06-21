# Gravador de Passos

Clone do Gravador de Passos (Steps Recorder) do Windows 11, em Python.

## Funcionalidades

- Registra cliques esquerdos e direitos (com screenshot no momento do clique)
- Registra uso do teclado agrupado por campo (até Tab/Enter/clique fora do campo)
- Registra atalhos com Ctrl (ex.: `Ctrl+C (Copiar)`)
- Marca o ponto do clique na screenshot com círculo vermelho + número da etapa
- Permite adicionar comentários manuais a qualquer momento (gravando ou pausado), escolhendo **em qual etapa** o comentário será inserido
- Exporta em dois modos:
  - **HTML único** com imagens embutidas em base64 (portátil, qualidade reduzida)
  - **HTML + pasta de imagens** com PNGs em resolução total (zoom nítido)
- Opção de gerar também um **arquivo ZIP** contendo o HTML e as imagens para facilitar o compartilhamento
- GUI simples em tkinter, sempre visível durante a gravação

## Atalhos (globais)

| Atalho | Ação |
|--------|------|
| `F9`   | Iniciar / Pausar / Retomar a gravação |
| `F10`  | Parar a gravação e exportar HTML |
| `F11`  | Adicionar comentário à etapa |

> Cliques sobre a própria janela do aplicativo são ignorados automaticamente.

## Requisitos

- Windows
- Python 3.10+ (testado com 3.14)
- Dependências: `pynput`, `Pillow`

## Instalação

```powershell
pip install -r requirements.txt
```

## Uso

```powershell
python main.py
```

1. Pressione **F9** para começar a gravar.
2. Execute os passos que deseja documentar (cliques, digitação, atalhos Ctrl).
3. Pressione **F11** sempre que quiser inserir um comentário explicativo.
4. Pressione **F10** para parar; escolha o local do arquivo HTML.
5. O relatório abre no navegador (opcional).

## Estrutura

```
gravador-passos/
├── main.py              # entry point (DPI awareness + mainloop)
├── requirements.txt
├── gravador/
│   ├── models.py        # dataclass Step
│   ├── screenshot.py    # captura + marcador de clique
│   ├── recorder.py      # listeners pynput + agrupamento de teclado
│   ├── exporter.py      # geração do HTML com base64
│   └── gui.py           # janela tkinter
└── README.md
```

## Notas

- As screenshots são capturadas em resolução real (DPI-aware) e abrangem todos os monitores (virtual screen).
- No modo **HTML único**, as imagens são redimensionadas para no máximo 1280px e codificadas em JPEG para reduzir o tamanho do arquivo.
- No modo **HTML + pasta de imagens**, os PNGs originais em resolução total são copiados para uma pasta `<nome do html>_files/` ao lado do relatório. Clique na imagem para abri-la em tamanho original.
- Quando a opção de ZIP está ativa, é gerado um `<nome>.zip` com a mesma estrutura (HTML na raiz + pasta de imagens), pronto para envio.
- As screenshots temporárias são apagadas ao fechar o programa.
- Ao adicionar um comentário no meio da sequência, ele é inserido na posição escolhida sem renumerar as etapas existentes (o número de cada etapa é fixo e corresponde ao marker desenhado na sua screenshot).
