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
        return dict(
            p_kills_total=total,
            p_kills_firearm=values['Firearm'],
            p_kills_melee=sum(values[key] for key in MELEE),
            # O Lua TTF acumula segundos reais de jogo, nao horas sobrevividas.
            # Nao apresentar tempo jogado como tempo de sobrevivencia.
            p_survival_seconds=None,
        )
    except (ValueError, KeyError, TypeError, UnicodeError, IndexError, struct.error):
        return unavailable
