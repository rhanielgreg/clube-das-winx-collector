"""CLI administrativa para abrir, listar e encerrar temporadas do ranking."""
import argparse
import json
import os
import re
import sys

import requests


def required(key):
    value = os.getenv(key, '').strip()
    if not value:
        raise RuntimeError(f'Variavel obrigatoria ausente: {key}')
    return value


def rpc(name, payload):
    url = required('SUPABASE_URL').rstrip('/') + '/rest/v1/rpc/' + name
    key = required('SUPABASE_SERVICE_ROLE_KEY')
    response = requests.post(url, json=payload, headers={
        'apikey': key,
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/json',
    }, timeout=25)
    if not response.ok:
        raise RuntimeError(f'Supabase respondeu HTTP {response.status_code}: {response.text[:400]}')
    return response.json() if response.content else None


def command_start(args):
    slug = args.slug.strip().lower()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('Slug invalido. Use letras minusculas, numeros e hifens.')
    season_id = rpc('start_ranking_season', {
        'p_name': args.name.strip(),
        'p_slug': slug,
        'p_reward_message': args.reward,
    })
    print(f'Temporada criada: {season_id}')


def command_close(args):
    if not args.yes:
        raise RuntimeError('Encerramento cancelado. Repita com --yes depois de conferir o ID.')
    season_id = rpc('close_ranking_season', {
        'p_season_id': args.id,
        'p_winner_character_id': args.winner_id,
    })
    print(f'Temporada encerrada e resultado preservado: {season_id}')


def command_list(_args):
    seasons = rpc('get_public_seasons', {'p_limit': 50})
    print(json.dumps(seasons, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Administracao manual de temporadas Clube das Winx')
    commands = parser.add_subparsers(required=True)
    start = commands.add_parser('start', help='abre uma nova temporada')
    start.add_argument('--name', required=True)
    start.add_argument('--slug', required=True)
    start.add_argument('--reward', default='Premiação especial oferecida pelo Admin do servidor.')
    start.set_defaults(run=command_start)
    close = commands.add_parser('close', help='encerra a temporada e grava o vencedor')
    close.add_argument('--id', required=True)
    close.add_argument('--winner-id', help='UUID do vencedor escolhido pelo Admin em caso de empate')
    close.add_argument('--yes', action='store_true', help='confirma o encerramento irreversivel')
    close.set_defaults(run=command_close)
    listing = commands.add_parser('list', help='lista temporadas e vencedores')
    listing.set_defaults(run=command_list)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Erro: {error}', file=sys.stderr)
        raise SystemExit(1)
