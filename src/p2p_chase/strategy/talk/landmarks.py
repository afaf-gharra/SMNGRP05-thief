"""Map a real-world setting onto board regions, so hints can name places.

The agreed ``map_area`` turns bare compass directions into something a person
would actually say. "Cutting west past the river" carries the same spatial claim
as "moving west" but sounds like a fugitive rather than a robot — and, more
usefully, it lets the two sides build a shared vocabulary that the lie detector
on the other end can still parse.

Every setting resolves to the same nine sectors, so the parser and the generator
agree by construction and an unknown setting degrades to plain bearings instead
of failing.
"""

from p2p_chase.constants import Cell
from p2p_chase.domain.board import Board

#: sector key -> (row band, column band), each -1 / 0 / +1
SECTORS: tuple[str, ...] = ("NW", "N", "NE", "W", "C", "E", "SW", "S", "SE")

_OFFSETS: dict[str, tuple[int, int]] = {
    "NW": (-1, -1), "N": (-1, 0), "NE": (-1, 1),
    "W": (0, -1), "C": (0, 0), "E": (0, 1),
    "SW": (1, -1), "S": (1, 0), "SE": (1, 1),
}

#: Setting -> sector -> landmark words. Lower-case, single tokens, because the
#: hint parser tokenises on words and must be able to match them back.
GAZETTEER: dict[str, dict[str, list[str]]] = {
    "new york": {
        "NW": ["harlem", "columbia"], "N": ["bronx", "yankee"], "NE": ["astoria", "queens"],
        "W": ["chelsea", "highline"], "C": ["midtown", "broadway"], "E": ["gramercy", "un"],
        "SW": ["tribeca", "battery"], "S": ["soho", "chinatown"], "SE": ["brooklyn", "dumbo"],
    },
    "london": {
        "NW": ["camden", "hampstead"], "N": ["islington", "angel"], "NE": ["hackney", "shoreditch"],
        "W": ["kensington", "notting"], "C": ["soho", "holborn"], "E": ["whitechapel", "aldgate"],
        "SW": ["chelsea", "battersea"], "S": ["southwark", "borough"], "SE": ["greenwich", "peckham"],
    },
    "paris": {
        "NW": ["batignolles", "clichy"], "N": ["montmartre", "sacre"], "NE": ["belleville", "buttes"],
        "W": ["passy", "trocadero"], "C": ["louvre", "chatelet"], "E": ["bastille", "nation"],
        "SW": ["grenelle", "eiffel"], "S": ["montparnasse", "denfert"], "SE": ["bercy", "tolbiac"],
    },
}

#: Used when the setting is empty or unknown: still spatial, just not evocative.
GENERIC: dict[str, list[str]] = {
    "NW": ["northwest", "upper"], "N": ["north", "top"], "NE": ["northeast", "corner"],
    "W": ["west", "left"], "C": ["centre", "middle"], "E": ["east", "right"],
    "SW": ["southwest", "lower"], "S": ["south", "bottom"], "SE": ["southeast", "edge"],
}


def gazetteer_for(setting: str) -> dict[str, list[str]]:
    """Landmark vocabulary for a setting, falling back to generic bearings."""
    return GAZETTEER.get((setting or "").strip().lower(), GENERIC)


def sector_cells(board: Board, sector: str) -> set[Cell]:
    """Every cell inside a sector — the region a landmark word claims."""
    d_row, d_col = _OFFSETS.get(sector, (0, 0))
    return {
        (row, col)
        for row in range(board.size)
        for col in range(board.size)
        if _offset(row, board.size) == d_row and _offset(col, board.size) == d_col
    }


def _offset(index: int, size: int) -> int:
    third = size / 3.0
    if index < third:
        return -1
    return 0 if index < 2 * third else 1


def cell_sector(board: Board, cell: Cell) -> str:
    """The sector key for a cell, e.g. ``"NE"``."""
    row, col = _offset(cell[0], board.size), _offset(cell[1], board.size)
    for key, offsets in _OFFSETS.items():
        if offsets == (row, col):
            return key
    return "C"


def landmark_index(board: Board, setting: str) -> dict[str, Cell]:
    """word -> a representative cell, for :func:`p2p_chase.domain.hint_parser.parse_hint`."""
    index: dict[str, Cell] = {}
    for sector, words in gazetteer_for(setting).items():
        cells = sector_cells(board, sector)
        if not cells:
            continue
        representative = sorted(cells)[len(cells) // 2]
        for word in words:
            index[word] = representative
    return index


def opposite(sector: str) -> str:
    """The sector diagonally across the board — the natural decoy for a lie."""
    d_row, d_col = _OFFSETS.get(sector, (0, 0))
    target = (-d_row, -d_col)
    for key, offsets in _OFFSETS.items():
        if offsets == target:
            return key
    return "C"
