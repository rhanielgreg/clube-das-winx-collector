# Coletor Railway + ranking sazonal — Clube das Winx

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
