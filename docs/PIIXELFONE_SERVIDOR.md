# Preparar o servidor do Piixelfone

O Piixelfone usa um projeto Supabase compartilhado pelos participantes. Cada
instalação mantém sua identidade criptográfica e seu histórico localmente. O
Supabase autentica os aparelhos e guarda uma fila de envelopes cifrados enquanto
o destinatário está desconectado. Não é necessário instalar um daemon no sistema.

## Instalação pelo administrador

1. Abra o projeto no [painel do Supabase](https://supabase.com/dashboard).
2. Em **Authentication → Sign In / Providers**, habilite **Anonymous Sign-Ins**.
   Os nomes podem variar com a versão do painel. Essas sessões recebem o papel
   `authenticated`; o papel de API `anon` não pode chamar os RPCs do Piixelfone.
3. Abra **SQL Editor**, crie uma consulta e execute **todo** o arquivo
   [`supabase/piixelfone.sql`](../supabase/piixelfone.sql). Ele instala as tabelas
   privadas, as regras de acesso e os RPCs. Uma segunda execução preserva os dados.
4. Em **Settings → API Keys**, copie a chave **Publishable** (`sb_publishable_…`)
   ou a chave legada **anon public**. Distribua essa chave e a URL do projeto aos
   participantes. Não distribua `service_role`, `sb_secret_…`, senhas ou tokens
   administrativos.
5. Em cada computador, abra **Piixelfone**, informe a chave pública na tela de
   conexão e crie a senha local de proteção da identidade. A URL já sugerida é
   `https://ukxwkgzwokzllprivknn.supabase.co`; todos precisam usar o mesmo projeto.

Ao atualizar para o Piixel 0.3.0, execute novamente o arquivo SQL completo. Essa
migração eleva o limite do envelope de 180.000 para 190.000 caracteres, necessário
para enviar um `.pii` v2 máximo com beads transparentes, sem apagar conversas ou
identidades existentes.

A chave de conexão é pública por definição. Ela identifica o projeto e permite
solicitar uma sessão; os JWTs individuais, os RPCs e a aceitação de contatos
controlam o acesso. Ela não permite ler mensagens de outros usuários. O aplicativo
nunca precisa de uma chave administrativa.

O código de seis algarismos também é um endereço público. A identidade efetiva
usa o UUID da sessão e uma chave pública imutável. Um código não é uma senha.

## Primeira conversa

1. Compartilhe seu número por um canal conhecido.
2. Procure o número da outra pessoa e envie uma solicitação de contato.
3. A outra pessoa aceita a solicitação no Piixelfone.
4. Comparem os códigos de segurança da conversa por voz ou por outro canal
   confiável antes de trocar conteúdo sensível. O primeiro contato fixa a chave
   recebida do diretório; essa comparação detecta uma substituição inicial pelo
   diretório ou por um intermediário.

Depois da aceitação, cada texto pode ter até 150 caracteres. Os anexos são arquivos
`.pii` válidos dentro do limite do formato. O cliente valida o arquivo e o conteúdo
recebido; como o servidor só recebe ciphertext, ele limita o tamanho do envelope,
não lê nem conta os caracteres do texto.

O aplicativo consulta a fila enquanto está aberto e desbloqueado, inclusive quando
outro módulo está visível. Ao fechar o Piixel, as mensagens continuam aguardando
no Supabase. Ao abri-lo e desbloquear o Piixelfone, a recepção recomeça. Não há
notificações de um processo que permaneça aberto depois de encerrar o aplicativo.

## Criptografia e armazenamento

- A implementação usa as primitivas **Box** do libsodium/PyNaCl: Curve25519 com
  XSalsa20-Poly1305 e um nonce aleatório para cada envelope. A chave privada é
  criada no aparelho e nunca é enviada ao Supabase.
- Textos, nomes dos anexos e bytes dos arquivos viajam dentro do envelope cifrado.
  O servidor vê remetente, destinatário, horários, estados e tamanho aproximado.
- As chaves dos contatos são fixadas localmente. Uma mudança de chave não deve
  ser aceita silenciosamente; confirme a identidade por outro canal.
- A identidade local é protegida por um cofre com senha, Argon2id e SecretBox.
  O histórico é cifrado no computador. A senha local não é enviada ao servidor.
- Essa versão usa chaves estáticas de identidade. Ela não implementa Double
  Ratchet nem sigilo futuro: comprometer a chave privada pode permitir decifrar
  envelopes antigos que tenham sido copiados.

O cliente grava uma mensagem recebida localmente antes de confirmar a entrega.
Após a confirmação, o servidor apaga o envelope e mantém somente os metadados e
seu resumo SHA-256, usados para estado de entrega e reenvio idempotente. Envelopes
inválidos podem ser recusados pelo destinatário; saem da fila sem receber estado
de entregue. Uma mensagem pendente não expira automaticamente.

Não é usado bucket de arquivos: o `.pii` cifrado integra o mesmo envelope da
mensagem, simplificando a autorização e a confirmação da entrega. Os históricos
locais são a cópia durável depois da confirmação. Faça cópia de segurança da pasta
de dados do aplicativo com o Piixel fechado; preserve o cofre e a senha. Perder a
senha ou a identidade privada não pode ser resolvido pelo servidor. Não exclua
usuários anônimos ativos no painel de Authentication: a sessão persistente está
ligada à identidade dessa instalação.

## Regenerar o número

O botão **Regenerar número** troca somente o endereço de seis algarismos. A chave
criptográfica, o UUID, os contatos, o histórico e as mensagens pendentes continuam
os mesmos. Contatos existentes acompanham a mudança; o número antigo deixa de
encontrar a pessoa. Números anteriores ficam reservados permanentemente, inclusive
quando uma conta é excluída, e nunca são entregues a outra pessoa.

## Limites operacionais

Os limites iniciais por identidade são:

| Operação | Limite |
| --- | --- |
| Pesquisa de números | 30 por hora |
| Novas solicitações | 10 por hora, até 20 pendentes |
| Reenvio após recusa | Aguarda 24 horas |
| Regeneração do número | 3 por dia |
| Envio de mensagens | 60 por minuto e 1.000 por dia |
| Volume de envelopes enviados | 10 MiB por dia |
| Tamanho de um envelope em base64 | 190.000 caracteres |
| Fila pendente de um destinatário | 5.000 envelopes |
| Recepção por consulta | Até 10 envelopes, mais antigos primeiro |

Os contadores usam janelas fixas pelo relógio do servidor. Repetir exatamente o
mesmo UUID de mensagem e envelope não duplica o conteúdo nem reabre uma entrega.
Preserve os limites de criação de usuários anônimos do Supabase. Os contadores por
identidade não impedem abuso por alguém que consiga criar muitas identidades;
uma distribuição ampla exige revisar controle de cadastro, proteção contra abuso
e capacidade do projeto.

O plano gratuito atualmente inclui banco de 500 MB e pode pausar projetos após
sete dias de baixa atividade. Verifique os limites atuais na
[página de preços](https://supabase.com/pricing). Retome um projeto pausado no painel.
Monitore banco, autenticações e tráfego: remover envelopes já confirmados reduz o
uso do banco, mas metadados e números reservados permanecem. O serviço só pode
entregar mensagens quando o projeto e a conexão de internet estiverem disponíveis.

## Validação da migração

Os testes em [`supabase/tests/piixelfone.sql`](../supabase/tests/piixelfone.sql)
verificam isolamento entre usuários, acesso direto negado, aceitação de contatos,
idempotência, confirmação exclusiva pelo destinatário, rejeição de envelopes e
preservação da identidade ao regenerar o número.

Para reproduzir em um **PostgreSQL 17 descartável**, execute com `ON_ERROR_STOP=1`,
nesta ordem:

1. `supabase/tests/bootstrap.sql` — simulação mínima de `auth.users`, `auth.uid()`
   e papéis; **nunca execute esse bootstrap em um projeto Supabase**.
2. `supabase/piixelfone.sql` — migração real.
3. `supabase/tests/piixelfone.sql` — testes com rollback ao terminar.

Esses testes exercitam SQL e permissões reais do PostgreSQL. A simulação não
substitui um teste de autenticação e entrega entre dois aplicativos no projeto
Supabase depois de instalar a migração e preencher a chave pública.
