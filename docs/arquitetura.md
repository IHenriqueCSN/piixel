# Arquitetura do Piixel

O Piixel é uma aplicação Qt organizada por responsabilidade. O ponto de entrada continua em `startup.py`; a tela inicial, os módulos, os comandos e os formatos de arquivo mantêm seus fluxos existentes.

```mermaid
flowchart TD
    Bootstrap["startup / splash"] --> Shell["app: janela e navegação"]
    Shell --> Registry["modules: registro e factories"]
    Registry --> Contract["module_api: ModulePage"]
    Contract --> Atelier["atelier: coordenação do editor"]
    Contract --> Settings["settings: configurações"]
    Shell --> UpdateUI["update_ui: coordenação em segundo plano"]
    UpdateUI --> Update["update: Releases e SHA-256"]
    Update --> GitHub["GitHub Releases"]
    Contract --> Phone["piixelfone/page: interface e worker"]
    Phone --> PhoneService["piixelfone/service: casos de uso"]
    PhoneService --> PhoneStore["store / crypto: histórico e cofre cifrados"]
    PhoneService --> Transport["transport: HTTPS e autenticação"]
    Transport --> Supabase["Supabase: RPCs e fila cifrada"]
    Atelier --> View["editor/view: widgets e sinais"]
    Atelier --> Actions["editor/actions: ações e atalhos"]
    Atelier --> Session["editor/session: documento e histórico"]
    Session --> History["editor/history: comandos reversíveis"]
    History --> Model["model: grade de peças"]
    View --> Canvas["canvas: gestos e prévias"]
    Atelier --> Files["format / png_export: arquivos"]
```

## Documento e regras de desenho

- `model.py` representa a grade, as cores e o nome do design.
- `operations.py`, `shapes.py` e `resize.py` calculam alterações sem depender de widgets Qt.
- `editor/session.py` mantém o documento aberto, seu caminho e o `QUndoStack`. Um salvamento só atualiza o caminho e a marca de documento salvo depois que a gravação termina com sucesso.
- `editor/history.py` aplica pixels, nomes e dimensões à sessão. Os comandos não conhecem janelas, campos de texto ou a construção da interface.

A identidade do documento é preservada durante redimensionamentos. Isso permite desfazer uma alteração de dimensões e depois desfazer comandos de pintura anteriores sem trocar seus índices de referência. Abrir outro arquivo substitui o documento e limpa o histórico, como antes.

## Apresentação e coordenação

- `editor/view.py` constrói os widgets e emite intenções como selecionar uma cor ou confirmar a edição do nome. Recebe as ações compartilhadas para os menus e a barra.
- `editor/actions.py` centraliza textos, ícones, atalhos e grupos exclusivos de ferramentas. Menus e botões usam as mesmas instâncias de `QAction`.
- `editor/palette.py` contém a paleta inicial, sem dependências de interface.
- `editor/recent_colors.py` apresenta nove amostras numeradas. A ordem das cores recentes pertence ao coordenador do Ateliê; selecionar um atalho mantém essa ordem, sem alterar o documento ou as preferências salvas.
- `editor/new_design_dialog.py` contém o diálogo de novo design.
- `ui/icons.py` e `ui/widgets.py` fornecem recursos visuais compartilhados, sem depender do Ateliê.
- `atelier.py` conecta a view, a sessão e os fluxos de interação, como diálogos de abrir, salvar, exportar e escolher cores. Ele mantém os acessos existentes a `design`, `file_path`, `history` e aos widgets usados pela interface e pelos testes.

Os construtores de comandos anteriormente importados de `atelier.py` continuam disponíveis como adaptadores para a sessão. O código novo usa os comandos de `editor/history.py` diretamente; esses comandos não dependem do coordenador ou dos widgets.

O canvas mantém o estado transitório dos gestos. A pintura livre continua atualizando os pixels durante o arraste; as formas geométricas continuam usando uma prévia separada até a confirmação. Ao concluir um gesto, o canvas informa os valores anteriores e posteriores, e a sessão registra o comando reversível. As notificações da sessão atualizam a apresentação.

## Módulos

`modules.py` reúne os metadados e as factories. As implementações são importadas quando o módulo é solicitado. A janela usa `ModulePage`, definido em `module_api.py`, em vez de acessar o canvas ou o histórico de um módulo concreto.

O contrato contém:

- `set_active`, `prepare_navigation` e `focus_default` para ativação e navegação.
- `home_state` para informar opcionalmente o nome e as alterações pendentes exibidos no início.
- `attach_navigation` para receber as ações globais de início e configurações.
- `attach_updater` para a página de Configurações receber o serviço da aplicação.
- `confirm_close` para autorizar o fechamento, inclusive quando o módulo está oculto.
- `shutdown` para encerrar o trabalho em segundo plano depois que todos os módulos aceitarem o fechamento.
- `load_path` e o sinal `document_accessed` para módulos que abrem documentos.

Para acrescentar um módulo, implemente esse contrato e registre sua factory junto aos metadados. A rota de arquivos `.pii` continua direcionada ao Ateliê.

## Indicação de carregamento

`loading.py` coordena as aberturas de páginas e a atualização dos recentes. Um overlay é pintado antes do trabalho síncrono; a mesma pequena superfície é animada por um processo auxiliar durante imports e construção dos widgets. Os widgets da aplicação continuam na thread gráfica. O controlador encerra a indicação após a primeira pintura do destino, ou imediatamente em falhas, fechamento e abertura de um diálogo modal. Operações aninhadas compartilham a indicação e callbacks antigos não encerram um carregamento mais recente.

`ui/loading.py` contém a rodinha, o overlay e o card compartilhado. `startup.py` despacha o modo auxiliar tanto pelo código-fonte quanto pelo executável empacotado; `splash.py` compartilha o monitoramento do pipe. Fechar o pipe encerra o auxiliar, inclusive se o processo principal falhar; a limpeza ocorre sem esperar na thread gráfica. O popup não solicita foco nem usa a opção global de ficar acima de todas as janelas. Em plataformas sem superfície gráfica nativa, a indicação local continua disponível.

No Piixelfone, as ações explícitas já executam em uma thread de trabalho; o overlay usa o próprio event loop da interface. A página é reabilitada e a animação para tanto em sucesso quanto em erro. A sincronização periódica não abre overlay. Os diálogos de arquivo são exibidos antes do início da ação, e a navegação para outros módulos continua disponível.

## Persistência e compatibilidade

O Piixelfone fica isolado em `piixelfone/`. `page.py` constrói a interface e envia operações para uma única fila em uma thread de trabalho; um timer solicita sincronização sem sobrepor operações. Navegar para outro módulo mantém a sessão conectada. O encerramento interrompe novas tarefas e não espera por chamadas de rede na thread gráfica.

`service.py` coordena identidade, contatos, criptografia, envio, recebimento e confirmação de entrega, sem depender do Qt. `transport.py` usa HTTPS, bloqueia redirecionamentos, limita tamanhos e apresenta erros sem incluir tokens nem respostas do servidor. `config.py` aceita apenas a chave pública; credenciais administrativas são recusadas.

`crypto.py` usa Box da libsodium para os envelopes e SecretBox para o cofre e os registros locais. Argon2id deriva a chave do cofre a partir da senha local. `store.py` mantém contatos e registros cifrados no SQLite, com conexões por operação e proteção contra troca de chave. Cada envelope vincula criptograficamente o UUID da mensagem, remetente e destinatário. Retransmissões preservam o mesmo UUID e ciphertext; o destinatário grava antes de confirmar ao servidor.

`supabase/piixelfone.sql` mantém tabelas em schema privado, com RLS e sem acesso direto por clientes. RPCs autorizam cada operação pelo JWT autenticado. O conteúdo cifrado permanece até o destinatário confirmar ou recusar; depois disso fica apenas o estado e o hash para preservar a idempotência. Números antigos ficam reservados permanentemente. O [guia de instalação](PIIXELFONE_SERVIDOR.md) descreve a implantação e as limitações criptográficas.

`format.py` continua responsável pelo `.pii` versionado e pela gravação atômica.
A versão 1 usa paleta RGB; a versão 2 acrescenta a bead transparente com uma
entrada ARGB explícita. `None`, branco e transparente permanecem estados distintos
no modelo. Designs sem transparência continuam sendo gravados como v1. O pequeno
`materials.py` traduz o material especial para nome, preenchimento claro e contorno
visível, sem espalhar um RGB fictício pelas regras do documento.

`preferences.py` continua guardando arquivos recentes, cores salvas e tamanho das
peças. A transparência é parte da paleta padrão e não entra nas cores personalizadas.
`png_export.py` inclui a peça transparente nos limites e medidas e a representa
visualmente no PNG, em vez de produzir um pixel invisível.

`update.py` trata a versão, o manifesto de GitHub Releases, os limites de download e
a validação SHA-256 sem depender do Qt. `update_ui.py` executa rede e disco fora da
thread gráfica, apresenta o progresso e só entrega o instalador ao sistema depois
que todos os módulos autorizam o fechamento. `startup.py` inicia um PowerShell do
próprio Windows, que espera o processo principal liberar o `AppMutex`; o Inno Setup
então substitui a aplicação e reabre o executável instalado. Esse fluxo fica
desativado no código-fonte e fora do pacote Windows congelado.

As chaves das preferências, limites das pranchetas, menus e atalhos permanecem
compatíveis. Os testes verificam as duas versões do `.pii`, a separação entre vazio,
branco e transparente e o uso do material em edição, contagem e exportação.

## Comparação antes/depois

No mesmo ambiente, versão do Qt e sistema gráfico, capture uma referência antes da alteração:

```sh
python scripts/capture_behavior.py /tmp/piixel-before
```

Depois da alteração, compare em outra pasta:

```sh
python scripts/capture_behavior.py /tmp/piixel-after --compare /tmp/piixel-before
```

O script usa preferências temporárias e compara 17 artefatos: telas em dois tamanhos, diálogos, exportações PNG, design `.pii`, preferências e definições das ações. A pasta de dados normal do usuário não é usada por essa verificação.
