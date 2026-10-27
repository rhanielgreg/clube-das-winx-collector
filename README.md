# Coletor Railway + ranking sazonal — Clube das Winx

## Missão 13 — evidência histórica e continuidade observacional

**Requer a migração011 do site antes de publicar este coletor.** O modo legado passa a ler `get_service_source_evidence_v1` e grava `collector_runs.source_diagnostics` ao concluir com sucesso. São somente HMACs do ID observado/escopo e hashes do BLOB/chave legada; não certificam vida, geração do mundo ou cobertura. A mesma chave legada com ID diferente/ausente após uma observação válida é recusada antes da ingestão, preservando as métricas. Sem contrato instalado, falha explicitamente; não usar fallback para contornar a proteção. O coletor anterior continua compatível com011 e ignora a coluna nova.

Arquivos reais em `.cache/Lua/ttf_stats_mp` confirmaram morte do ID de Ebony Adama antes do ID de Bruce Crawley, associado à mesma conta nas cópias SQLite. O log de usuário também registra a morte. Isso não autoriza vincular históricos do Supabase apenas por nome. `identity_evidence.py ... --record ARQUIVO_LOCAL` confronta o ID completo e o usuário do registro com a cópia local; não ingere dados. `death_recorded_at` é horário de registro da morte, não nascimento/idade inferidos.

O pin passa a incluir também `TTF_StatsMP_Shared.lua`, que define a pasta, categorias e snapshot; os quatro arquivos são conferidos no modo nativo. Kills/distância/dias e coorte continuam com os gates existentes. Códigos operacionais agora distinguem autenticação/conexão, snapshot, contrato, parser/identidade e ingestão, sem incluir IDs ou mensagens da fonte no campo error_code. Logs registram contagem de métricas indisponíveis, sem convertê-las em zero.

## Missão 12 — integridade adicional, modo legado preservado

O snapshot agora compara também os bytes de uma segunda leitura de DB/sidecars: tamanho e mtime iguais não bastam para detectar reescritas no mesmo segundo. Nenhuma escrita remota foi adicionada; credenciais, cron, salt e modos existentes são conservados. O leitor nativo rejeita o mesmo ID de vida reclamado por duas contas no mesmo mundo.

`python -B identity_evidence.py COPIA_ANTERIOR.db COPIA_ATUAL.db` compara **cópias locais destacadas**, em SQLite somente leitura, sem imprimir contas/IDs. Sidecars tornam a cópia inadequada para esse diagnóstico. IDs novos não certificam automaticamente nascimento, cobertura ou namespace. O comando não ingere nem ativa o contrato.

A cópia real conferida nesta missão conserva os cinco IDs: três vivos/dois mortos. Em relação à primeira amostra houve uma morte, sem nascimento/renomeação observado. **TTF/life-v1 continuam desativados em produção** até cumprir esses eventos e confirmar a geração do mundo. Não associar o histórico legado por nome. Migração 010 do site prepara guardas transacionais adicionais; não habilita a coorte e não muda o payload legado. Testes atuais: 28 Python isolados; a validação do deployment produtivo deve constar no checkpoint do site.

## Go-live — Missão 08

A imagem Docker Python 3.12 foi construída e os 22 testes passaram também dentro dela. A transição conserva inicialmente o modo legado. As migrações do site são aplicadas manualmente na ordem 001–004, 006, 005, 007; 005 prepara os leitores, 007 prepara a ativação, sem trocar a coorte automaticamente. Somente após um lote nativo completo validado a RPC privada de ativação libera o ranking de vidas.

O snapshot inclui agora a verificação do journal SQLite: journal ativo e sidecar sem permissão bloqueiam a leitura antes do download. WAL/SHM continuam verificados. Nenhuma escrita é feita na origem.

O modo nativo exige somente as configurações adicionais não secretas LIFE_PIPELINE_VERSION, LIFE_SOURCE_NAMESPACE_UUID e TTF_SOURCE_ROOT; não trocar o salt ou as credenciais existentes. Registros legados continuam preservados, sem atribuição de pontos/medalhas passados por nome. Pontos do novo perfil de vida começam em sua primeira leitura validada, separados dos totais TTF observados.

## Estado da Missão Master 07 — 25/10/2026

Clone legítimo em `codex/mission07`, base `master@07dde5c`. Vínculo Railway confirmado por sessão autenticada: projeto `heartfelt-surprise`, serviço `winx-ranking-collector`, branch produtiva `master`, Dockerfile/Python 3.12, `python collector.py`, cron de 5 minutos e política Never. A feature branch não é a branch de deploy. A correção 001 foi aplicada separadamente no Supabase; o usuário corrigiu o SFTP e uma coleta de 5 personagens foi confirmada no banco. Nenhuma credencial foi alterada pelo agente e o código novo continua sem implantação.

O checkpoint consolidado está no repositório do site, `docs/MASTER07-CHECKPOINT.md`. Migrações canônicas 001–005 pertencem àquele repositório. `schema.sql` deste coletor é somente bootstrap de banco vazio, agora protegido contra reaplicação. Não usar para atualizar banco existente. Corrigida sua ACL de 10 para a assinatura real de 11 argumentos; encerramento antigo fica bloqueado até a migração oficial.

## Fluxo

`BisectHosting (SFTP) → Railway Cron → Supabase → API Vercel → site`

O Railway executa `collector.py` a cada 5 minutos, coleta uma cópia temporária e somente leitura de `players.db`, valida o SQLite e encerra. Não é um bot ou worker permanente.

## Segurança e consistência

- Validação obrigatória da chave SSH por `known_hosts`; `AutoAddPolicy` não é usado.
- DB, WAL e SHM são verificados antes e depois do download. Se algum arquivo mudar ou aparecer durante a transferência, a leitura é rejeitada e repetida com backoff.
- `PRAGMA query_only` e `PRAGMA integrity_check` são aplicados à cópia temporária.
- Um lock atômico no Supabase impede duas execuções simultâneas. O lock também expira automaticamente.
- Usuário da conta é armazenado apenas como hash com salt. Steam ID, IP, coordenadas e o BLOB não são publicados.
- A `service_role` fica somente no Railway e na CLI administrativa; o site usa a chave pública e RPCs com saída restrita.

## Importante sobre estatísticas

O leitor de `TTF_KillStats` foi validado contra cinco registros reais. Os testes usam apenas os fragmentos TTF anonimizados, sem contas, nomes, Steam IDs, coordenadas ou BLOB completo. Categorias, armas e veículos precisam concordar; valores inconsistentes são rejeitados.

Kills totais incluem todas as categorias; kills corpo a corpo incluem armas de contato e desarmado. O código Lua instalado confirma que `TTFStatsGameTimeSeconds` acumula segundos reais de jogo, não sobrevivência. Por isso sobrevivência permanece indisponível até uma fonte própria ser validada. A coleta reflete salvamentos do jogo; não é instantânea.

## Configuração

1. Se alguma senha SFTP foi compartilhada em chat ou repositório, troque-a antes de continuar.
2. Crie um projeto Supabase dedicado e execute `schema.sql` no SQL Editor.
3. Configure no Railway as variáveis de `.env.example`. Nunca faça commit de `.env`.
4. Confirme a fingerprint SFTP com a hospedagem e salve a linha completa em `SFTP_KNOWN_HOSTS`.
5. Rode primeiro com `DRY_RUN=true`; confira que o banco é lido sem alterações.
6. Após validar a leitura, mude para `DRY_RUN=false`. Configure o Cron Schedule do serviço Railway para `*/5 * * * *`, início `python collector.py` e reinício `Never`. O modo de teste também verifica o Supabase por uma RPC somente leitura quando as credenciais estão presentes.
7. Na Vercel, configure `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` para liberar o painel público.

## Temporadas — controle manual do Admin

As estatísticas ficam separadas por temporada. Ao encerrar, o vencedor e a classificação final permanecem no histórico; uma nova temporada cria uma nova linha de base.

```powershell
# listar
python season_admin.py list

# iniciar
python season_admin.py start --name "Temporada 1" --slug "temporada-1"

# encerrar (exige confirmação explícita)
python season_admin.py close --id "UUID_DA_TEMPORADA" --yes

# se o Admin precisar decidir um empate
python season_admin.py close --id "UUID_DA_TEMPORADA" --winner-id "UUID_DO_JOGADOR" --yes
```

Após 003/005, só vidas certificadas e confirmadas vivas competem; offline continua elegível. Kills da temporada, desempate por tempo jogado registrado e UUID. Um `--winner-id` divergente do primeiro classificado é rejeitado pelo banco. Todos os participantes certificados mortos com evidência recente suficiente: O Apocalipse Venceu, sem campeão. Estado desconhecido ou coleta falhando bloqueia encerramento. Não executar os exemplos em produção apenas para testar.

## Limitação de identidade do personagem

Sem um identificador de vida confirmado no SQLite, `character_key` combina conta anonimizada e nome do personagem. Se a mesma conta reutilizar exatamente o mesmo nome após morrer, as vidas podem ser tratadas como o mesmo personagem. Não use o histórico de mortes como definitivo até a origem fornecer um identificador confiável.

## Contrato futuro de vidas — opt-in

Vazio/`legacy` em `LIFE_PIPELINE_VERSION` mantém o protocolo anterior. `life-v1` exige 004/005, catálogo de 100, permissões conferidas e emissor confiável **ainda não instalado ou validado**. Não habilitar somente porque a variável existe. A migração 005 muda a população do ranking; coordenar a transição com o site e o banco.

`WinxLifeV1` não é um campo atribuído ao TTF atual: é o envelope futuro em modData, com `payload_json` UTF-8 e HMAC-SHA256 hexadecimal em `signature`. A chave `LIFE_ATTESTATION_KEY` (mínimo 32 caracteres) deve ser provisionada por secret store, nunca pelo Git/chat. O payload contém `schema=winx-life-v1`, `world_id`, `life_id`, `account_id`, `source_username`, `character_name`, `source_observed_at`, `alive` e `metrics` tipadas (`value`, `unit`, `scope=life`, `coverage`). Modificar/instalar emissor no jogo exige autorização adicional.

A conta Steam é anonimizada com salt, não usada como nome. O UUID da vida é obrigatório; renomear mantém vida e reutilizar nome não reaproveita medalhas. Linha SQLite, assinatura e estado precisam concordar. Mortos legados sem envelope não ganham nova identidade; vivo/desconhecido sem envelope faz a coleta falhar antes de enviar observações. Não há fallback silencioso para a ingestão por nome.

Reutilizar TTF exige `ttf_counters_are_lifetime=true`, `ttf_metrics_digest` dos contadores canônicos e `ttf_coverage`. O digest liga os contadores ao snapshot assinado; o emissor precisa comprovar a semântica vitalícia. Veículos já participam do total e não são adicionados novamente. As cinco fixtures reais anonimizadas comprovam os contadores, sem comprovar IDs/unidades/escopo da instalação atual.

Unidades do protocolo: `count`, `seconds` para tempo jogado, `world_days` para sobrevivência e `meters` para as distâncias separadas. Não converter horas jogadas em dias no mundo. Dados ausentes não viram zero. Observação representa a leitura do snapshot, não a data exata de nascimento, morte ou conquista. O novo fluxo registra sucesso somente após concluir envios; falha parcial registra execução falha e impede encerramento no contrato oficial.

Teste local sem acessar serviços: `python -B -m unittest discover -p "test*.py"`. O site contém testes de integração dos dois leitores com TTF anonimizado, banco PostgreSQL descartável, API e apresentação reais; apenas o transporte PostgREST é simulado. Múltiplas sessões e PostgREST reais ainda exigem homologação.

## Leitor do TTF já existente — `ttf-mp-v1`

A inspeção em leitura encontrou `TTFStatsMP.characterID` em 5/5 registros, associado à conta Steam do SQLite. A variante habilitada é `twistonfirestatsmpstable`; a fonte instalada gera um ID com timestamp e componente aleatório, grava no modData e o preserva nas leituras seguintes. Não é necessário instalar o emissor futuro para esse leitor. Não usar nome ou ID de linha como substituto.

O modo `ttf-mp-v1` reutiliza integralmente a conexão SFTP existente. Lê as duas colunas adicionais `steamid`/`world`, valida a associação e anonimiza os IDs. `LIFE_SOURCE_NAMESPACE_UUID` deve identificar de forma estável a origem/geração do mundo, conferida pelo responsável; não gerar a cada execução ou reutilizar sem revisão após reset do mundo. `TTF_SOURCE_ROOT` aponta para a variante MP STABLE/42.19. Três fontes Lua são conferidas por SHA256, com stat/get somente leitura, antes de aceitar os campos; atualização do mod bloqueia o leitor até revisão.

O contador `distanceTracker` representa distância agregada em metros conforme o Lua instalado; não separa caminhada/direção. `TTFStatsGameTimeSeconds` é tempo jogado em segundos. Kills/tempo/distância são limites observados da vida, não prova de cobertura desde o nascimento: o mod pode ter sido instalado depois. Por isso igualdade a zero e homenagens que exigem histórico completo continuam bloqueadas. Dias no mundo não são derivados de horas jogadas.

**Manter o modo legado em produção** até haver recuperação verificável, migrações 002–005 compatíveis, namespace aprovado e transição coordenada da coorte. Sem dados ambíguos inventados ou backfill por nome. Nenhuma variável foi habilitada automaticamente. O Dockerfile inclui os dois módulos opt-in para evitar falha de importação num deploy futuro.
