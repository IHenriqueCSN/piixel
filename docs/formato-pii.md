# Formato binário `.pii`

Todos os inteiros usam *little-endian*. Uma célula representa uma peça. As
dimensões aceitas vão de 1 a 128 por eixo.

| Campo, em ordem | Tamanho | Conteúdo |
| --- | --- | --- |
| Assinatura | 4 bytes | `50 49 49 00` (`PII` e byte nulo) |
| Versão | uint8 | `1` ou `2` |
| Largura | uint16 | Número de colunas |
| Altura | uint16 | Número de linhas |
| Número de materiais | uint16 | N entradas distintas na paleta |
| Tamanho do nome | uint16 | Bytes UTF-8, no máximo 4096 |
| Nome | tamanho declarado | Texto UTF-8 estrito |
| Paleta | depende da versão | Materiais únicos em ordem hexadecimal na escrita |
| Pixels | largura × altura × 2 bytes | Índices uint16, por linhas da esquerda para a direita |
| Integridade | uint32 | CRC32 de todos os bytes anteriores |

O índice 0 representa uma célula vazia. Índices de 1 a N apontam para uma peça
da paleta. Portanto, vazio, branco e transparente são três estados diferentes.

Na **versão 1**, cada item da paleta ocupa três bytes RGB. Ela continua sendo
usada ao salvar designs que contenham apenas cores opacas, mantendo
compatibilidade com os arquivos anteriores.

Na **versão 2**, cada item ocupa quatro bytes ARGB. `FF RRGGBB` representa uma
cor opaca e `00 FFFFFF` representa especificamente uma bead transparente. Outros
valores de alfa são recusados. O Piixel usa essa versão somente quando o design
contém pelo menos uma peça transparente.

Arquivos truncados, com bytes extras, materiais duplicados, índices inválidos,
alfas desconhecidos ou CRC incorreto são rejeitados. O limite absoluto de leitura
é 102.417 bytes. O CRC32 detecta corrupção acidental e não constitui uma
assinatura criptográfica.

A gravação escreve um temporário na mesma pasta, sincroniza o conteúdo e
substitui o destino somente depois de concluir a escrita.
