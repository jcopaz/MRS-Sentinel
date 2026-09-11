# auth/confirmar_telefone.py — Confirmação de telefone (recuperação por SMS)
#
# DORMENTE desde 2026-09-11 (app.py não chama mais esta tela): existia pra
# capturar telefone de quem já tinha conta antes da v11.0.0, viabilizando
# reset por SMS. Revertida no mesmo dia — sem orçamento pra SMS agora (ver
# core/versao.py 13.0.0, auth/telefone.py, integracoes/brevo.py). Fica
# pronta pra reativar (bastaria importar e chamar de novo em app.py::main())
# se um dia fizer sentido retomar.
#
# Descrição original: contas criadas ANTES de 2026-09-11 não passavam pela
# captura de telefone (deve_trocar_senha já era False pra elas — não caíam
# em auth/trocar_senha_obrigatoria.py, que ganhou o campo nessa data). Esta
# tela interceptava o app UMA VEZ, só pra quem ainda não tinha telefone
# cadastrado (usuarios.telefone IS NULL) — depois de preencher, nunca mais
# aparecia. Mesmo mecanismo de gate de app.py::main() já usado pra troca de
# senha obrigatória, verificado DEPOIS dela.

import streamlit as st

from auth.session import get_usuario, clear_session
from auth.telefone import validar_e_formatar_telefone
from database.queries import atualizar_telefone, log_acesso


def render_confirmar_telefone() -> None:
    st.markdown("## 📱 Confirme seu celular")
    st.info(
        "Passo único: cadastre seu celular para poder recuperar sua senha "
        "por SMS caso esqueça. Usamos só para isso — nenhum outro envio."
    )

    usuario = get_usuario()

    with st.form("form_confirmar_telefone"):
        telefone_bruto = st.text_input(
            "Celular com DDD", placeholder="(11) 91234-5678", key="ct_telefone",
        )
        enviar = st.form_submit_button(
            "✅ Confirmar e continuar", type="primary", key="ct_btn_enviar",
        )

    if enviar:
        telefone = validar_e_formatar_telefone(telefone_bruto)
        if not telefone:
            st.error("⚠️ Informe um celular válido, com DDD.")
        else:
            atualizar_telefone(usuario["id"], telefone)
            usuario["telefone"] = telefone
            st.session_state["usuario"] = usuario
            try:
                log_acesso(usuario["id"], "CONFIRMAR_TELEFONE", {"telefone": telefone})
            except Exception:
                pass
            st.success("✅ Celular confirmado!")
            st.rerun()

    st.markdown("---")
    st.caption("Não é você quem deveria estar confirmando isto agora?")
    if st.button("🚪 Sair", key="ct_btn_sair"):
        clear_session()
        st.rerun()
