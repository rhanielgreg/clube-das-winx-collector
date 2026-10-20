"""Leitor restrito do modData TTF validado contra amostra local do servidor."""
import math
import struct
from probe_stats import anchored_value

CATEGORIES = {'Axe', 'LongBlade', 'SmallBlade', 'Spear', 'Blunt', 'SmallBlunt', 'Firearm', 'Vehicle', 'Unarmed', 'Other'}
MELEE = {'Axe', 'LongBlade', 'SmallBlade', 'Spear', 'Blunt', 'SmallBlunt', 'Unarmed'}


def count(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Contagem invalida')
    if not math.isfinite(value) or value < 0 or value > 2_000_000_000 or int(value) != value:
        raise ValueError('Contagem fora do limite')
    return int(value)


def game_time_seconds(value):
    """Valida o tempo acumulado pelo TTF em segundos de jogo."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Tempo de jogo invalido')
    if not math.isfinite(value) or value < 0 or value > 31_536_000_000:
        raise ValueError('Tempo de jogo fora do limite')
    return int(value)


def confirmed_stats(blob):
    unavailable = dict(p_kills_total=None, p_kills_firearm=None, p_kills_melee=None, p_survival_seconds=None)
    try:
        data = anchored_value(blob, 'TTF_KillStats')
        categories = data['categories']
        weapons = data['weapons']
        if set(categories) != CATEGORIES or not isinstance(weapons, dict):
            raise ValueError('Estrutura TTF desconhecida')
        values = {key: count(value) for key, value in categories.items()}
        total = sum(values.values())
        if total != sum(count(value) for value in weapons.values()):
            raise ValueError('Categorias e armas divergem')
        if values['Vehicle'] != count(data['vehicleKills']):
            raise ValueError('Kills de veiculo divergem')

        # O campo TTF e tempo jogado acumulado, nao uma estimativa inventada.
        try:
            played_seconds = game_time_seconds(anchored_value(blob, 'TTFStatsGameTimeSeconds'))
        except (ValueError, struct.error, UnicodeError):
            played_seconds = None

        return dict(
            p_kills_total=total,
            p_kills_firearm=values['Firearm'],
            p_kills_melee=sum(values[key] for key in MELEE),
            # Mantem o contrato publico existente; este valor representa tempo jogado.
            p_survival_seconds=played_seconds,
        )
    except (ValueError, KeyError, TypeError, UnicodeError, IndexError, struct.error):
        return unavailable
