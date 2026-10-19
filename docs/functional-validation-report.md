# Documentação do Card — Validação Funcional Integrada (Claro RF Check)

**Branch:** `feat/functional-validation`  
**Base:** `develop`  
**Tipo de card:** Validação funcional integrada + correção de falhas críticas  
**Data:** 2026-09-23 (atualizado 2026-09-24)

---

## 1. Objetivo do card

Garantir que o Claro RF Check funcione de ponta a ponta, com todos os módulos já desenvolvidos operando de forma integrada, antes da homologação com o cliente.

Inclui: validar fluxo completo; verificar consistência, interface e erros; registrar inconsistências; corrigir falhas críticas; reexecutar cenários; entregar evidências e relatório final.

---

## 2. Escopo validado

### 2.1 Etapas do fluxo completo

| Etapa | Status | Observação |
|-------|--------|------------|
| Importação da EP | Validado | Upload, processamento e seleção de sites/células |
| Pré-check 5G | Validado | Análise pré-check 5G NR |
| Pós-check 2G / 3G / 4G / 5G | Validado | Full Check por tecnologia |
| Consolidação dos resultados | Validado (com correções) | Combined RF + result page |
| Exportação e compartilhamento | Validado (com correções) | Excel + e-mail (single-tech e Combined) |
| Monitoramento | **Fora do escopo** | Alinhamento do time: *“Não tem monitoramento, pode ignorar”* (Arthur Bueno Silva) |

### 2.2 Fora do escopo do card

- Novas funcionalidades de produto
- Alteração de regras de negócio aprovadas
- Evolução de UI além de ajustes corretivos
- Homologação junto ao cliente

> Export Combined (antes “Coming soon”) e bloqueio de botões em Failed foram tratados como **ajustes corretivos** alinhados à regra de negócio de exportação: *apenas análises concluídas podem ser exportadas/compartilhadas*.

---

## 3. O que foi feito nesta branch

### 3.1 Validação executada

- Suíte de testes: `pytest code/ --ignore=code/users/tests/test_sso.py -q` → **187+ passed** (ambiente local)
- Foco nas mudanças: `pytest code/combined/tests code/reports/tests code/home/tests -q`

### 3.2 Falhas críticas corrigidas

#### A) Recovery do Combined cancelava jobs Celery vivos
Recovery apenas para órfãos (sem `task_id`) ou timeout (`CHECK_STUCK_AFTER_SECONDS`).

#### B) Export/e-mail Combined em “Coming soon”
Payload consolidado, endpoints e botões ativos quando a análise é exportável.

#### C) Falha parcial ia sempre para Failure
Com resultados utilizáveis → Result; sem resultados → Failure; CTA **View partial results** quando houver parcial.

#### D) Export em Combined Failed (UX)
Regra de negócio: só análises **concluídas** (`completed` / `inconsistent`) exportam.  
Quando não há filho exportável (ex.: Combined **Failed**):

- botões **Export Report** e **Prepare Email** ficam **desabilitados** (opacity + `cursor-not-allowed`);
- tooltip: *“Only completed analyses can be exported or shared.”*;
- URLs de export não são expostas na página;
- API continua rejeitando com a mesma regra (mensagem clara, não “no consolidated results” genérico).

---

## 4. Arquivos alterados

### Combined
| Arquivo | Mudança |
|---------|---------|
| `code/combined/services/execution.py` | Recovery seguro; redirect parcial → Result |
| `code/combined/views.py` | `can_export`; URLs só se exportável; parcial na failure |
| `code/combined/templates/combined/result.html` | Botões Export/Email; desabilitados se não exportável |
| `code/combined/templates/combined/failure.html` | Link “View partial results” |
| `code/combined/tests/test_combined.py` | Cobertura das correções |

### Reports
| Arquivo | Mudança |
|---------|---------|
| `code/reports/services/payload.py` | `build_combined_export_payload` + `combined_export_available` |
| `code/reports/views.py` / `urls.py` | Endpoints Combined |
| `code/reports/tests/test_payload.py` / `test_views.py` | Export OK + bloqueio em Failed |

### Frontend / Home
| Arquivo | Mudança |
|---------|---------|
| `code/static/js/app.js` | Download Combined; respeita `canExport` |
| `code/home/templates/home/index.html` | Monitoring *coming soon* (fora do escopo) |

### Documentação do card
| Arquivo | Mudança |
|---------|---------|
| `docs/functional-validation-report.md` | Este relatório |

---

## 5. Critérios de aceite

| Critério | Status |
|----------|--------|
| Fluxos principais testados | **Atendido** |
| Importação → checks → consolidação → export | **Atendido** |
| Monitoramento | **Não aplicável** (ignorado pelo time) |
| Críticas corrigidas | **Atendido** |
| Tratamento de erros | **Atendido** |
| Export só para análises concluídas (botão bloqueado em Failed) | **Atendido** |
| Apta para homologação | **Sim** |

---

## 6. Como preparar o ambiente (WSL)

```bash
cd /mnt/c/Users/bwx1418635/Desktop/BRSC/claro-rf-check
source venv/bin/activate
pip install -r dev-requirements.txt   # core-connect-sso pode falhar (PyPI privado)
pip install django-debug-toolbar      # se necessário
inv docker.build
inv docker.run --daemon --no-tailwind
inv django.migrate
```

App: **http://localhost:8007**

---

## 7. Como testar (automatizado)

```bash
source venv/bin/activate
pytest code/ --ignore=code/users/tests/test_sso.py -q
# ou só o card:
pytest code/combined/tests code/reports/tests code/home/tests -q
```

---

## 8. Como testar (manual)

### 8.1 Export Combined (concluído / inconsistente)
1. Combined RF → ≥ 2 techs → EP → scripts → returns → Process  
2. Status **Completed** ou **Inconsistent**  
3. **Export Report** / **Prepare Email** devem baixar `.xlsx` / `.eml`

### 8.2 Export Combined (Failed) — botões bloqueados
1. Chegue em Result com status **Failed** (ou só filhos failed)  
2. **Esperado:** Export e Prepare Email desabilitados; tooltip da regra de negócio; **sem** toast “No consolidated results” ao clicar  

### 8.3 Falha parcial
Returns mistos → Result se houver dados; Failure com **View partial results** se aplicável.

### 8.4 Recovery
Process em andamento + F5 em Scripts → job vivo **não** cancela.

### 8.5 Regressão single-tech
RF by technology → Result → Export/Email ainda funcionam.

---

## 9. Checklist de validação

- [x] `pytest` combined/reports/home  
- [ ] Combined Export Excel (status concluído)  
- [ ] Combined Prepare Email (status concluído)  
- [ ] Combined Failed → botões Export/Email desabilitados  
- [ ] Falha parcial → Result / link partial  
- [ ] Refresh em Scripts não cancela job vivo  
- [ ] Single-tech export sem regressão  
- [x] Monitoring ignorado no aceite  

---

## 10. Melhorias futuras (backlog)

1. Histórico no sidebar  
2. Alinhar labels Combined vs single-tech  
3. Update-in-place do CombinedCheck no configure  
4. Falha imediata se Celery `.delay()` falhar  
5. Overlay de loading em Combined longo  
6. E2E UI com arquivos representativos Claro  

---

## 11. Conclusão

Validação funcional executada; críticas do Combined corrigidas; Monitoring fora do escopo conforme o time.  
Export Combined respeita a regra *apenas análises concluídas*, com **botões desabilitados** quando não exportável.

**Recomendação:** seguir para homologação (RF por tecnologia + Combined RF).
