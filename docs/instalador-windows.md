# Instalador Windows do Piixel

O instalador prepara o Piixel para **Windows 10, versão 1809 ou superior, e Windows
11 de 64 bits**. Ele inclui Python, Qt e a biblioteca de criptografia; o computador
que recebe o aplicativo não precisa instalar esses componentes separadamente.

A instalação é feita para o usuário atual, por padrão em
`%LOCALAPPDATA%\Programs\Piixel`, sem exigir uma conta administrativa. Um atalho é
criado no menu Iniciar. O atalho na área de trabalho é opcional e começa desmarcado.
O aplicativo aparece em **Configurações → Aplicativos**, para desinstalação.

## Baixar pelo GitHub Actions

1. Abra [Actions → Instalador Windows](https://github.com/IHenriqueCSN/piixel/actions/workflows/windows-installer.yml).
2. Escolha uma execução concluída com sucesso. Se precisar gerar outra versão,
   use **Run workflow** na branch `main`.
3. Em **Artifacts**, baixe **Piixel-Windows-x64**. O GitHub pode pedir login.
4. Extraia o ZIP do artifact e execute `Piixel-Setup-<versão>-x64.exe`.

O artifact é produzido pelo workflow em um computador Windows do GitHub. Ele tem
um prazo de retenção; se o download tiver expirado, execute novamente o workflow.
O ZIP do código-fonte e o ZIP do artifact são diferentes: o instalador compilado
fica no artifact da execução bem-sucedida.

## Gerar em um computador Windows

Para preparar o instalador, instale **Python 3.11 ou superior de 64 bits** e
[Inno Setup 6](https://jrsoftware.org/isdl.php). Abra PowerShell na raiz do projeto
e execute:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\scripts\build_windows_installer.ps1 -PythonExecutable ".\.venv\Scripts\python.exe"
```

O script primeiro empacota o aplicativo e depois compila o instalador. O resultado
fica em:

```text
dist\installer\Piixel-Setup-0.3.1-x64.exe
```

O número vem de `version` em `pyproject.toml`. O compilador do Inno Setup é
localizado pelo `PATH`, pelas pastas padrão do Inno Setup 6 ou pela variável
`INNO_SETUP_COMPILER`. Para uma instalação em outra pasta:

```powershell
$env:INNO_SETUP_COMPILER = "C:\Ferramentas\Inno Setup 6\ISCC.exe"
.\scripts\build_windows_installer.ps1 -PythonExecutable ".\.venv\Scripts\python.exe"
```

Se o pacote Windows já tiver sido gerado por `scripts/build.py`, é possível compilar
somente o instalador:

```powershell
.\scripts\build_windows_installer.ps1 -SkipBuild -PythonExecutable ".\.venv\Scripts\python.exe"
```

Mesmo com `-SkipBuild`, Python é usado para ler a versão do projeto. Um pacote
gerado no Linux ou macOS não pode ser convertido em um executável Windows por
esse comando; a geração precisa ocorrer em Windows ou pelo workflow.

## Publicar uma atualização

O atualizador usa **GitHub Releases**. O artifact do Actions serve para obter os
arquivos compilados, mas não é consultado pelo aplicativo porque expira e pode
exigir uma conta do GitHub.

1. Altere a versão em `pyproject.toml` e `piixelverso/__init__.py`, mantendo os
   dois valores iguais e no formato `1.2.3`.
2. Gere o instalador pelo workflow ou pelo script local. O resultado inclui o
   `.exe` e o arquivo `.exe.sha256`.
3. No GitHub, crie uma Release estável com a tag `v1.2.3`, apontando para o commit
   dessa versão. Não marque a Release como *pre-release*.
4. Anexe os dois arquivos individualmente, com os nomes exatos
   `Piixel-Setup-1.2.3-x64.exe` e `Piixel-Setup-1.2.3-x64.exe.sha256`.

O programa compara versões numericamente, exige que a tag, os nomes dos arquivos
e a versão do instalador coincidam e valida o SHA-256 antes de executar qualquer
arquivo. Uma Release incompleta ou um checksum diferente é recusado.

A versão 0.2.0 inaugura o atualizador. Quem tiver a versão 0.1.0 precisa instalar
a 0.2.0 manualmente uma única vez; as versões posteriores já poderão ser obtidas
pelo próprio Piixel.

## Atualização e dados do usuário

Na versão instalada para Windows, o Piixel procura uma Release nova em segundo
plano depois da abertura. A verificação também pode ser iniciada em
**Configurações → Verificar atualizações**. O código-fonte executado diretamente
e os pacotes de Linux e macOS não ativam esse fluxo do instalador Windows.

Ao escolher **Baixar e instalar**, o download mostra o progresso e pode ser
cancelado. O Piixel só começa a atualização depois de conferir o checksum e de
permitir que cada módulo confirme ou salve alterações pendentes. Um processo do
Windows espera o programa encerrar, executa o Inno Setup silenciosamente e reabre
o Piixel atualizado. A instalação não reinicia o Windows.

Atualizações usam a mesma identificação do aplicativo e a mesma pasta de
instalação. A pasta `_internal`, que contém as dependências distribuídas, é
substituída para evitar bibliotecas antigas. A pasta inteira do aplicativo não é
apagada indiscriminadamente.

As preferências, cores salvas, identidade e conversas do Piixelfone ficam
separadas, em `%LOCALAPPDATA%\Piixelverso\Piixel`, ou no diretório definido por
`PIIXEL_DATA_DIR`. Atualizar ou desinstalar o aplicativo preserva esses dados. Os
designs `.pii` continuam nos locais escolhidos ao salvar. O instalador também não
muda a associação de arquivos `.pii` de outros programas.

A conexão do Piixelfone continua sendo configurada dentro do aplicativo. O
instalador não contém chaves administrativas nem altera o projeto Supabase.

## Manutenção do pacote

- `scripts/build.py` gera a pasta distribuível, o ícone e os metadados de versão.
- `scripts/build_windows_installer.ps1` valida o pacote e chama `ISCC.exe`.
- `installer/windows/piixel.iss` define a instalação, atalhos e desinstalação.
- `piixelverso/update.py` consulta Releases e baixa o instalador com limite de tamanho e SHA-256.
- `piixelverso/update_ui.py` executa a verificação fora da interface e coordena a confirmação.
- `.github/workflows/windows-installer.yml` gera o pacote em Windows e publica o artifact usado para montar uma Release.

O `AppId` do arquivo `.iss` deve permanecer igual entre versões, para que a
atualização reconheça a instalação anterior. O `AppMutex` também deve acompanhar
o nome usado na inicialização do aplicativo; ele evita substituir arquivos de uma
instância em execução.

O instalador ainda não usa assinatura digital. A assinatura pode ser acrescentada
ao processo de distribuição quando houver um certificado de publicação.
