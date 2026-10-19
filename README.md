# Coletor Railway + ranking sazonal — Clube das Winx

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

Kills totais incluem todas as categorias; kills corpo a corpo incluem armas de contato e desarmado. O campo de tempo TTF foi decodificado, mas fica indisponível como sobrevivência até confirmar sua semântica no código Lua. A coleta reflete salvamentos do jogo; não é instantânea.

## Configuração

1. Se alguma senha SFTP foi compartilhada em chat ou repositório, troque-a antes de continuar.
2. Crie um projeto Supabase dedicado e execute `schema.sql` no SQL Editor.
3. Configure no Railway as variáveis de `.env.example`. Nunca faça commit de `.env`.
4. Confirme a fingerprint SFTP com a hospedagem e salve a linha completa em `SFTP_KNOWN_HOSTS`.
5. Rode primeiro com `DRY_RUN=true`; confira que o banco é lido sem alterações.
6. Mude para `DRY_RUN=false`. `railway.json` agenda `collector.py` a cada cinco minutos.
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

O critério atual é kills da temporada; desempate por maior tempo de sobrevivência e, ainda empatado, nome em ordem alfabética apenas para estabilidade técnica. O Admin pode escolher explicitamente um jogador classificado com `--winner-id` quando o critério administrativo for necessário.

## Limitação de identidade do personagem

Sem um identificador de vida confirmado no SQLite, `character_key` combina conta anonimizada e nome do personagem. Se a mesma conta reutilizar exatamente o mesmo nome após morrer, as vidas podem ser tratadas como o mesmo personagem. Não use o histórico de mortes como definitivo até a origem fornecer um identificador confiável.
