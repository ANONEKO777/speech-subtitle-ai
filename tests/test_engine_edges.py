from backend.core.model import Word
from backend.core.vad import Chunk
from scripts.engine_edges import edge_scorecard


def test_scorecard_counts_which_periods_repair_removes() -> None:
    chunks = [Chunk(0, 1000), Chunk(1100, 2000), Chunk(2600, 3500)]
    placed = [
        [Word("we", 0, 400), Word("fit.", 500, 900)],
        [Word("and", 1200, 1500), Word("so.", 1600, 1900)],
        [Word("Next", 2700, 3000)],
    ]
    reference = [
        Word("we", 0, 400),
        Word("fit", 500, 900),
        Word("and", 1200, 1500),
        Word("so.", 1600, 1900),
        Word("Next", 2700, 3000),
    ]
    removed_false, false, removed_true, true = edge_scorecard(
        chunks, placed, reference, [(0, 1), (1, 2)]
    )
    assert (removed_false, false) == (1, 1)
    assert (removed_true, true) == (0, 1)
