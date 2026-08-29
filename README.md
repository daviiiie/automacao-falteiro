# AUTOMAÇÃO | Falteiro_Pacheco

Esse sistema tem como finalidade a solicitação de novos produtos quando constam apenas 2 ou menos no estoque
-- se não atender a esse critério, o sistema pula para o próximo produto.

Os códigos dos produtos -- podendo ser tanto internos como código de barra -- vão no txt ean_falteiro; o sistema, 
baseado em python, lê linha por linha e faz o algoritmo de solicitar novas unidades do produto correspondente.

Quando o algoritmo encerra, sou notificado em meu celular quantos foram solicitados, quantos não foram e os que deram
erro de busca, são levados ao txt erros_falteiro. Assim debugo.
