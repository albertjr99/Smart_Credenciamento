# 📋 Documentos Disponíveis na Pasta Modelos

## ✅ Documentos Atualmente Disponíveis

### Termos de Credenciamento
1. **TermodeCredenciamentoAgenteAutonomodeInvestimentos_IPAJM.xlsx**
   - Termo para credenciamento de Agente Autônomo de Investimentos

2. **TermodeCredenciamentoAdministradorouGestordeFundodeInvestimento_IPAJM.xlsx**
   - Termo para credenciamento de Administrador ou Gestor de Fundo de Investimento

3. **TermodeCredenciamentoDistribuidor_IPAJM.xlsx**
   - Termo para credenciamento de Distribuidor

4. **TermodeCredenciamentoCustodiante_IPAJM.xlsx**
   - Termo para credenciamento de Custodiante

5. **TermodeCredenciamentoInstituioFinanceiraBancriaemissoradeativofinanceiroderendafixa_IPAJM.xlsx**
   - Termo para credenciamento de Instituição Financeira Bancária emissora de ativo financeiro de renda fixa

6. **TermodeCadastramentoFundosdeInvestimentos.xlsx**
   - Termo de cadastramento de Fundos de Investimentos

### Declarações
7. **Declaracao_Unificada.docx**
   - Declaração Unificada padrão

8. **Declaracao_Unificada_Intermediario_TPF.docx**
   - Declaração Unificada específica para Intermediário TPF

### Checklists
9. **Checklist_Credenciamento_AnexoNP43.xlsm**
   - Checklist de Credenciamento (Anexo NP43)

10. **Checklist_Cadastro_Fundos_CADPREV.xlsx**
    - Checklist para Cadastro de Fundos no CADPREV

### Informações e Instruções
11. **Informacoes_preenchimento_CADPREV.xlsx**
    - Informações e instruções para preenchimento do CADPREV

12. **exemplo_checklist.txt**
    - Arquivo de exemplo demonstrativo

13. **README.md**
    - Instruções sobre como usar a pasta de modelos

## 🎯 Como os Nomes Aparecem no Sistema

O sistema automaticamente converte os nomes dos arquivos para títulos mais amigáveis. Por exemplo:

- `TermodeCredenciamentoDistribuidor_IPAJM.xlsx` 
  → Aparece como: **"Termo de Credenciamento Distribuidor IPAJM"**

- `Declaracao_Unificada.docx`
  → Aparece como: **"Declaração Unificada"**

## 📝 Personalizando os Nomes e Descrições

Para criar nomes e descrições personalizadas, edite o arquivo `app.py` adicionando entradas no dicionário `descricoes_mapeamento`:

```python
descricoes_mapeamento = {
    'TermodeCredenciamentoDistribuidor': {
        'nome': 'Termo de Credenciamento - Distribuidor',
        'descricao': 'Termo oficial para credenciamento de instituições distribuidoras junto ao IPAJM.'
    },
    'Declaracao_Unificada': {
        'nome': 'Declaração Unificada',
        'descricao': 'Declaração unificada contendo todas as informações necessárias para o processo de credenciamento.'
    },
    # Adicione mais mapeamentos aqui...
}
```

## 🔄 Atualizando os Documentos

Para atualizar ou adicionar novos documentos:

1. **Adicione/Substitua** o arquivo na pasta `Modelos/`
2. **Mantenha um nome descritivo** usando underscores
3. **Não é necessário** reiniciar o servidor
4. **Recarregue** a página de Modelos no navegador

## ✨ Status

✅ **13 documentos** atualmente disponíveis
✅ Sistema detecta automaticamente novos arquivos
✅ Download funcionando corretamente
✅ Integrado nas páginas de IF e RPPS

---

**Última atualização**: $(date)
