-- Clube das Winx: ranking sazonal seguro e histórico de estatísticas.
-- Migração aditiva. Não remove nem altera dados existentes.
create extension if not exists pgcrypto;

create table if not exists public.game_players (
  id uuid primary key default gen_random_uuid(),
  player_key text not null unique,
  steam_username text,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);

create table if not exists public.game_characters (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references public.game_players(id) on delete restrict,
  character_key text not null unique,
  public_name text not null check (char_length(public_name) between 1 and 80),
  alive boolean,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  died_at timestamptz,
  source_blob_sha256 text not null
);

create table if not exists public.ranking_seasons (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 80),
  slug text not null unique check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  status text not null default 'active' check (status in ('draft', 'active', 'closed')),
  scoring_metric text not null default 'kills_total' check (scoring_metric in ('kills_total')),
  reward_message text not null default 'Premiação especial oferecida pelo Admin do servidor.',
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  closed_at timestamptz,
  check ((status = 'closed' and ended_at is not null) or status <> 'closed')
);

create unique index if not exists ranking_seasons_one_active
  on public.ranking_seasons ((status)) where status = 'active';

create table if not exists public.player_statistics_current (
  season_id uuid not null references public.ranking_seasons(id) on delete restrict,
  character_id uuid not null references public.game_characters(id) on delete restrict,
  baseline_kills_total integer,
  baseline_kills_firearm integer,
  baseline_kills_melee integer,
  source_kills_total integer,
  source_kills_firearm integer,
  source_kills_melee integer,
  kills_total integer,
  kills_firearm integer,
  kills_melee integer,
  survival_seconds bigint,
  observed_at timestamptz not null,
  source_blob_sha256 text not null,
  primary key (season_id, character_id),
  check (kills_total is null or kills_total >= 0),
  check (kills_firearm is null or kills_firearm >= 0),
  check (kills_melee is null or kills_melee >= 0),
  check (survival_seconds is null or survival_seconds >= 0)
);

create table if not exists public.player_stat_snapshots (
  id bigint generated always as identity primary key,
  season_id uuid not null references public.ranking_seasons(id) on delete restrict,
  character_id uuid not null references public.game_characters(id) on delete restrict,
  kills_total integer,
  kills_firearm integer,
  kills_melee integer,
  survival_seconds bigint,
  alive boolean,
  observed_at timestamptz not null,
  source_blob_sha256 text not null,
  unique (season_id, character_id, observed_at, source_blob_sha256)
);
create index if not exists player_stat_snapshots_profile_time
  on public.player_stat_snapshots (character_id, observed_at desc);

create table if not exists public.season_winners (
  season_id uuid primary key references public.ranking_seasons(id) on delete restrict,
  character_id uuid references public.game_characters(id) on delete restrict,
  winner_name text,
  final_kills_total integer,
  final_survival_seconds bigint,
  reward_message text not null,
  recorded_at timestamptz not null default now()
);

create table if not exists public.collector_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running' check (status in ('running', 'success', 'failed', 'skipped')),
  records_seen integer not null default 0,
  error_code text,
  source_fingerprint text
);
create index if not exists collector_runs_success_time
  on public.collector_runs (finished_at desc) where status = 'success';

create table if not exists public.collector_locks (
  lock_name text primary key,
  owner_token text not null,
  expires_at timestamptz not null,
  updated_at timestamptz not null default now()
);

alter table public.game_players enable row level security;
alter table public.game_characters enable row level security;
alter table public.ranking_seasons enable row level security;
alter table public.player_statistics_current enable row level security;
alter table public.player_stat_snapshots enable row level security;
alter table public.season_winners enable row level security;
alter table public.collector_runs enable row level security;
alter table public.collector_locks enable row level security;

revoke all on public.game_players, public.game_characters, public.ranking_seasons,
  public.player_statistics_current, public.player_stat_snapshots, public.season_winners,
  public.collector_runs, public.collector_locks from anon, authenticated;

create or replace function public.get_public_ranking(p_limit integer default 100)
returns table (
  profile_id uuid,
  season_id uuid,
  season_name text,
  rank_position bigint,
  character_name text,
  steam_username text,
  alive boolean,
  kills_total integer,
  kills_firearm integer,
  kills_melee integer,
  survival_seconds bigint,
  last_updated_at timestamptz
)
language sql stable security definer set search_path = ''
as $$
  with latest_player_character as (
    -- Seleciona apenas 1 personagem por jogador da Steam (o mais recente da conta)
    select distinct on (c.player_id)
      c.id as character_id,
      c.player_id,
      c.public_name,
      c.alive,
      p.steam_username,
      st.kills_total,
      st.kills_firearm,
      st.kills_melee,
      st.survival_seconds,
      st.observed_at,
      s.id as season_id,
      s.name as season_name
    from public.ranking_seasons s
    join public.player_statistics_current st on st.season_id = s.id
    join public.game_characters c on c.id = st.character_id
    join public.game_players p on p.id = c.player_id
    where s.status = 'active' and st.kills_total is not null
    order by c.player_id,
             -- Dá prioridade para o personagem vivo; se todos estiverem mortos, pega o mais recente
             case when c.alive = true then 0 else 1 end,
             c.last_seen_at desc,
             st.observed_at desc
  )
  select
    character_id as profile_id,
    season_id,
    season_name,
    row_number() over (order by kills_total desc nulls last, survival_seconds desc nulls last, coalesce(steam_username, public_name) asc) as rank_position,
    public_name as character_name,
    steam_username,
    alive,
    kills_total,
    kills_firearm,
    kills_melee,
    survival_seconds,
    observed_at as last_updated_at
  from latest_player_character
  order by kills_total desc nulls last, survival_seconds desc nulls last, coalesce(steam_username, public_name) asc
  limit least(greatest(coalesce(p_limit, 100), 1), 250);
$$;

create or replace function public.get_public_seasons(p_limit integer default 8)
returns table (
  season_id uuid,
  name text,
  slug text,
  status text,
  started_at timestamptz,
  ended_at timestamptz,
  winner_name text,
  winner_kills integer,
  reward_message text
)
language sql stable security definer set search_path = ''
as $$
  select s.id, s.name, s.slug, s.status, s.started_at, s.ended_at,
    w.winner_name, w.final_kills_total, s.reward_message
  from public.ranking_seasons s
  left join public.season_winners w on w.season_id = s.id
  where s.status in ('active', 'closed')
  order by case when s.status = 'active' then 0 else 1 end, s.started_at desc
  limit least(greatest(coalesce(p_limit, 8), 1), 50);
$$;

create or replace function public.get_public_ranking_status()
returns table (last_success_at timestamptz, records_seen integer, active_season_name text, ranked_players bigint)
language sql stable security definer set search_path = ''
as $$
  select r.finished_at, coalesce(r.records_seen, 0), s.name,
    (select count(*) from public.player_statistics_current st where st.season_id = s.id and st.kills_total is not null)
  from (select id, name from public.ranking_seasons where status = 'active' limit 1) s
  left join lateral (
    select finished_at, records_seen from public.collector_runs
    where status = 'success' order by finished_at desc nulls last limit 1
  ) r on true;
$$;

create or replace function public.get_public_player(p_profile_id uuid)
returns table (
  profile_id uuid,
  season_id uuid,
  season_name text,
  rank_position bigint,
  character_name text,
  steam_username text,
  alive boolean,
  kills_total integer,
  kills_firearm integer,
  kills_melee integer,
  survival_seconds bigint,
  last_updated_at timestamptz
)
language sql stable security definer set search_path = ''
as $$
  with ranked as (
    select c.id profile_id, s.id season_id, s.name season_name,
      row_number() over (partition by s.id order by st.kills_total desc nulls last, st.survival_seconds desc nulls last, coalesce(p.steam_username, c.public_name)) rank_position,
      c.public_name character_name, p.steam_username, c.alive, st.kills_total, st.kills_firearm, st.kills_melee,
      st.survival_seconds, st.observed_at last_updated_at, s.status, s.started_at
    from public.ranking_seasons s
    join public.player_statistics_current st on st.season_id = s.id
    join public.game_characters c on c.id = st.character_id
    join public.game_players p on p.id = c.player_id
    where s.status in ('active', 'closed') and st.kills_total is not null
  )
  select r.profile_id, r.season_id, r.season_name, r.rank_position, r.character_name, r.steam_username,
    r.alive, r.kills_total, r.kills_firearm, r.kills_melee, r.survival_seconds, r.last_updated_at
  from ranked r where r.profile_id = p_profile_id
  order by case when r.status = 'active' then 0 else 1 end, r.started_at desc limit 1;
$$;

create or replace function public.get_public_player_history(p_profile_id uuid, p_limit integer default 90)
returns table (observed_at timestamptz, kills_total integer, survival_seconds bigint, alive boolean)
language sql stable security definer set search_path = ''
as $$
  select p.observed_at, p.kills_total, p.survival_seconds, p.alive
  from public.player_stat_snapshots p
  where p.character_id = p_profile_id
  order by p.observed_at asc
  limit least(greatest(coalesce(p_limit, 90), 1), 365);
$$;

create or replace function public.acquire_collector_lock(p_owner text, p_ttl_seconds integer default 240)
returns boolean
language plpgsql security definer set search_path = ''
as $$
declare v_owner text;
begin
  insert into public.collector_locks(lock_name, owner_token, expires_at, updated_at)
  values ('players-db', p_owner, now() + make_interval(secs => least(greatest(p_ttl_seconds, 60), 900)), now())
  on conflict (lock_name) do update set owner_token = excluded.owner_token,
    expires_at = excluded.expires_at, updated_at = now()
  where public.collector_locks.expires_at < now() or public.collector_locks.owner_token = p_owner
  returning owner_token into v_owner;
  return v_owner = p_owner;
end;
$$;

create or replace function public.release_collector_lock(p_owner text)
returns void
language sql security definer set search_path = ''
as $$ delete from public.collector_locks where lock_name = 'players-db' and owner_token = p_owner; $$;

create or replace function public.ingest_player_observation(
  p_player_key text,
  p_character_key text,
  p_character_name text,
  p_alive boolean,
  p_blob_sha256 text,
  p_observed_at timestamptz,
  p_kills_total integer default null,
  p_kills_firearm integer default null,
  p_kills_melee integer default null,
  p_survival_seconds bigint default null,
  p_steam_username text default null
)
returns uuid
language plpgsql security definer set search_path = ''
as $$
declare
  v_player_id uuid;
  v_character_id uuid;
  v_season_id uuid;
  v_current public.player_statistics_current%rowtype;
begin
  if p_kills_total < 0 or p_kills_firearm < 0 or p_kills_melee < 0 or p_survival_seconds < 0 then
    raise exception 'negative statistics are invalid';
  end if;

  insert into public.game_players(player_key, steam_username, last_seen_at)
  values (p_player_key, p_steam_username, p_observed_at)
  on conflict (player_key) do update set
    steam_username = coalesce(excluded.steam_username, public.game_players.steam_username),
    last_seen_at = greatest(public.game_players.last_seen_at, excluded.last_seen_at)
  returning id into v_player_id;

  insert into public.game_characters(player_id, character_key, public_name, alive, first_seen_at, last_seen_at, died_at, source_blob_sha256)
  values (v_player_id, p_character_key, p_character_name, p_alive, p_observed_at, p_observed_at,
    case when p_alive = false then p_observed_at else null end, p_blob_sha256)
  on conflict (character_key) do update set
    public_name = excluded.public_name,
    alive = excluded.alive,
    last_seen_at = greatest(public.game_characters.last_seen_at, excluded.last_seen_at),
    died_at = case when excluded.alive = false then coalesce(public.game_characters.died_at, excluded.last_seen_at) else public.game_characters.died_at end,
    source_blob_sha256 = excluded.source_blob_sha256
  returning id into v_character_id;

  select id into v_season_id from public.ranking_seasons where status = 'active' limit 1;
  if v_season_id is null or p_kills_total is null then return v_character_id; end if;

  insert into public.player_statistics_current(
    season_id, character_id, baseline_kills_total, baseline_kills_firearm, baseline_kills_melee,
    source_kills_total, source_kills_firearm, source_kills_melee,
    kills_total, kills_firearm, kills_melee, survival_seconds, observed_at, source_blob_sha256)
  values (v_season_id, v_character_id, p_kills_total, p_kills_firearm, p_kills_melee,
    p_kills_total, p_kills_firearm, p_kills_melee, 0,
    case when p_kills_firearm is null then null else 0 end,
    case when p_kills_melee is null then null else 0 end,
    p_survival_seconds, p_observed_at, p_blob_sha256)
  on conflict (season_id, character_id) do update set
    source_kills_total = excluded.source_kills_total,
    source_kills_firearm = excluded.source_kills_firearm,
    source_kills_melee = excluded.source_kills_melee,
    kills_total = greatest(0, excluded.source_kills_total - public.player_statistics_current.baseline_kills_total),
    kills_firearm = case when excluded.source_kills_firearm is null or public.player_statistics_current.baseline_kills_firearm is null then null else greatest(0, excluded.source_kills_firearm - public.player_statistics_current.baseline_kills_firearm) end,
    kills_melee = case when excluded.source_kills_melee is null or public.player_statistics_current.baseline_kills_melee is null then null else greatest(0, excluded.source_kills_melee - public.player_statistics_current.baseline_kills_melee) end,
    survival_seconds = excluded.survival_seconds,
    observed_at = excluded.observed_at,
    source_blob_sha256 = excluded.source_blob_sha256
  returning * into v_current;

  insert into public.player_stat_snapshots(season_id, character_id, kills_total, kills_firearm, kills_melee,
    survival_seconds, alive, observed_at, source_blob_sha256)
  values (v_season_id, v_character_id, v_current.kills_total, v_current.kills_firearm, v_current.kills_melee,
    v_current.survival_seconds, p_alive, p_observed_at, p_blob_sha256)
  on conflict do nothing;
  return v_character_id;
end;
$$;

create or replace function public.start_ranking_season(p_name text, p_slug text, p_reward_message text default null)
returns uuid
language plpgsql security definer set search_path = ''
as $$
declare v_id uuid;
begin
  if exists (select 1 from public.ranking_seasons where status = 'active') then
    raise exception 'there is already an active season';
  end if;
  insert into public.ranking_seasons(name, slug, reward_message)
  values (p_name, p_slug, coalesce(nullif(trim(p_reward_message), ''), 'Premiação especial oferecida pelo Admin do servidor.'))
  returning id into v_id;
  return v_id;
end;
$$;

create or replace function public.close_ranking_season(p_season_id uuid, p_winner_character_id uuid default null)
returns uuid
language plpgsql security definer set search_path = ''
as $$
declare v_winner record;
begin
  if not exists (select 1 from public.ranking_seasons where id = p_season_id and status = 'active') then
    raise exception 'active season not found';
  end if;
  select st.character_id, c.public_name, st.kills_total, st.survival_seconds, s.reward_message into v_winner
  from public.player_statistics_current st
  join public.game_characters c on c.id = st.character_id
  join public.ranking_seasons s on s.id = st.season_id
  where st.season_id = p_season_id and st.kills_total is not null
    and (p_winner_character_id is null or st.character_id = p_winner_character_id)
  order by st.kills_total desc, st.survival_seconds desc nulls last, c.public_name asc limit 1;

  if p_winner_character_id is not null and v_winner.character_id is null then
    raise exception 'selected winner is not ranked in this season';
  end if;

  insert into public.season_winners(season_id, character_id, winner_name, final_kills_total, final_survival_seconds, reward_message)
  values (p_season_id, v_winner.character_id, v_winner.public_name, v_winner.kills_total,
    v_winner.survival_seconds, coalesce(v_winner.reward_message, 'Premiação especial oferecida pelo Admin do servidor.'))
  on conflict (season_id) do nothing;
  update public.ranking_seasons set status = 'closed', ended_at = now(), closed_at = now() where id = p_season_id;
  return p_season_id;
end;
$$;

revoke execute on function public.get_public_ranking(integer) from public;
revoke execute on function public.get_public_seasons(integer) from public;
revoke execute on function public.get_public_ranking_status() from public;
revoke execute on function public.get_public_player(uuid) from public;
revoke execute on function public.get_public_player_history(uuid, integer) from public;
revoke execute on function public.acquire_collector_lock(text, integer) from public;
revoke execute on function public.release_collector_lock(text) from public;
revoke execute on function public.ingest_player_observation(text, text, text, boolean, text, timestamptz, integer, integer, integer, bigint) from public;
revoke execute on function public.start_ranking_season(text, text, text) from public;
revoke execute on function public.close_ranking_season(uuid, uuid) from public;

revoke execute on function public.acquire_collector_lock(text, integer),
  public.release_collector_lock(text),
  public.ingest_player_observation(text, text, text, boolean, text, timestamptz, integer, integer, integer, bigint),
  public.start_ranking_season(text, text, text), public.close_ranking_season(uuid, uuid)
  from anon, authenticated;

grant execute on function public.get_public_ranking(integer) to anon, authenticated;
grant execute on function public.get_public_seasons(integer) to anon, authenticated;
grant execute on function public.get_public_ranking_status() to anon, authenticated;
grant execute on function public.get_public_player(uuid) to anon, authenticated;
grant execute on function public.get_public_player_history(uuid, integer) to anon, authenticated;
grant execute on function public.get_public_ranking(integer), public.get_public_seasons(integer),
  public.get_public_ranking_status(), public.get_public_player(uuid),
  public.get_public_player_history(uuid, integer) to service_role;
grant select, insert, update on public.collector_runs to service_role;
grant execute on function public.acquire_collector_lock(text, integer) to service_role;
grant execute on function public.release_collector_lock(text) to service_role;
grant execute on function public.ingest_player_observation(text, text, text, boolean, text, timestamptz, integer, integer, integer, bigint) to service_role;
grant execute on function public.start_ranking_season(text, text, text) to service_role;
grant execute on function public.close_ranking_season(uuid, uuid) to service_role;
