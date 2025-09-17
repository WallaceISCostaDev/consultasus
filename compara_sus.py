import streamlit as st
import pandas as pd
import unicodedata
from decimal import Decimal, InvalidOperation
from io import BytesIO
import xlsxwriter
st.set_page_config(page_title="Comparador SUS", layout="wide")
st.title("🩺 Comparador de Profissionais da Saúde (por CNS ou Nome)")
st.link_button("Baixe os dados aqui (Competência Antiga/Atual)","https://cnes.datasus.gov.br/pages/profissionais/extracao.jsp")

# Função para normalizar nomes de colunas
def normalize_col(col_name):
    nfkd = unicodedata.normalize('NFKD', col_name)
    only_ascii = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    return only_ascii.strip().lower()

# Função para corrigir CNS (remove notação científica, força 15 dígitos)
def corrigir_cns(cns_valor):
    try:
        cns_str = str(cns_valor).replace(",", ".").replace(" ", "").strip()
        if 'e' in cns_str.lower():
            cns_decimal = Decimal(cns_str)
            cns_str = str(cns_decimal.to_integral_value())
        return cns_str.zfill(15)
    except (InvalidOperation, ValueError):
        return str(cns_valor).strip()

# Função para converter dataframe para Excel bytes
def to_excel_bytes(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True)
    return output.getvalue()

# Upload dos arquivos
arquivo_antigo = st.file_uploader("📂 Envie o arquivo ANTIGO (CSV)", type="csv")
arquivo_novo = st.file_uploader("📂 Envie o arquivo NOVO (CSV)", type="csv")

if arquivo_antigo and arquivo_novo:
    # Leitura dos arquivos
    df_antigo = pd.read_csv(arquivo_antigo, sep=";", dtype=str, encoding="utf-8").fillna('')
    df_novo = pd.read_csv(arquivo_novo, sep=";", dtype=str, encoding="utf-8").fillna('')

    # Normaliza colunas
    df_antigo.columns = [normalize_col(c) for c in df_antigo.columns]
    df_novo.columns = [normalize_col(c) for c in df_novo.columns]

    # Remove coluna 'competencia' se existir
    df_antigo = df_antigo.drop(columns=[c for c in df_antigo.columns if 'competencia' in c], errors='ignore')
    df_novo = df_novo.drop(columns=[c for c in df_novo.columns if 'competencia' in c], errors='ignore')

    # Corrige CNS se a coluna existir
    if 'cns' in df_antigo.columns:
        df_antigo['cns'] = df_antigo['cns'].apply(corrigir_cns)
    if 'cns' in df_novo.columns:
        df_novo['cns'] = df_novo['cns'].apply(corrigir_cns)

    # Seleciona chave primária para comparação
    colunas_comuns = sorted(list(set(df_antigo.columns).intersection(df_novo.columns)))
    chave = st.selectbox("🔑 Escolha a chave para comparar os dados:", colunas_comuns, index=colunas_comuns.index('cns') if 'cns' in colunas_comuns else 0)

    # Remove duplicatas pela chave
    df_antigo = df_antigo.drop_duplicates(subset=chave, keep='first')
    df_novo = df_novo.drop_duplicates(subset=chave, keep='first')

    # Define índice
    df_antigo_indexado = df_antigo.set_index(chave)
    df_novo_indexado = df_novo.set_index(chave)

    # Verifica se colunas são compatíveis (exceto chave)
    colunas_antigas = set(df_antigo_indexado.columns)
    colunas_novas = set(df_novo_indexado.columns)

    if colunas_antigas != colunas_novas:
        st.error("❌ Os arquivos têm colunas diferentes.")
        st.write("📄 Colunas ANTIGO:", sorted(colunas_antigas))
        st.write("📄 Colunas NOVO:", sorted(colunas_novas))
        st.stop()

    # Parte 1: Comparação geral dos dados (com mesma chave)
    chaves_comuns = df_antigo_indexado.index.intersection(df_novo_indexado.index)
    registros_alterados = []

    for valor_chave in chaves_comuns:
        linha_antiga = df_antigo_indexado.loc[valor_chave]
        linha_nova = df_novo_indexado.loc[valor_chave]
        mudou = False
        diff = {chave: valor_chave}

        for coluna in df_antigo_indexado.columns:
            va = str(linha_antiga[coluna]).strip()
            vn = str(linha_nova[coluna]).strip()

            if va != vn:
                diff[coluna] = f"{va} ➜ {vn}"
                mudou = True
            else:
                diff[coluna] = vn

        if mudou:
            registros_alterados.append(diff)

    # Parte 2: Detecta mudança de CNS se a chave for "nome"
    registros_cns_trocado = []
    if chave == "nome" and "cns" in df_antigo.columns and "cns" in df_novo.columns:
        mapa_antigo = df_antigo.groupby("nome")["cns"].apply(set).to_dict()
        mapa_novo = df_novo.groupby("nome")["cns"].apply(set).to_dict()

        for nome in set(mapa_antigo.keys()).intersection(mapa_novo.keys()):
            cns_antigos = mapa_antigo[nome]
            cns_novos = mapa_novo[nome]

            if cns_antigos != cns_novos:
                registros = df_novo[df_novo["nome"] == nome]
                for _, linha in registros.iterrows():
                    dados = linha.to_dict()
                    dados["cns_antigo(s)"] = ", ".join(cns_antigos)
                    dados["cns_novo"] = linha["cns"]
                    registros_cns_trocado.append(dados)

    # Exibição dos resultados
    total = 0

    if registros_alterados:
        df_dif = pd.DataFrame(registros_alterados).set_index(chave)
        st.subheader("📌 Profissionais com dados alterados")
        st.success(f"🔍 {len(df_dif)} registros com alterações encontradas.")
        st.dataframe(df_dif, use_container_width=True)

        # Botões de download CSV e XLSX para alterações gerais
        csv_dif = df_dif.to_csv().encode("utf-8")
        xlsx_dif = to_excel_bytes(df_dif)
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("⬇️ Baixar CSV das alterações", csv_dif, "dados_alterados.csv", "text/csv")
        with col2:
            st.download_button("⬇️ Baixar XLSX das alterações", xlsx_dif, "dados_alterados.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        total += len(df_dif)

    if registros_cns_trocado:
        df_cns = pd.DataFrame(registros_cns_trocado)
        st.subheader("🔁 Profissionais com CNS alterado (mesmo nome)")
        st.warning(f"⚠️ {len(df_cns)} profissionais com CNS diferente entre os arquivos.")
        st.dataframe(df_cns, use_container_width=True)

        # Botões de download CSV e XLSX para alterações de CNS
        csv_cns = df_cns.to_csv(index=False).encode("utf-8")
        xlsx_cns = to_excel_bytes(df_cns)
        col3, col4 = st.columns(2)
        with col3:
            st.download_button("⬇️ Baixar CSV das mudanças de CNS", csv_cns, "cns_alterado.csv", "text/csv")
        with col4:
            st.download_button("⬇️ Baixar XLSX das mudanças de CNS", xlsx_cns, "cns_alterado.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        total += len(df_cns)

    if total == 0:
        st.info("✅ Nenhuma alteração detectada.")
