# Piixel · ferramentas do Piixelverso

Piixel é um aplicativo desktop do Piixelverso, organizado em módulos. A tela inicial oferece o **Ateliê**, para criar pixel arts e contar as peças por cor, e **Configurações**, para definir o tamanho de cada peça nas imagens exportadas. A interface usa Python e Qt (PySide6), e os designs ficam em arquivos locais `.pii`.

Ao iniciar, uma pequena tela com o Pii mostra **Carregando…**, uma barra de atividade animada e **Desenvolvido por Piixelverso**. Ela abre antes de carregar o editor e fecha automaticamente assim que a janela principal aparece, sem uma espera mínima. A animação continua funcionando durante a inicialização.

![Tela de carregamento do Piixel](docs/previa-carregamento.png)

## Tela inicial

![Tela inicial do Piixel com Ateliê e Configurações](docs/previa-inicio.png)

Escolha **Abrir Ateliê** para entrar no editor. Dentro dele, use **← Início**, **Arquivo → Tela inicial** ou **Alt+Home** para voltar. Ao retornar à tela inicial, o desenho, o arquivo aberto, o histórico, as cores e a visualização ficam preservados durante a sessão. Use **Continuar no Ateliê** para retomar.

Voltar ao início não salva nem descarta o desenho. Para conservar o trabalho depois de fechar o aplicativo, salve o arquivo `.pii`. Ao fechar o Piixel, a confirmação de alterações não salvas continua funcionando, inclusive na tela inicial.

À direita, **Últimos arquivos modificados** reúne os 20 designs abertos ou salvos mais recentes pela data de modificação do arquivo. Cada item mostra o nome do arquivo, uma miniatura e o caminho. Clique no item ou pressione Enter para abri-lo no Ateliê. A lista continua disponível ao reiniciar o Piixel e é atualizada ao voltar ao início.

Se o arquivo tiver sido movido ou apagado, a miniatura e o caminho anteriores permanecem na lista, e o programa informa: **Arquivo não encontrado. Verifique se o arquivo foi movido ou apagado.** O desenho que já estiver aberto continua preservado. Para localizar um arquivo movido, entre no Ateliê e use **Arquivo → Abrir** com o novo caminho.

## Recursos do Ateliê

- Grade de 1 a 128 quadradinhos em cada dimensão.
- Lápis, balde de tinta, borracha e conta-gotas para capturar cores já usadas.
- Substituição de uma cor em todo o desenho, com prévia da quantidade de peças afetadas.
- Paleta inicial e cores personalizadas da sessão, com opção de salvar cores nomeadas para próximas sessões.
- Contagem por cor e total de peças; espaços vazios não entram na contagem.
- Desfazer, refazer e zoom da grade.
- Exibição em quadradinhos ou em rosquinhas estilo hama beads.
- Menus Arquivo, Editar e Exibir e uma única linha compacta de ferramentas, com atalhos de teclado.
- Salvamento e leitura no formato binário `.pii`, preservando dimensões, nome e cores.
- Exportação de PNG em quadradinhos ou rosquinhas, com grade opcional e medidas em milímetros.
- Configuração persistente do tamanho de cada peça, com padrão de 5 mm.

A contagem é a base para controlar materiais e calcular preços. Esta versão ainda não mantém um cadastro de estoque, custos, margens ou preços de venda.

## Identidade visual

A interface usa o kit de identidade visual v3 do Piixelverso: símbolo oficial do gatinho, logotipo em Pixelify Sans, textos em DejaVu Sans, fundo creme, azul-claro, rosa e contornos em tinta roxa. A frase de apoio é **Feito à mão, pixel por pixel.**

O símbolo e o logotipo vetoriais preservam as formas, cores e transparências do kit. As fontes de apoio e suas licenças acompanham o aplicativo, sem precisar instalá-las no sistema. A barra de menus e ferramentas permanece compacta, com 44 px de altura. As cores dos desenhos continuam sendo escolhidas livremente.

Os recursos usados e suas origens estão documentados em [piixelverso/assets/brand/README.md](piixelverso/assets/brand/README.md).

## Baixar o projeto

[Baixar o código em ZIP para Windows e Linux](https://github.com/IHenriqueCSN/piixel/archive/refs/heads/main.zip).

Extraia o ZIP e abra a pasta `piixel-main`. O pacote contém o código-fonte e os iniciadores; para usá-lo, instale Python 3.11 ou superior. A geração de um executável sem depender de Python instalado está descrita ao final deste documento.

![Módulo Ateliê do Piixel com desenho de exemplo e contagem por cor](docs/previa.png)

## Iniciar no Windows

Instale **Python 3.11 ou superior** pelo [site oficial](https://www.python.org/downloads/) e habilite a opção de adicionar Python ao `PATH`.

Com todos os arquivos do projeto na mesma pasta, abra `iniciar-windows.bat`. Na primeira execução, ele cria o ambiente `.venv` e instala os componentes Qt; essa etapa precisa de internet e ocorre antes de a tela de carregamento estar disponível. Nas próximas execuções, o aplicativo funciona localmente e exibe o carregamento logo no início.

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

Na primeira instalação pelo iniciador, a criação do ambiente e a instalação dos componentes Qt acontecem antes da tela de carregamento. Com os componentes já instalados, o iniciador evita carregar o Qt duas vezes e mostra a tela antes da inicialização da janela principal. O tempo até a primeira imagem depende da inicialização do Python, do Qt e do sistema gráfico.

## Usar o editor

Na tela inicial, entre no **Ateliê**. Em seguida:

1. Em **Arquivo → Novo**, crie um design e escolha a largura e a altura da grade.
2. Selecione uma cor na paleta ou use **Editar → Cor personalizada**.
3. Clique e arraste sobre os quadradinhos para desenhar. Use a borracha para remover peças.
4. Consulte a contagem por cor e o total de peças enquanto desenha.
5. Use **Arquivo → Salvar** para gravar o design `.pii` e **Arquivo → Abrir** para continuar depois.

O branco é uma cor e conta como peça quando aplicado. Um quadradinho vazio é transparente e não conta como peça.

Selecione **Balde de tinta** na barra ou pressione **G** e clique em uma célula para preencher a área da mesma cor ligada pelas laterais. Células que se tocam somente pela diagonal ficam separadas. O balde também preenche áreas vazias e funciona nas duas exibições de peças. Cada clique forma uma única ação de desfazer.

Para trocar uma cor em todo o desenho, use **Editar → Substituir cor…** ou **Ctrl+H**. Os dois campos são listas suspensas: **Cor original** reúne as cores usadas no desenho, com a quantidade de peças; **Nova cor** oferece toda a paleta padrão e as cores personalizadas salvas, com nome, código hexadecimal e amostra da cor. Para criar outra cor, selecione **Escolher cor personalizada…** no final da lista. Se cancelar o seletor, a escolha anterior é preservada. O diálogo mostra quantas peças serão alteradas antes de confirmar. A troca inclui regiões separadas e pode ser desfeita em uma única ação. A contagem por cor é atualizada, mantendo o total de peças. Uma nova cor de destino entra na paleta da sessão; use a opção de salvar cor se quiser guardá-la para próximas sessões.

![Substituir cor com prévia da quantidade de peças](docs/previa-substituir-cor.png)

Em **Exibir → Peças**, alterne entre **Quadradinhos** e **Rosquinhas (hama beads)**. As rosquinhas têm um furo central e continuam permitindo desenhar, apagar e capturar cores em toda a célula. Essa opção muda apenas a exibição: as cores, as quantidades e os arquivos `.pii` são os mesmos. A escolha vale durante a sessão e continua ativa ao abrir ou criar outro design.

![Visualização em rosquinhas estilo hama beads](docs/previa-rosquinhas.png)

Clique no nome para renomear o design. A lista de cores à direita também permite selecionar uma cor já usada. Abra `examples/cogumelo-do-bosque.pii` para experimentar o editor com um desenho pronto.

## Exportar como PNG

No Ateliê, use **Arquivo → Exportar como PNG…** ou **Ctrl+Shift+E**. Escolha **Quadradinhos** ou **Rosquinhas (hama beads)** e marque **Mostrar grade** se quiser incluir as linhas. A prévia mostra o resultado antes de gravar a imagem; essas escolhas valem para a exportação e preservam a visualização atual do editor.

![Escolha da aparência e prévia do PNG com medidas](docs/previa-exportar-png.png)

O PNG tem fundo branco e inclui setas de duas pontas e textos pretos: a largura fica acima do desenho e a altura à esquerda. As medidas vão da borda da peça mais à esquerda à borda da peça mais à direita e da peça mais alta à mais baixa. As margens vazias ficam fora da medida; os espaços entre as peças continuam contando para a distância entre as extremidades. Por exemplo, um desenho que ocupa **10 colunas × 8 linhas**, mesmo dentro de uma grade maior, mede **50 × 40 mm** com peças de **5 mm**. Peças brancas também entram no cálculo. Sem peças pintadas, as medidas são **0 × 0 mm**.

Clique em **Escolher onde salvar…** para selecionar a pasta e o nome do PNG. O arquivo registra também a densidade correspondente ao tamanho configurado da peça. Exportar mantém o caminho do design, o histórico e o estado de salvamento do `.pii`. Para continuar editando o trabalho em outra sessão, salve também o design pelo comando **Salvar**.

![Exemplo de PNG exportado com grade e cotas](docs/exemplo-exportado.png)

## Configurações

Abra **Configurações** na tela inicial, por **Arquivo → Configurações** no Ateliê ou com **Ctrl+,**. Em **Lado da peça**, informe o tamanho em milímetros e clique em **Salvar configurações**. O valor padrão é **5 mm**, como uma peça hama beads; são aceitos valores de **0,1 a 100 mm**, com até duas casas decimais.

![Módulo Configurações com tamanho da peça em milímetros](docs/previa-configuracoes.png)

A configuração permanece entre sessões e é usada nas próximas exportações de PNG. Ela fica nas preferências locais do usuário. Voltar ao Ateliê preserva o desenho, as cores, o histórico e o arquivo aberto.

## Cores personalizadas

Em **Editar → Cor personalizada**, informe um hexadecimal `#RRGGBB` ou use **Escolher cor**. Ao confirmar **Adicionar cor**, ela aparece na paleta e fica disponível durante a sessão, inclusive ao voltar ao início e retornar ao Ateliê.

**Salvar para próximas sessões** começa desmarcado. Marque essa opção somente se quiser guardar a cor; nesse caso, também pode preencher um nome opcional. As cores salvas são restauradas ao iniciar outra sessão, e seus nomes aparecem na cor ativa, nas dicas da paleta e na contagem de peças.

![Cor personalizada com opção de salvar e nomear](docs/previa-cor-personalizada.png)

O botão direito sobre uma cor permite salvá-la, editar sua opção salva ou **Remover das cores salvas**. Remover essa opção mantém a cor disponível na sessão atual. Salvar um desenho `.pii` preserva as cores usadas nele, mas não transforma automaticamente suas cores em favoritas da paleta.

A lista de recentes, as cores que você escolheu guardar e o tamanho configurado das peças ficam nas preferências locais do usuário, separadas dos arquivos `.pii`.

## Menus e atalhos

A barra compacta no topo reúne menus tradicionais e ícones das ferramentas mais usadas. Os menus abrem somente quando acionados, deixando mais espaço para a prancheta:

- **Arquivo**: novo design, abrir, salvar, salvar como, exportar PNG, tela inicial e Configurações.
- **Editar**: desfazer/refazer, lápis, balde de tinta, borracha, conta-gotas, substituir cor e cor personalizada.
- **Exibir**: formato das peças, grade, zoom e ajustar à janela.

Os atalhos aparecem nos menus e nas dicas ao passar o mouse. Funcionam enquanto você desenha, sem precisar abrir os menus. No Windows e Linux:

| Comando | Atalho |
| --- | --- |
| Novo design | Ctrl+N |
| Abrir `.pii` | Ctrl+O |
| Salvar | Ctrl+S |
| Salvar como | Ctrl+Shift+S |
| Exportar como PNG | Ctrl+Shift+E |
| Abrir Configurações | Ctrl+, |
| Desfazer | Ctrl+Z |
| Refazer | Ctrl+Y ou Ctrl+Shift+Z |
| Lápis | B |
| Balde de tinta | G |
| Borracha | E |
| Conta-gotas | I |
| Substituir cor em todo o desenho | Ctrl+H |
| Menu Arquivo | Alt+A |
| Menu Editar | Alt+E |
| Menu Exibir | Alt+X |
| Voltar à tela inicial | Alt+Home |

O botão direito apaga sem trocar de ferramenta. Ao editar o nome do design, as letras são digitadas normalmente. Os atalhos de edição ficam ativos apenas no Ateliê. No macOS, os comandos usam os atalhos nativos indicados nos menus.

Também é possível abrir um arquivo diretamente no Ateliê pelo terminal:

```sh
python -m piixelverso examples/cogumelo-do-bosque.pii
```

## Arquivos `.pii`

O `.pii` é um formato próprio, binário e versionado. A versão 1 armazena um cabeçalho, nome em UTF-8, paleta RGB, índices das cores de cada quadradinho e um checksum CRC32 para detectar corrupção. O aplicativo valida o conteúdo ao abrir. Renomear uma imagem PNG ou outro arquivo para `.pii` não converte seu conteúdo.

Os arquivos ficam no local escolhido ao salvar. Faça cópias dos designs que quiser preservar em outro disco ou serviço de backup de sua preferência.

A especificação binária está em [docs/formato-pii.md](docs/formato-pii.md).

## Executar testes

Dentro do ambiente virtual do projeto:

```sh
python -m unittest discover -s tests
```

`unittest` faz parte do Python. Os testes de interface usam QtTest e executam em modo offscreen. A validação cobre desenho contínuo, preenchimento por área, substituição global de cor, contagem, histórico, salvar/reabrir, PNG com cotas, configurações persistentes, falhas de gravação, arquivos inválidos e uma paleta com 16.384 cores.

## Gerar um aplicativo para distribuição

O script de build usa PyInstaller e deve ser executado **no sistema de destino**: gere a versão Windows em Windows, macOS em macOS e Linux em Linux.

No ambiente virtual do projeto:

```sh
python -m pip install -r requirements-dev.txt
python scripts/build.py
```

O resultado fica em `dist/`. O build usa o modo `onedir`: distribua a pasta inteira gerada, com o executável e suas dependências. No Windows, a pasta `Piixel` contém `Piixel.exe`; no macOS, o PyInstaller pode gerar o pacote `.app`. Quem usar esse pacote não precisa instalar Python separadamente.

Esta etapa gera o aplicativo para distribuição local. Assinatura digital, notarização e um instalador assistido poderão ser preparados depois, conforme o sistema escolhido.

## Organização

- `piixelverso/`: aplicativo, grade, contagem, modelo e leitura/gravação `.pii`.
- `piixelverso/app.py`: janela do Piixel e navegação, mantendo os módulos abertos durante a sessão.
- `piixelverso/startup.py`: entrada leve e encerramento do carregamento na abertura da janela principal.
- `piixelverso/splash.py`: tela de carregamento com animação independente da inicialização do editor.
- `piixelverso/modules.py`: cadastro dos módulos disponíveis: Ateliê e Configurações.
- `piixelverso/home.py`: tela inicial.
- `piixelverso/atelier.py`: módulo Ateliê, com desenho, histórico, contagem e salvamento.
- `piixelverso/preferences.py`: preferências locais, arquivos recentes e cores salvas por escolha do usuário.
- `piixelverso/recents.py`: lista com miniaturas, nomes e caminhos dos arquivos recentes.
- `piixelverso/colors.py`: diálogo de cores personalizadas e opção de persistência.
- `piixelverso/operations.py`: cálculo dos preenchimentos e substituições sem alterar o desenho original.
- `piixelverso/replace.py`: escolha e prévia da substituição de cor.
- `piixelverso/png_export.py`: desenho e gravação atômica do PNG com medidas.
- `piixelverso/export_dialog.py`: escolha da aparência e prévia da imagem exportada.
- `piixelverso/settings.py`: módulo de configuração do tamanho das peças.
- `tests/`: verificações do editor e do formato.
- `run_piixelverso.py`: entrada usada no empacotamento.
- `scripts/build.py`: geração do aplicativo pelo PyInstaller.
- `requirements.txt`: dependências para executar o editor.
- `requirements-dev.txt`: dependências para empacotar.
