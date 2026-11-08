# Formato binário .pii — versão 1

Todos os inteiros usam little-endian. Uma célula representa uma peça. Dimensões: de 1 a 128 por eixo.

| Campo, em ordem | Tamanho | Conteúdo |
| --- | --- | --- |
| Assinatura | 4 bytes | `50 49 49 00` (`PII` e byte nulo) |
| Versão | uint8 | `1` |
| Largura | uint16 | Número de colunas |
| Altura | uint16 | Número de linhas |
| Número de cores | uint16 | N cores distintas |
| Tamanho do nome | uint16 | Bytes UTF-8, no máximo 4096 |
| Nome | tamanho declarado | Texto UTF-8 estrito |
| Paleta | N × 3 bytes | RGB; cores únicas em ordem hexadecimal na escrita |
| Pixels | largura × altura × 2 bytes | Índices uint16, por linhas da esquerda para a direita |
| Integridade | uint32 | CRC32 de todos os bytes anteriores |

Índice 0 indica célula vazia. Índices de 1 a N apontam para a paleta. Branco (`FFFFFF`) é uma cor preenchida. Arquivos truncados, com bytes extras, índices inválidos ou CRC incorreto são rejeitados. O limite absoluto de leitura é 86.033 bytes. CRC32 detecta corrupção acidental, sem constituir assinatura criptográfica.

A gravação escreve um temporário na mesma pasta, sincroniza o conteúdo e substitui o destino somente após concluir a escrita.
