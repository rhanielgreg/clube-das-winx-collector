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


def ttf_observation_counters(blob):
    """Categorias reais da fonte, SEM afirmar identidade/escopo vitalício.

    Somente um emissor confiável pode atestar que correspondem à vida indicada.
    Vehicle participa do total; Other continua separado, nunca por subtração.
    """
    base = confirmed_stats(blob)
    if base['p_kills_total'] is None:
        return None
    categories = anchored_value(blob, 'TTF_KillStats')['categories']
    mapping = {'Axe':'kills_axe','Blunt':'kills_blunt','SmallBlunt':'kills_small_blunt',
               'LongBlade':'kills_long_blade','SmallBlade':'kills_small_blade','Spear':'kills_spear',
               'Unarmed':'kills_unarmed','Vehicle':'kills_vehicle','Other':'kills_other'}
    result = {target: count(categories[source]) for source, target in mapping.items()}
    result.update(kills_total=base['p_kills_total'], kills_firearm=base['p_kills_firearm'], kills_melee=base['p_kills_melee'])
    if base['p_survival_seconds'] is not None:
        result['played_seconds'] = base['p_survival_seconds']
    return result
