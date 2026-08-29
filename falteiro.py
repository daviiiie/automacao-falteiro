"""
Script de automacao - Falteiro (Balcao 2.0)
--------------------------------------------
Le uma lista de EANs, busca cada um no sistema, verifica o estoque
e envia ao Falteiro os produtos com estoque baixo (<=2).
"""

import os
import re
import time
import requests
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

# ---------------------------------------------------------------------------
# CONFIGURACAO
# ---------------------------------------------------------------------------


PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
# CAMINHO_NAVEGADORES = os.path.join(PASTA_BASE, "playwright_dependencies")
# os.environ["PLAYWRIGHT_BROWSERS_PATH"] = CAMINHO_NAVEGADORES

URL_SISTEMA = "https://balcao2-front.dpsp.io/product/dipirona"
ARQUIVO_EANS = os.path.join(PASTA_BASE, "ean_falteiro.txt")
ARQUIVO_ERROS = os.path.join(PASTA_BASE, "erros_falteiro.txt")

ESTOQUE_MINIMO = 2          # se estoque <= isso, manda pro falteiro
QUANTIDADE_SOLICITADA = 2   # quantidade pedida no falteiro

NTFY_TOPIC = "SISTEMA_FALTEIRO"   
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

TIMEOUT_BUSCA_MS = 6000  # tempo maximo esperando resultado da busca


# ---------------------------------------------------------------------------
# NOTIFICACOES (ntfy) -> Mi Band
# ---------------------------------------------------------------------------

def notificar(mensagem: str, titulo: str = "Falteiro") -> None:
    """Envia notificacao push via ntfy. Nao trava o script se falhar."""
    print(f"[NTFY] Enviando notificacao: {titulo} -> {mensagem[:50]}...")
    try:
        requests.post(
            NTFY_URL,
            data=mensagem.encode("utf-8"),
            headers={"Title": titulo},
            timeout=5,
        )
        print("[NTFY] Notificacao enviada com sucesso.")
    except requests.RequestException as erro:
        print(f"[aviso] Falha ao notificar via ntfy: {erro}")


# ---------------------------------------------------------------------------
# LEITURA DA LISTA DE EANS
# ---------------------------------------------------------------------------

def carregar_eans(caminho: str) -> list[str]:
    print(f"[SETUP] Carregando lista de EANs de: {caminho}")
    with open(caminho, "r", encoding="utf-8") as arquivo:
        eans = [linha.strip() for linha in arquivo if linha.strip()]
    print(f"[SETUP] {len(eans)} EAN(s) carregado(s).")
    return eans


# ---------------------------------------------------------------------------
# LOGIN MANUAL
# ---------------------------------------------------------------------------

def aguardar_login_manual(page: Page) -> None:
    """Abre o sistema e pausa ate voce logar manualmente."""
    print(f"[LOGIN] Abrindo {URL_SISTEMA}...")
    page.goto(URL_SISTEMA)
    input(">> Faca login manualmente na janela do navegador. Depois, pressione ENTER aqui para continuar...")
    print("[LOGIN] Login confirmado, iniciando processamento.")


# ---------------------------------------------------------------------------
# BUSCA DE UM PRODUTO
# ---------------------------------------------------------------------------

def buscar_produto(page: Page, ean: str) -> str:
    print(f"[BUSCA] Buscando EAN {ean}...")
    campo_busca = page.locator("#productDetailsSearchbar")
    campo_busca.fill(ean)
    campo_busca.press("Enter")

    erro_locator = page.locator('[data-testid="productDetailsSearchbar-error"]')

    try:
        erro_locator.wait_for(state="visible", timeout=TIMEOUT_BUSCA_MS)
        print(f"[BUSCA] EAN {ean} -> produto NAO encontrado.")
        return "Produto nao encontrado"

    except PlaywrightTimeoutError:
        print(f"[BUSCA] EAN {ean} -> produto encontrado (erro nao apareceu).")
        return "produto encontrado"

    # OBS: esses returns repassam ao restante do codigo o que aconteceu ao buscar um produto


# ---------------------------------------------------------------------------
# VERIFICAR ESTOQUE  #CHECK
# ---------------------------------------------------------------------------

def verificar_estoque(page: Page) -> int:
    """Le o estoque visivel na tela de detalhes do produto."""
    padrao = re.compile(r"Estoque\s*:\s*(\d+)", re.IGNORECASE)
    
    loc = page.get_by_text(padrao)
    texto = loc.first.text_content(timeout=2000) or ""
    
    match = padrao.search(texto)
    if not match:
        raise ValueError("Nao foi possivel localizar o estoque na tela.")
    
    return int(match.group(1))

# ---------------------------------------------------------------------------
# ENVIAR AO FALTEIRO
# ---------------------------------------------------------------------------

def enviar_ao_falteiro(page: Page, quantidade: int) -> None:
    """Abre o modal Falteiro, preenche a quantidade e confirma."""
    print("[FALTEIRO] Funcao de envio ao falteiro rodando...")
    page.locator("#productDetailsOpenMissingProducts").click()

    campo_quantidade = page.locator("#quantity")
    campo_quantidade.fill(str(quantidade))

    page.get_by_role("button", name="Lançar").click()
    print("[FALTEIRO] Envio concluido com sucesso!")


# ---------------------------------------------------------------------------
# FLUXO PRINCIPAL
# ---------------------------------------------------------------------------

def processar_ean(page: Page, ean: str, eans_com_erro: list[str]) -> str:
    """
    Processa um EAN e retorna a categoria final:
    'falteiro' | 'ok' | 'erro'
    """
    print(f"\n[PROCESSAR] Iniciando EAN {ean}...")
    resultado_busca = buscar_produto(page, ean)

    if resultado_busca == "Produto nao encontrado":
        print(f"[ERRO] EAN {ean} - produto nao encontrado")
        eans_com_erro.append(ean)
        return "erro"

    if resultado_busca == "erro_inesperado":
        print(f"[ERRO] EAN {ean} - timeout/erro inesperado")
        eans_com_erro.append(ean)
        return "erro"

    # produto encontrado - segue fluxo normal
    try:
        estoque = verificar_estoque(page)
    except ValueError as erro:
        print(f"[ERRO] EAN {ean} - nao foi possivel ler o estoque: {erro}")
        eans_com_erro.append(ean)
        return "erro"

    if estoque <= ESTOQUE_MINIMO:
        enviar_ao_falteiro(page, QUANTIDADE_SOLICITADA)
        print(f"[FALTEIRO] EAN {ean} - estoque {estoque}, solicitado +{QUANTIDADE_SOLICITADA}")
        return "falteiro"

    print(f"[OK] EAN {ean} - estoque {estoque}, nao precisa de falteiro")
    return "ok"
    # (removi o print que estava depois do return acima - ele nunca rodava)


def salvar_erros(caminho: str, eans_com_erro: list[str]) -> None:
    if not eans_com_erro:
        print("[SALVAR] Nenhum erro para salvar.")
        return
    print(f"[SALVAR] Gravando {len(eans_com_erro)} EAN(s) com erro em {caminho}")
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(eans_com_erro))


def main() -> None:
    print("=== INICIO DO SCRIPT FALTEIRO ===")
    eans = carregar_eans(ARQUIVO_EANS)
    if not eans:
        print("Nenhum EAN encontrado no arquivo. Encerrando.")
        return

    print(f"{len(eans)} codigos carregados.")

    total = len(eans)
    contagem = {"falteiro": 0, "ok": 0, "erro": 0}
    eans_com_erro: list[str] = []

    with sync_playwright() as pw:
        print("[NAVEGADOR] Iniciando Chromium...")
        navegador = pw.chromium.launch(headless=False)
        page = navegador.new_page()

        aguardar_login_manual(page)

        for indice, ean in enumerate(eans, start=1):
            print(f"\n--- Processando {indice}/{total} ---")
            categoria = processar_ean(page, ean, eans_com_erro)
            contagem[categoria] += 1
            time.sleep(2)  # pequena pausa entre buscas

        print("[NAVEGADOR] Fechando navegador...")
        navegador.close()                #depois q corrigir os bugs, reativar

    salvar_erros(ARQUIVO_ERROS, eans_com_erro)

    resumo = (
        f"Total processado: {total}\n"
        f"Foram ao Falteiro: {contagem['falteiro']}\n"
        f"Nao precisaram: {contagem['ok']}\n"
        f"Com erro: {contagem['erro']}"
    )
    print("\n" + resumo)

    if eans_com_erro:
        notificar(
            f"Senhor, {contagem['erro']} produto(s) deram erro na busca. "
            f"Verifique o arquivo erros_falteiro.txt para tentar novamente."
        )
    else:
        notificar(f"Falteiro concluido sem erros.\n{resumo}")

    print("=== FIM DO SCRIPT FALTEIRO ===")


if __name__ == "__main__":
    main()