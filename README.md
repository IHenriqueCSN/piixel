# Piixelverso · Editor de pixel art

Primeira versão de um aplicativo desktop nativo para desenhar pixel art e saber quantas peças de cada cor serão necessárias. A interface usa Python e Qt (PySide6). Os designs ficam em arquivos locais `.pii`, sem login ou servidor.

## Recursos

- Grade de 1 a 128 quadradinhos em cada dimensão.
- Lápis, borracha e conta-gotas para capturar cores já usadas.
- Paleta inicial e seleção de cores personalizadas.
- Contagem por cor e total de peças; espaços vazios não entram na contagem.
- Desfazer, refazer e zoom da grade.
- Exibição em quadradinhos ou em rosquinhas estilo hama beads.
- Salvamento e leitura no formato binário `.pii`, preservando dimensões, nome e cores.

A contagem é a base para controlar materiais e calcular preços. Esta versão ainda não mantém um cadastro de estoque, custos, margens ou preços de venda.

## Baixar o projeto

[Baixar o código em ZIP para Windows e Linux](https://github.com/IHenriqueCSN/piixel/archive/refs/heads/main.zip).

Extraia o ZIP e abra a pasta `piixel-main`. O pacote contém o código-fonte e os iniciadores; para usá-lo, instale Python 3.11 ou superior. A geração de um executável sem depender de Python instalado está descrita ao final deste documento.

![Editor Piixelverso com desenho de exemplo e contagem por cor](docs/previa.png)

## Iniciar no Windows

Instale **Python 3.11 ou superior** pelo [site oficial](https://www.python.org/downloads/) e habilite a opção de adicionar Python ao `PATH`.

Com todos os arquivos do projeto na mesma pasta, abra `iniciar-windows.bat`. Na primeira execução, ele cria o ambiente `.venv` e instala os componentes Qt; essa etapa precisa de internet. Nas próximas execuções, o aplicativo funciona localmente.

Também é possível iniciar pelo terminal, dentro da pasta do projeto:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m piixelverso
```

## Iniciar no macOS ou Linux

Com Python 3.11 ou superior instalado, abra o terminal na pasta do projeto e execute:

```sh
sh iniciar-macos-linux.sh
```

Ou prepare o ambiente manualmente:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m piixelverso
```

O aplicativo precisa de uma sessão gráfica. No Linux, o Qt depende também das bibliotecas gráficas da distribuição. Se aparecer um erro de plataforma Qt ou `xcb`, confira a biblioteca citada na mensagem e instale o pacote correspondente pelo gerenciador do sistema.

## Usar o editor

1. Crie um design e escolha a largura e a altura da grade.
2. Selecione uma cor na paleta ou adicione uma cor personalizada.
3. Clique e arraste sobre os quadradinhos para desenhar. Use a borracha para remover peças.
4. Consulte a contagem por cor e o total de peças enquanto desenha.
5. Salve o design com a extensão `.pii` e use **Abrir** para continuar depois.

O branco é uma cor e conta como peça quando aplicado. Um quadradinho vazio é transparente e não conta como peça.

No seletor acima da prancheta, alterne entre **Quadradinhos** e **Rosquinhas (hama beads)**. As rosquinhas têm um furo central e continuam permitindo desenhar, apagar e capturar cores em toda a célula. Essa opção muda apenas a exibição: as cores, as quantidades e os arquivos `.pii` são os mesmos. A escolha vale durante a sessão e continua ativa ao abrir ou criar outro design.

![Visualização em rosquinhas estilo hama beads](docs/previa-rosquinhas.png)

Clique no nome para renomear o design. A lista de cores à direita também permite selecionar uma cor já usada. Abra `examples/cogumelo-do-bosque.pii` para experimentar o editor com um desenho pronto.

Atalhos: **B** lápis, **E** borracha, **I** conta-gotas, **Ctrl+Z** desfazer, **Ctrl+Y** ou **Ctrl+Shift+Z** refazer, **Ctrl+N** novo, **Ctrl+O** abrir, **Ctrl+S** salvar e **Ctrl+Shift+S** salvar como. O botão direito apaga sem trocar de ferramenta.

## Arquivos `.pii`

O `.pii` é um formato próprio, binário e versionado. A versão 1 armazena um cabeçalho, nome em UTF-8, paleta RGB, índices das cores de cada quadradinho e um checksum CRC32 para detectar corrupção. O aplicativo valida o conteúdo ao abrir. Renomear uma imagem PNG ou outro arquivo para `.pii` não converte seu conteúdo.

Os arquivos ficam no local escolhido ao salvar. Faça cópias dos designs que quiser preservar em outro disco ou serviço de backup de sua preferência.

A especificação binária está em [docs/formato-pii.md](docs/formato-pii.md).

## Executar testes

Dentro do ambiente virtual do projeto:

```sh
python -m unittest discover -s tests
```

`unittest` faz parte do Python. Os testes de interface usam QtTest e executam em modo offscreen. A validação da versão inicial cobre desenho contínuo, contagem, histórico, salvar/reabrir, falhas de gravação, arquivos inválidos e uma paleta com 16.384 cores.

## Gerar um aplicativo para distribuição

O script de build usa PyInstaller e deve ser executado **no sistema de destino**: gere a versão Windows em Windows, macOS em macOS e Linux em Linux.

No ambiente virtual do projeto:

```sh
python -m pip install -r requirements-dev.txt
python scripts/build.py
```

O resultado fica em `dist/`. O build usa o modo `onedir`: distribua a pasta inteira gerada, com o executável e suas dependências. No Windows, ela contém `Piixelverso.exe`; no macOS, o PyInstaller pode gerar o pacote `.app`. Quem usar esse pacote não precisa instalar Python separadamente.

Esta etapa gera o aplicativo para distribuição local. Assinatura digital, notarização e um instalador assistido poderão ser preparados depois, conforme o sistema escolhido.

## Organização

- `piixelverso/`: aplicativo, grade, contagem, modelo e leitura/gravação `.pii`.
- `tests/`: verificações do editor e do formato.
- `run_piixelverso.py`: entrada usada no empacotamento.
- `scripts/build.py`: geração do aplicativo pelo PyInstaller.
- `requirements.txt`: dependências para executar o editor.
- `requirements-dev.txt`: dependências para empacotar.
