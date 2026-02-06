# 📋 Pasta de Modelos de Documentos Oficiais

Esta pasta contém os modelos de documentos oficiais necessários para o processo de credenciamento de Instituições Financeiras junto ao RPPS.

## 📁 Como Adicionar Novos Modelos

1. **Adicione o arquivo** nesta pasta (formato PDF, DOC, DOCX, XLSX, etc.)
2. **Nomeie o arquivo** de forma descritiva usando underscores:
   - Exemplo: `termo_credenciamento.pdf`
   - Exemplo: `declaracao_unificada.docx`
   - Exemplo: `checklist_documentos.xlsx`

3. O sistema **detectará automaticamente** o novo arquivo e o exibirá na seção "Modelos de Documentos" do site.

## 📝 Documentos Recomendados

Os seguintes documentos são sugeridos para o processo de credenciamento:

### Documentos Institucionais
- ✅ **termo_credenciamento** - Termo de Credenciamento
- ✅ **declaracao_unificada** - Declaração Unificada
- ✅ **checklist** - Checklist de Documentos
- ✅ **apresentacao_institucional** - Apresentação Institucional

### Documentos Regulatórios
- ✅ **formulario_referencia** - Formulário de Referência CVM
- ✅ **qdd_anbima** - QDD Anbima Seção I
- ✅ **contrato_distribuicao** - Contrato de Distribuição

### Certidões
- ✅ **certidao_bacen** - Certidões do BACEN
- ✅ **certidao_anbima** - Certidão ANBIMA
- ✅ **certidoes_tributarias** - Certidões Tributárias (Municipal, Estadual, Federal)

## 🔧 Personalização de Nomes e Descrições

Para personalizar o nome e descrição de um documento no site, edite o arquivo `app.py` na seção:

```python
descricoes_mapeamento = {
    'seu_documento': {
        'nome': 'Nome Amigável do Documento',
        'descricao': 'Descrição detalhada do documento.'
    }
}
```

## 📌 Observações Importantes

- Os arquivos devem estar em formatos compatíveis: PDF, DOC, DOCX, XLSX, XLS, TXT
- Evite usar caracteres especiais nos nomes dos arquivos
- Use nomes descritivos e auto-explicativos
- Mantenha os documentos sempre atualizados
- Teste o download após adicionar novos arquivos

## ✅ Status

**Pasta criada e configurada com sucesso!**
Adicione seus modelos de documentos aqui e eles aparecerão automaticamente no sistema.
